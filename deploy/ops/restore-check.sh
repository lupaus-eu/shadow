#!/usr/bin/env bash
# Isolated restore rehearsal (ADR-013). Runs inside a disposable, hardened
# runner started by deploy/bin/restore-rehearsal with the backup directory
# mounted read-only. The separately held private key (and optional passphrase)
# arrive on stdin as a tar stream and live only in this container's tmpfs.
# Verifies the stored checksum, decrypts, restores into the disposable
# PostgreSQL target named by PGHOST, then checks schema and data. Prints only
# identifiers, counts and check results, never row contents.

set -Eeuo pipefail
umask 077

readonly BACKUP_DIR=/backups

log() {
  printf '%s restore %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

fail() {
  log "status=failed error=\"$1\""
  exit 1
}

manifest_value() {
  local value
  value="$(grep -E "^$1=" "${MANIFEST}" | head -n 1 | cut -d= -f2-)"
  [[ -n "${value}" ]] || fail "manifest is missing $1"
  printf '%s' "${value}"
}

query() {
  psql -X -A -t -v ON_ERROR_STOP=1 -c "$1"
}

requested_id="${RESTORE_BACKUP_ID:-}"
[[ "${requested_id}" =~ ^shadow-[0-9]{8}T[0-9]{6}Z-[a-z-]+-[0-9a-f]{6}$ ]] || fail "invalid backup ID"
DUMP="${BACKUP_DIR}/${requested_id}.dump.gpg"
MANIFEST="${BACKUP_DIR}/${requested_id}.manifest"
[[ -r "${MANIFEST}" ]] || fail "backup has no readable completion manifest"
[[ -r "${DUMP}" ]] || fail "encrypted backup file is not readable"

secrets_dir="$(mktemp -d /tmp/secrets.XXXXXX)"
tar --extract --ignore-zeros --no-same-owner --directory "${secrets_dir}" --file - 2>/dev/null \
  || fail "could not read key material from stdin"
PRIVATE_KEY="${secrets_dir}/backup-private-key.asc"
PASSPHRASE_FILE="${secrets_dir}/backup-key-passphrase"
[[ -r "${PRIVATE_KEY}" ]] || fail "backup private key was not supplied"

backup_id="$(manifest_value BACKUP_ID)"
[[ "${backup_id}" == "${requested_id}" ]] || fail "manifest identifier mismatch"
expected_sha256="$(manifest_value DUMP_SHA256)"
expected_version="$(manifest_value SCHEMA_MIGRATION_VERSION)"
expected_tables="$(manifest_value TABLE_COUNT)"
log "status=started backup_id=${backup_id}"

actual_sha256="$(sha256sum "${DUMP}" | cut -d' ' -f1)"
[[ "${actual_sha256}" == "${expected_sha256}" ]] || fail "checksum mismatch"
log "check=checksum result=pass"

GNUPGHOME="$(mktemp -d /tmp/gnupg.XXXXXX)"
export GNUPGHOME
gpg --batch --quiet --import "${PRIVATE_KEY}" 2>/dev/null || fail "private key import failed"
decrypt_options=(--batch --no-tty --quiet --decrypt)
if [[ -r "${PASSPHRASE_FILE}" ]]; then
  decrypt_options+=(--pinentry-mode loopback --passphrase-file "${PASSPHRASE_FILE}")
fi

for attempt in $(seq 1 30); do
  pg_isready --quiet && break
  [[ "${attempt}" == "30" ]] && fail "disposable restore target is not ready"
  sleep 1
done

if ! gpg "${decrypt_options[@]}" "${DUMP}" \
  | pg_restore --no-owner --no-acl --exit-on-error --single-transaction --dbname "${PGDATABASE}"; then
  fail "decryption or pg_restore failed"
fi
log "check=decrypt-and-restore result=pass"

if [[ "$(query "SELECT to_regclass('schema_migrations') IS NOT NULL")" == "t" ]]; then
  restored_version="$(query 'SELECT coalesce(max(version), 0) FROM schema_migrations')"
  restored_rows="$(query 'SELECT count(*) FROM schema_migrations')"
else
  restored_version=0
  restored_rows=0
fi
[[ "${restored_version}" == "${expected_version}" ]] || fail "schema migration version ${restored_version} != ${expected_version}"
[[ "${restored_rows}" == "${restored_version}" ]] || fail "schema migration history is not contiguous"
log "check=schema-migrations result=pass version=${restored_version}"

restored_tables="$(query 'SELECT count(*) FROM pg_tables WHERE schemaname = current_schema()')"
[[ "${restored_tables}" == "${expected_tables}" ]] || fail "table count ${restored_tables} != ${expected_tables}"
log "check=table-count result=pass tables=${restored_tables}"

invalid_constraints="$(query 'SELECT count(*) FROM pg_constraint WHERE NOT convalidated')"
[[ "${invalid_constraints}" == "0" ]] || fail "restored database has unvalidated constraints"
log "check=constraints result=pass"

# Exact per-table row counts (identifiers and counts only).
while IFS= read -r table; do
  [[ -n "${table}" ]] || continue
  count="$(query "SELECT count(*) FROM \"${table//\"/\"\"}\"")"
  log "rows table=${table} count=${count}"
done < <(query 'SELECT tablename FROM pg_tables WHERE schemaname = current_schema() ORDER BY tablename')

log "status=success backup_id=${backup_id} schema_version=${restored_version} tables=${restored_tables}"
