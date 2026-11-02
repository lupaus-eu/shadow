#!/usr/bin/env bash
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly BASE_ENV_FILE="${1:-${REPOSITORY_ROOT}/.env}"
readonly ENTRA_ENV_FILE="${2:-${REPOSITORY_ROOT}/.env.entra.local}"

for required_file in "${BASE_ENV_FILE}" "${ENTRA_ENV_FILE}"; do
  [[ -f "${required_file}" ]] || { printf 'Missing required local environment file: %s\n' "${required_file}" >&2; exit 1; }
done

relative_env_file="${ENTRA_ENV_FILE#"${REPOSITORY_ROOT}/"}"
if git -C "${REPOSITORY_ROOT}" ls-files --error-unmatch "${relative_env_file}" >/dev/null 2>&1; then
  printf 'Local Entra secret file is tracked by Git.\n' >&2
  exit 1
fi

rendered_json="$(mktemp)"
trap 'rm -f "${rendered_json}"' EXIT
docker compose --project-directory "${REPOSITORY_ROOT}" --env-file "${BASE_ENV_FILE}" --env-file "${ENTRA_ENV_FILE}" config --quiet
docker compose --project-directory "${REPOSITORY_ROOT}" --env-file "${BASE_ENV_FILE}" --env-file "${ENTRA_ENV_FILE}" config --format json >"${rendered_json}"

python3 - "${rendered_json}" <<'PY'
import json
import sys

services = json.load(open(sys.argv[1], encoding="utf-8"))["services"]
assert not any("authentik" in name.lower() for name in services)
backend = services["backend"]
assert backend["command"] == ["/app/docker-entrypoint-dev.sh"]
assert backend["environment"]["PUBLIC_ORIGIN"] == "https://app.localhost"
assert backend["environment"]["APP_ALLOWED_ORIGIN"] == "https://app.localhost"
assert backend["environment"]["SESSION_COOKIE_SECURE"] == "true"
assert backend["environment"]["OIDC_REQUIRE_VERIFIED_EMAIL"] == "false"
assert backend["environment"]["TRUSTED_CADDY_PEER_CIDRS"] == "172.28.59.2/32"
caddy = services["local-caddy"]
assert caddy["ports"] == [{"mode": "ingress", "target": 443, "published": "443", "protocol": "tcp", "host_ip": "127.0.0.1"}]
assert all("ca.key" not in mount["source"] for mount in caddy["volumes"])
assert not backend.get("ports")
assert not services["frontend"].get("ports")
assert not services["prediction-worker"].get("ports")
PY

grep -Fq 'wss://app.localhost' "${REPOSITORY_ROOT}/local/Caddyfile"
grep -Fq 'request>headers>X-Csrf-Token replace REDACTED' "${REPOSITORY_ROOT}/local/Caddyfile"
grep -Fq 'replace session_state REDACTED' "${REPOSITORY_ROOT}/local/Caddyfile"
grep -Fq 'clientPort: 443' "${REPOSITORY_ROOT}/frontend/vite.config.ts"
printf 'Local Caddy/direct-Entra Compose, TLS mount, proxy, and loopback checks passed.\n'
