# shellcheck shell=bash
# Shared helpers for deploy/bin/* operator commands. These commands use the
# already-installed Docker Engine/Compose and never provision the host.

set -Eeuo pipefail

SCHATTEN_ENV_FILE="${SCHATTEN_ENV_FILE:-/opt/apps/schatten-config/production.env}"
SCHATTEN_PROJECT=schatten

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
}

die() {
  log "ERROR: $*"
  exit 1
}

# Read one KEY=value from the protected env file without sourcing it.
config_value() {
  local key="$1" default="${2-}" line
  line="$(grep -E "^${key}=" "${SCHATTEN_ENV_FILE}" | tail -n 1 || true)"
  if [[ -n "${line}" ]]; then
    line="${line#*=}"
    line="${line%\"}"
    line="${line#\"}"
    printf '%s' "${line}"
  else
    printf '%s' "${default}"
  fi
}

load_config() {
  [[ -f "${SCHATTEN_ENV_FILE}" ]] || die "Missing protected env file ${SCHATTEN_ENV_FILE}"
  local mode owner
  mode="$(stat -c %a "${SCHATTEN_ENV_FILE}")"
  owner="$(stat -c %u "${SCHATTEN_ENV_FILE}")"
  [[ "${mode}" =~ ^[0-7]?[0-7]00$ ]] || die "${SCHATTEN_ENV_FILE} must not be group/other accessible (mode ${mode})"
  [[ "${owner}" == "$(id -u)" ]] || die "${SCHATTEN_ENV_FILE} must be owned by the operator running this command"
  if grep -qE '^(BACKEND_IMAGE|FRONTEND_IMAGE)=' "${SCHATTEN_ENV_FILE}"; then
    die "Image references come from release records, not ${SCHATTEN_ENV_FILE}"
  fi
  # Used by the sourcing deploy/bin commands.
  # shellcheck disable=SC2034
  {
    SCHATTEN_STATE_DIR="$(config_value SCHATTEN_STATE_DIR /opt/apps/schatten-state)"
    SCHATTEN_RELEASES_DIR="$(config_value SCHATTEN_RELEASES_DIR /opt/apps/schatten-releases)"
    # Must match schatten-receive's SCHATTEN_SOURCES_DIR (same default).
    SCHATTEN_SOURCES_DIR="$(config_value SCHATTEN_SOURCES_DIR /opt/apps/schatten-sources)"
    SCHATTEN_BACKUP_DIR="$(config_value SCHATTEN_BACKUP_DIR /opt/postgres-backups)"
    SCHATTEN_BACKUP_UID="$(config_value SCHATTEN_BACKUP_UID 10002)"
    SCHATTEN_BACKUP_GID="$(config_value SCHATTEN_BACKUP_GID 10002)"
    SCHATTEN_DOCKER_SOCKET="$(config_value SCHATTEN_DOCKER_SOCKET /var/run/docker.sock)"
  }
  SCHATTEN_LOCK_DIR="${SCHATTEN_STATE_DIR}/locks"
}

release_dir() {
  local release_id="$1"
  [[ "${release_id}" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] || die "Invalid release ID: ${release_id}"
  printf '%s/%s' "${SCHATTEN_RELEASES_DIR}" "${release_id}"
}

release_value() {
  local directory="$1" key="$2" value
  value="$(grep -E "^${key}=" "${directory}/release.env" | head -n 1 | cut -d= -f2-)"
  [[ -n "${value}" ]] || die "Release record ${directory} is missing ${key}"
  printf '%s' "${value}"
}

pointer_value() {
  local pointer="${SCHATTEN_RELEASES_DIR}/$1"
  if [[ -f "${pointer}" ]]; then
    cat "${pointer}"
  fi
}

# Run Compose from a frozen release directory with a minimal environment so
# stray operator shell variables cannot override the protected configuration.
compose_release() {
  local directory="$1"
  shift
  local files=(--file "${directory}/source/docker-compose.production.yml")
  if [[ -n "${SCHATTEN_COMPOSE_OVERRIDE_FILE:-}" ]]; then
    # Disposable QA only (for example internal TLS); recorded in deployments.
    files+=(--file "${SCHATTEN_COMPOSE_OVERRIDE_FILE}")
  fi
  env -i \
    PATH="${PATH}" \
    HOME="${HOME}" \
    ${DOCKER_HOST:+DOCKER_HOST="${DOCKER_HOST}"} \
    BACKEND_IMAGE="$(release_value "${directory}" BACKEND_IMAGE_ID)" \
    FRONTEND_IMAGE="$(release_value "${directory}" FRONTEND_IMAGE_ID)" \
    docker compose \
      --project-name "${SCHATTEN_PROJECT}" \
      --project-directory "${directory}/source" \
      --env-file "${SCHATTEN_ENV_FILE}" \
      "${files[@]}" \
      "$@"
}

verify_release_images() {
  local directory="$1" kind tag expected actual
  [[ -f "${directory}/release.env" && -d "${directory}/source" ]] || die "Release record ${directory} is incomplete"
  for kind in BACKEND FRONTEND; do
    tag="$(release_value "${directory}" "${kind}_IMAGE")"
    expected="$(release_value "${directory}" "${kind}_IMAGE_ID")"
    actual="$(docker image inspect --format '{{.Id}}' "${tag}" 2>/dev/null)" \
      || die "Frozen image ${tag} is not present locally"
    [[ "${actual}" == "${expected}" ]] || die "${tag} resolves to ${actual}, not the recorded ${expected}"
  done
}

# Shared maintenance lock: many releases/backups/restores may hold it; the
# weekly Docker cleanup needs it exclusively and skips while it is held.
hold_maintenance_lock() {
  [[ -r "${SCHATTEN_LOCK_DIR}/maintenance.lock" ]] || die "Missing ${SCHATTEN_LOCK_DIR}/maintenance.lock; run deploy/bin/init-state"
  exec 8<"${SCHATTEN_LOCK_DIR}/maintenance.lock"
  flock --shared --wait 600 8 || die "Docker cleanup holds the maintenance lock"
}

hold_release_lock() {
  [[ -r "${SCHATTEN_LOCK_DIR}/release.lock" ]] || die "Missing ${SCHATTEN_LOCK_DIR}/release.lock; run deploy/bin/init-state"
  exec 7<"${SCHATTEN_LOCK_DIR}/release.lock"
  flock --exclusive --nonblock 7 || die "Another build, release or rollback is running"
}

wait_for_healthy() {
  local directory="$1" service="$2" attempts="${3:-60}" container="" state="" unhealthy=0
  for _ in $(seq 1 "${attempts}"); do
    container="$(compose_release "${directory}" ps --quiet "${service}")"
    if [[ -n "${container}" ]]; then
      state="$(docker inspect --format '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container}")"
      [[ "${state}" == "running/healthy" ]] && return 0
      [[ "${state}" == exited/* ]] && break
      # An unchanged container is not recreated by a deploy and may carry an
      # unhealthy status from a transient probe failure; the next passing
      # probe clears it. Docker starts that probe one interval after the
      # failed one ends, so recovery can take interval + timeout (20 s for the
      # worker); fail only after 15 samples of at least 2 s (30 s or more).
      if [[ "${state}" == */unhealthy ]]; then
        unhealthy=$((unhealthy + 1))
        (( unhealthy >= 15 )) && break
      else
        unhealthy=0
      fi
    fi
    sleep 2
  done
  log "Service ${service} did not become healthy (state ${state:-missing})"
  # Exit codes and times only: probe output could echo configuration.
  # Docker records a probe timeout as exit code -1.
  if [[ -n "${container}" ]]; then
    docker inspect \
      --format '{{if .State.Health}}{{range .State.Health.Log}}probe exit={{.ExitCode}} start={{.Start}} end={{.End}}{{println}}{{end}}{{end}}' \
      "${container}" 2>/dev/null | sed '/^$/d' | while read -r probe; do log "${service} ${probe}"; done || true
  fi
  return 1
}
