# shellcheck shell=bash
# Shared helpers for deploy/bin/* operator commands. These commands use the
# already-installed Docker Engine/Compose and never provision the host.

set -Eeuo pipefail

SHADOW_ENV_FILE="${SHADOW_ENV_FILE:-/opt/apps/shadow-config/production.env}"
SHADOW_PROJECT=shadow

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
  line="$(grep -E "^${key}=" "${SHADOW_ENV_FILE}" | tail -n 1 || true)"
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
  [[ -f "${SHADOW_ENV_FILE}" ]] || die "Missing protected env file ${SHADOW_ENV_FILE}"
  local mode owner
  mode="$(stat -c %a "${SHADOW_ENV_FILE}")"
  owner="$(stat -c %u "${SHADOW_ENV_FILE}")"
  [[ "${mode}" =~ ^[0-7]?[0-7]00$ ]] || die "${SHADOW_ENV_FILE} must not be group/other accessible (mode ${mode})"
  [[ "${owner}" == "$(id -u)" ]] || die "${SHADOW_ENV_FILE} must be owned by the operator running this command"
  if grep -qE '^(BACKEND_IMAGE|FRONTEND_IMAGE)=' "${SHADOW_ENV_FILE}"; then
    die "Image references come from release records, not ${SHADOW_ENV_FILE}"
  fi
  # Used by the sourcing deploy/bin commands.
  # shellcheck disable=SC2034
  {
    SHADOW_STATE_DIR="$(config_value SHADOW_STATE_DIR /opt/apps/shadow-state)"
    SHADOW_RELEASES_DIR="$(config_value SHADOW_RELEASES_DIR /opt/apps/shadow-releases)"
    # Must match shadow-receive's SHADOW_SOURCES_DIR (same default).
    SHADOW_SOURCES_DIR="$(config_value SHADOW_SOURCES_DIR /opt/apps/shadow-sources)"
    SHADOW_BACKUP_DIR="$(config_value SHADOW_BACKUP_DIR /opt/postgres-backups)"
    SHADOW_BACKUP_UID="$(config_value SHADOW_BACKUP_UID 10002)"
    SHADOW_BACKUP_GID="$(config_value SHADOW_BACKUP_GID 10002)"
    SHADOW_DOCKER_SOCKET="$(config_value SHADOW_DOCKER_SOCKET /var/run/docker.sock)"
  }
  SHADOW_LOCK_DIR="${SHADOW_STATE_DIR}/locks"
}

release_dir() {
  local release_id="$1"
  [[ "${release_id}" =~ ^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$ ]] || die "Invalid release ID: ${release_id}"
  printf '%s/%s' "${SHADOW_RELEASES_DIR}" "${release_id}"
}

release_value() {
  local directory="$1" key="$2" value
  value="$(grep -E "^${key}=" "${directory}/release.env" | head -n 1 | cut -d= -f2-)"
  [[ -n "${value}" ]] || die "Release record ${directory} is missing ${key}"
  printf '%s' "${value}"
}

pointer_value() {
  local pointer="${SHADOW_RELEASES_DIR}/$1"
  if [[ -f "${pointer}" ]]; then
    cat "${pointer}"
  fi
}

# ADR-015 switches and client cap (TASK-069P) come from the protected env file;
# unset means the Compose defaults (off, 10000). Prints the first problem.
mcp_config_problem() {
  local key value lines
  # Compose also reads export-prefixed, indented and KEY: value lines, which
  # config_value does not see, so only plain KEY=value lines are allowed.
  for key in MCP_ENABLED MCP_CHANGE_SET_REVIEW_ENABLED MCP_OAUTH_MAX_CLIENTS; do
    lines="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*[:=]" "${SHADOW_ENV_FILE}" || true)"
    if [[ -n "${lines}" ]] && grep -qvE "^${key}=" <<<"${lines}"; then
      printf '%s must be a plain %s=<value> line' "${key}" "${key}"
      return
    fi
  done
  for key in MCP_ENABLED MCP_CHANGE_SET_REVIEW_ENABLED; do
    value="$(config_value "${key}" false)"
    if [[ "${value}" != true && "${value}" != false ]]; then
      printf '%s must be true or false' "${key}"
      return
    fi
  done
  value="$(config_value MCP_OAUTH_MAX_CLIENTS 10000)"
  [[ "${value}" =~ ^[1-9][0-9]{0,8}$ ]] || printf 'MCP_OAUTH_MAX_CLIENTS must be a positive whole number'
}

# The MCP settings a release's backend gets, as KEY=value lines. Releases built
# before TASK-069P pin them in Compose and ignore the env file. The rendered
# configuration holds secrets and is only parsed, never printed.
release_mcp_state() {
  compose_release "$1" config --format json | python3 -c '
import json, sys
environment = json.load(sys.stdin)["services"]["backend"].get("environment", {})
defaults = {
    "MCP_ENABLED": "false",
    "MCP_CHANGE_SET_REVIEW_ENABLED": "false",
    "MCP_OAUTH_MAX_CLIENTS": "10000",
}
for key, default in defaults.items():
    print(key + "=" + str(environment.get(key) or default))
'
}

# The MCP settings the env file asks for, in release_mcp_state's format. A
# release that renders other values ignores the env file.
env_mcp_state() {
  printf 'MCP_ENABLED=%s\nMCP_CHANGE_SET_REVIEW_ENABLED=%s\nMCP_OAUTH_MAX_CLIENTS=%s\n' \
    "$(config_value MCP_ENABLED false)" "$(config_value MCP_CHANGE_SET_REVIEW_ENABLED false)" \
    "$(config_value MCP_OAUTH_MAX_CLIENTS 10000)"
}

# The newest successful deployment record, or nothing.
last_deployment_record() {
  local file
  while IFS= read -r file; do
    if grep -qx 'STATUS=succeeded' "${file}"; then
      printf '%s' "${file}"
      return
    fi
  done < <(find "${SHADOW_STATE_DIR}/deployments" -maxdepth 1 -type f -name '*.env' 2>/dev/null | sort -r)
}

record_value() {
  local file="$1" key="$2" default="${3-}" value=""
  if [[ -n "${file}" ]]; then
    value="$(grep -E "^${key}=" "${file}" | tail -n 1 | cut -d= -f2- || true)"
  fi
  printf '%s' "${value:-${default}}"
}

# Run Compose from a frozen release directory with a minimal environment so
# stray operator shell variables cannot override the protected configuration.
compose_release() {
  local directory="$1"
  shift
  local files=(--file "${directory}/source/docker-compose.production.yml")
  if [[ -n "${SHADOW_COMPOSE_OVERRIDE_FILE:-}" ]]; then
    # Disposable QA only (for example internal TLS); recorded in deployments.
    files+=(--file "${SHADOW_COMPOSE_OVERRIDE_FILE}")
  fi
  env -i \
    PATH="${PATH}" \
    HOME="${HOME}" \
    ${DOCKER_HOST:+DOCKER_HOST="${DOCKER_HOST}"} \
    BACKEND_IMAGE="$(release_value "${directory}" BACKEND_IMAGE_ID)" \
    FRONTEND_IMAGE="$(release_value "${directory}" FRONTEND_IMAGE_ID)" \
    docker compose \
      --project-name "${SHADOW_PROJECT}" \
      --project-directory "${directory}/source" \
      --env-file "${SHADOW_ENV_FILE}" \
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
  [[ -r "${SHADOW_LOCK_DIR}/maintenance.lock" ]] || die "Missing ${SHADOW_LOCK_DIR}/maintenance.lock; run deploy/bin/init-state"
  exec 8<"${SHADOW_LOCK_DIR}/maintenance.lock"
  flock --shared --wait 600 8 || die "Docker cleanup holds the maintenance lock"
}

hold_release_lock() {
  [[ -r "${SHADOW_LOCK_DIR}/release.lock" ]] || die "Missing ${SHADOW_LOCK_DIR}/release.lock; run deploy/bin/init-state"
  exec 7<"${SHADOW_LOCK_DIR}/release.lock"
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
