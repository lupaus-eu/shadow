#!/usr/bin/env bash
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly BASE_ENV_FILE="${1:-${REPOSITORY_ROOT}/.env}"
readonly AUTHENTIK_ENV_FILE="${2:-${REPOSITORY_ROOT}/.env.authentik.local}"
readonly ENTRA_ENV_FILE="${3:-${REPOSITORY_ROOT}/.env.entra.local}"

for required_file in "${BASE_ENV_FILE}" "${AUTHENTIK_ENV_FILE}" "${ENTRA_ENV_FILE}"; do
  if [[ ! -f "${required_file}" ]]; then
    printf 'Missing required local environment file: %s\n' "${required_file}" >&2
    exit 1
  fi
done

relative_env_file="${ENTRA_ENV_FILE}"
if [[ "${ENTRA_ENV_FILE}" == "${REPOSITORY_ROOT}/"* ]]; then
  relative_env_file="${ENTRA_ENV_FILE#"${REPOSITORY_ROOT}/"}"
fi
if git -C "${REPOSITORY_ROOT}" ls-files --error-unmatch "${relative_env_file}" \
  >/dev/null 2>&1; then
  printf 'Local Entra environment file is tracked by Git.\n' >&2
  exit 1
fi

rendered_json="$(mktemp)"
trap 'rm -f "${rendered_json}"' EXIT

docker compose \
  --project-directory "${REPOSITORY_ROOT}" \
  --env-file "${BASE_ENV_FILE}" \
  --env-file "${AUTHENTIK_ENV_FILE}" \
  --env-file "${ENTRA_ENV_FILE}" \
  -f "${REPOSITORY_ROOT}/docker-compose.yml" \
  -f "${REPOSITORY_ROOT}/docker-compose.entra.yml" \
  config --quiet
docker compose \
  --project-directory "${REPOSITORY_ROOT}" \
  --env-file "${BASE_ENV_FILE}" \
  --env-file "${AUTHENTIK_ENV_FILE}" \
  --env-file "${ENTRA_ENV_FILE}" \
  -f "${REPOSITORY_ROOT}/docker-compose.yml" \
  -f "${REPOSITORY_ROOT}/docker-compose.entra.yml" \
  config --format json >"${rendered_json}"

python3 - "${rendered_json}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    services = json.load(source)["services"]

configurator = services["authentik-entra-config"]
required = {
    "ENTRA_APPLICATION_CLIENT_ID",
    "ENTRA_DIRECTORY_TENANT_ID",
    "ENTRA_CLIENT_SECRET",
}
assert required.issubset(configurator["environment"])
assert all(configurator["environment"][name] for name in required)
assert configurator["entrypoint"] == ["sh", "/config/configure-entra.sh"]
required_mounts = {
    "/config/configure-entra.sh",
    "/blueprints/schatten-entra.yaml",
    "/blueprints/schatten-entra-source.yaml",
    "/blueprints/schatten-entra-identification.yaml",
}
read_only_mounts = {
    mount["target"]
    for mount in configurator["volumes"]
    if mount["read_only"] is True
}
assert required_mounts.issubset(read_only_mounts)
worker = services["authentik-worker"]
assert not required.intersection(worker["environment"])
assert not any("schatten-entra" in mount["target"] for mount in worker["volumes"])
assert services["backend"]["depends_on"]["authentik-entra-config"]["condition"] == (
    "service_completed_successfully"
)
assert services["backend"]["environment"]["OIDC_ISSUER"] == (
    "https://auth.localhost:9443/application/o/schatten/"
)
PY

if grep -Eiq 'ENTRA_|schatten-entra|schatten-auth' \
  "${REPOSITORY_ROOT}/docker-compose.production.yml" \
  "${REPOSITORY_ROOT}/docker-compose.release.yml" \
  "${REPOSITORY_ROOT}/docker-compose.coolify.yml"; then
  printf 'Local Entra federation reference found in a production manifest.\n' >&2
  exit 1
fi

printf 'Local Entra configurator, secret isolation, HTTPS issuer and production-manifest checks passed.\n'
