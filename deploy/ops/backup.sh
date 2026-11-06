#!/usr/bin/env bash
# Encrypted PostgreSQL backup job (ADR-013). Runs inside the hardened
# backup-runner container: scheduled by Ofelia or on demand via
# deploy/bin/backup-now. Writes only job-owned files matching
# shadow-<UTC timestamp>-<reason>-<random>.{dump.gpg,manifest} under /backups.
#
# The runner holds only the encryption *public* key; decryption material never
# enters this container. The manifest is published last and marks completion.

set -Eeuo pipefail
umask 077

readonly BACKUP_DIR=/backups
readonly WORK_DIR="${BACKUP_DIR}/.incomplete"
readonly PUBLIC_KEY=/run/shadow/backup-public-key.asc
readonly LOCK_DIR=/locks
readonly NAME_PATTERN='^shadow-[0-9]{8}T[0-9]{6}Z-[a-z-]+-[0-9a-f]{6}$'

reason="${1:-manual}"
backup_id=""

log() {
  printf '%s backup %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

fail() {
  log "status=failed reason=${reason} backup_id=${backup_id:-none} error=\"$1\""
  exit 1
}

case "${reason}" in
  scheduled|pre-release|manual) ;;
  *) reason="invalid"; fail "reason must be scheduled, pre-release or manual" ;;
esac

retention_days="${BACKUP_RETENTION_DAYS:-7}"
lock_timeout="${BACKUP_LOCK_TIMEOUT_SECONDS:-1800}"
[[ "${retention_days}" =~ ^[1-9][0-9]*$ ]] || fail "BACKUP_RETENTION_DAYS must be a positive integer"
[[ "${lock_timeout}" =~ ^[0-9]+$ ]] || fail "BACKUP_LOCK_TIMEOUT_SECONDS must be an integer"

# Split DATABASE_URL into libpq variables so the password never appears in
# process arguments visible to other host users.
percent_decode() {
  local value="${1//\\/\\\\}"
  printf '%b' "${value//%/\\x}"
}

configure_database() {
  local url="${DATABASE_URL:-}"
  [[ -n "${url}" ]] || fail "DATABASE_URL is not set"
  url="${url/#postgresql+psycopg:\/\//postgresql://}"
  local pattern='^postgres(ql)?://([^:@/?]+)(:([^@/?]*))?@([^:/?]+)(:([0-9]+))?/([^?/]+)(\?(.*))?$'
  [[ "${url}" =~ ${pattern} ]] || fail "DATABASE_URL is not a supported PostgreSQL URL"
  PGUSER="$(percent_decode "${BASH_REMATCH[2]}")"
  PGPASSWORD="$(percent_decode "${BASH_REMATCH[4]}")"
  PGHOST="${BASH_REMATCH[5]}"
  PGPORT="${BASH_REMATCH[7]:-5432}"
  PGDATABASE="$(percent_decode "${BASH_REMATCH[8]}")"
  local query="${BASH_REMATCH[10]}" parameter
  if [[ -n "${query}" ]]; then
    IFS='&' read -r -a parameters <<<"${query}"
    for parameter in "${parameters[@]}"; do
      case "${parameter}" in
        sslmode=*) export PGSSLMODE="${parameter#sslmode=}" ;;
        sslrootcert=*)
          PGSSLROOTCERT="$(percent_decode "${parameter#sslrootcert=}")"
          export PGSSLROOTCERT
          ;;
        *) fail "DATABASE_URL has an unsupported query parameter" ;;
      esac
    done
  fi
  export PGUSER PGPASSWORD PGHOST PGPORT PGDATABASE
  export PGCONNECT_TIMEOUT=10 PGAPPNAME=shadow-backup
}

timestamp_epoch() {
  local stamp="${1:9:16}"
  date -u -d "${stamp:0:4}-${stamp:4:2}-${stamp:6:2} ${stamp:9:2}:${stamp:11:2}:${stamp:13:2}" +%s
}

configure_database

[[ -d "${BACKUP_DIR}" ]] || fail "backup directory is not mounted"
[[ -w "${BACKUP_DIR}" ]] || fail "backup directory is not writable by the backup user"
[[ -f "${PUBLIC_KEY}" && -r "${PUBLIC_KEY}" ]] || fail "backup encryption public key is missing or unreadable"
[[ -r "${LOCK_DIR}/maintenance.lock" && -r "${LOCK_DIR}/backup.lock" ]] || fail "operation lock files are missing"

# Shared maintenance lock: excludes Docker cleanup, coexists with releases.
exec 8<"${LOCK_DIR}/maintenance.lock"
flock --shared --wait "${lock_timeout}" 8 || fail "maintenance lock is held by Docker cleanup"
exec 9<"${LOCK_DIR}/backup.lock"
flock --exclusive --wait "${lock_timeout}" 9 || fail "another backup is still running"

GNUPGHOME="$(mktemp -d /tmp/gnupg.XXXXXX)"
export GNUPGHOME
key_listing="$(gpg --batch --with-colons --show-keys "${PUBLIC_KEY}" 2>/dev/null)" \
  || fail "backup encryption public key cannot be parsed"
if grep -q '^sec' <<<"${key_listing}"; then
  fail "refusing secret key material in the backup runner"
fi
[[ "$(grep -c '^pub' <<<"${key_listing}")" == "1" ]] || fail "backup key file must contain exactly one public key"
awk -F: '$1 == "pub" { print $12 }' <<<"${key_listing}" | grep -q 'E' \
  || fail "backup public key has no encryption capability"
key_fingerprint="$(awk -F: '$1 == "fpr" { print $10; exit }' <<<"${key_listing}")"

server_version="$(psql -X -A -t -c 'SHOW server_version' 2>/dev/null)" \
  || fail "database connection failed"
has_history="$(psql -X -A -t -c "SELECT to_regclass('schema_migrations') IS NOT NULL" 2>/dev/null)" \
  || fail "database metadata query failed"
migration_version=0
if [[ "${has_history}" == "t" ]]; then
  migration_version="$(psql -X -A -t -c 'SELECT coalesce(max(version), 0) FROM schema_migrations' 2>/dev/null)" \
    || fail "database metadata query failed"
fi
table_count="$(psql -X -A -t -c "SELECT count(*) FROM pg_tables WHERE schemaname = current_schema()" 2>/dev/null)" \
  || fail "database metadata query failed"

backup_id="shadow-$(date -u +%Y%m%dT%H%M%SZ)-${reason}-$(od -An -N3 -tx1 /dev/urandom | tr -d ' \n')"
mkdir -p "${WORK_DIR}" || fail "cannot create temporary backup directory"
chmod 0700 "${WORK_DIR}"
# Stale temporary files from interrupted runs (job-owned names only).
find "${WORK_DIR}" -maxdepth 1 -type f -name 'shadow-*' -mmin +1440 -delete 2>/dev/null || true

tmp_dump="${WORK_DIR}/${backup_id}.dump.gpg"
tmp_manifest="${WORK_DIR}/${backup_id}.manifest"
trap 'rm -f "${tmp_dump}" "${tmp_manifest}"' EXIT

log "status=started reason=${reason} backup_id=${backup_id}"

if ! pg_dump --format=custom --compress=zstd:3 --no-password \
  | gpg --batch --no-tty --quiet --trust-model always \
      --recipient-file "${PUBLIC_KEY}" --compress-algo none --cipher-algo AES256 \
      --output "${tmp_dump}" --encrypt; then
  fail "pg_dump, encryption or file write failed"
fi

dump_size="$(stat -c %s "${tmp_dump}")"
[[ "${dump_size}" -gt 0 ]] || fail "encrypted backup is empty"
# Without the secret key gpg lists the packets and then exits nonzero.
packets="$(gpg --batch --list-packets "${tmp_dump}" 2>/dev/null || true)"
grep -q '^:pubkey enc packet:' <<<"${packets}" \
  || fail "encrypted backup has no public-key encryption packet"
grep -Eq '^(:aead encrypted packet:|[[:space:]]+mdc_method: [1-9])' <<<"${packets}" \
  || fail "encrypted backup is not integrity protected"
dump_sha256="$(sha256sum "${tmp_dump}" | cut -d' ' -f1)" || fail "checksum failed"
sync "${tmp_dump}" || fail "fsync of encrypted backup failed"

{
  printf 'BACKUP_ID=%s\n' "${backup_id}"
  printf 'REASON=%s\n' "${reason}"
  printf 'COMPLETED_AT=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'FORMAT=%s\n' "pg_dump-custom-zstd+gpg-public-key"
  printf 'DUMP_FILE=%s\n' "${backup_id}.dump.gpg"
  printf 'DUMP_SIZE_BYTES=%s\n' "${dump_size}"
  printf 'DUMP_SHA256=%s\n' "${dump_sha256}"
  printf 'ENCRYPTION_KEY_FINGERPRINT=%s\n' "${key_fingerprint}"
  printf 'POSTGRES_SERVER_VERSION=%s\n' "${server_version}"
  printf 'PG_DUMP_VERSION=%s\n' "$(pg_dump --version)"
  printf 'SCHEMA_MIGRATION_VERSION=%s\n' "${migration_version}"
  printf 'TABLE_COUNT=%s\n' "${table_count}"
} >"${tmp_manifest}" || fail "manifest write failed"
sync "${tmp_manifest}" || fail "fsync of manifest failed"

mv "${tmp_dump}" "${BACKUP_DIR}/${backup_id}.dump.gpg" || fail "publishing encrypted backup failed"
mv "${tmp_manifest}" "${BACKUP_DIR}/${backup_id}.manifest" || fail "publishing manifest failed"
sync "${BACKUP_DIR}" || fail "fsync of backup directory failed"
trap - EXIT

# Seven-day retention on job-owned, completed backups. The newest backup is
# always kept; orphaned dumps without a manifest are removed after one day.
now="$(date -u +%s)"
cutoff=$(( now - retention_days * 86400 ))
pruned=0
retention_status=ok
shopt -s nullglob
for manifest in "${BACKUP_DIR}"/shadow-*.manifest; do
  base="$(basename "${manifest}" .manifest)"
  [[ "${base}" =~ ${NAME_PATTERN} && "${base}" != "${backup_id}" ]] || continue
  epoch="$(timestamp_epoch "${base}")" || continue
  if (( epoch < cutoff )); then
    if rm -f "${BACKUP_DIR}/${base}.dump.gpg" "${manifest}"; then
      pruned=$(( pruned + 1 ))
    else
      retention_status=failed
    fi
  fi
done
for dump in "${BACKUP_DIR}"/shadow-*.dump.gpg; do
  base="$(basename "${dump}" .dump.gpg)"
  [[ "${base}" =~ ${NAME_PATTERN} && ! -e "${BACKUP_DIR}/${base}.manifest" ]] || continue
  epoch="$(timestamp_epoch "${base}")" || continue
  if (( epoch < now - 86400 )); then
    rm -f "${dump}" || retention_status=failed
  fi
done

free_bytes="$(df -P -B1 "${BACKUP_DIR}" | awk 'NR == 2 { print $4 }')"
log "status=completed reason=${reason} backup_id=${backup_id} size_bytes=${dump_size} sha256=${dump_sha256} retention_days=${retention_days} retention=${retention_status} pruned=${pruned} free_bytes=${free_bytes}"
[[ "${retention_status}" == "ok" ]] || exit 2
