#!/usr/bin/env bash
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly AUTHENTIK_ENV_FILE="${1:-${REPOSITORY_ROOT}/.env.authentik.local}"
readonly BASE_ENV_FILE="${2:-${REPOSITORY_ROOT}/.env}"

if [[ ! -f "${BASE_ENV_FILE}" ]]; then
  printf 'Missing %s; copy .env.example to .env first.\n' "${BASE_ENV_FILE}" >&2
  exit 1
fi
if [[ ! -f "${AUTHENTIK_ENV_FILE}" ]]; then
  printf 'Missing %s; run scripts/setup-local-authentik.sh first.\n' "${AUTHENTIK_ENV_FILE}" >&2
  exit 1
fi

rendered_config="$(mktemp)"
rendered_json="$(mktemp)"
trap 'rm -f "${rendered_config}" "${rendered_json}"' EXIT

docker compose \
  --project-directory "${REPOSITORY_ROOT}" \
  --env-file "${BASE_ENV_FILE}" \
  --env-file "${AUTHENTIK_ENV_FILE}" \
  config --quiet
docker compose \
  --project-directory "${REPOSITORY_ROOT}" \
  --env-file "${BASE_ENV_FILE}" \
  --env-file "${AUTHENTIK_ENV_FILE}" \
  config >"${rendered_config}"
docker compose \
  --project-directory "${REPOSITORY_ROOT}" \
  --env-file "${BASE_ENV_FILE}" \
  --env-file "${AUTHENTIK_ENV_FILE}" \
  config --format json >"${rendered_json}"

if grep -Fq '/var/run/docker.sock' "${rendered_config}"; then
  printf 'Docker socket mount found in local Compose configuration.\n' >&2
  exit 1
fi

if grep -Eiq 'authentik|auth\.localhost' \
  "${REPOSITORY_ROOT}/docker-compose.production.yml" \
  "${REPOSITORY_ROOT}/docker-compose.release.yml" \
  "${REPOSITORY_ROOT}/docker-compose.coolify.yml"; then
  printf 'Authentik reference found in a production/release manifest.\n' >&2
  exit 1
fi

relative_env_file="${AUTHENTIK_ENV_FILE}"
if [[ "${AUTHENTIK_ENV_FILE}" == "${REPOSITORY_ROOT}/"* ]]; then
  relative_env_file="${AUTHENTIK_ENV_FILE#"${REPOSITORY_ROOT}/"}"
fi
if git -C "${REPOSITORY_ROOT}" ls-files --error-unmatch "${relative_env_file}" \
  >/dev/null 2>&1; then
  printf 'Local Authentik secret file is tracked by Git.\n' >&2
  exit 1
fi

python3 - "${rendered_json}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    services = json.load(source)["services"]

server = services["authentik-server"]
assert server["image"] == (
    "ghcr.io/goauthentik/server:2026.5.6@"
    "sha256:ed120caf710ccf82ef0026f0bc74e51615bc95ebff228a7a2d6fc60c441c3868"
)
assert not server.get("ports")
tls = services["authentik-tls"]
assert tls["image"] == (
    "docker.io/library/caddy:2.11.4-alpine@"
    "sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648"
)
assert tls["ports"] == [
    {
        "mode": "ingress",
        "target": 9443,
        "published": "9443",
        "protocol": "tcp",
        "host_ip": "127.0.0.1",
    }
]
assert services["authentik-tls"]["networks"]["default"]["aliases"] == [
    "auth.localhost"
]
assert all("ca.key" not in mount["source"] for mount in tls["volumes"])
assert not services["authentik-database"].get("ports")
assert services["backend"]["environment"]["PUBLIC_ORIGIN"] == (
    "http://app.localhost:5173"
)
assert services["backend"]["environment"]["OIDC_ISSUER"] == (
    "https://auth.localhost:9443/application/o/schatten/"
)
assert services["backend"]["environment"]["SSL_CERT_FILE"] == (
    "/etc/ssl/certs/ca-certificates.crt"
)
assert services["backend"]["depends_on"]["authentik-tls"]["condition"] == (
    "service_healthy"
)
assert services["backend"]["depends_on"]["authentik-worker"]["condition"] == (
    "service_started"
)
assert "@database:5432/" in services["backend"]["environment"]["DATABASE_URL"]
assert "SCHATTEN_OIDC_CLIENT_SECRET" not in server["environment"]
assert "AUTHENTIK_BOOTSTRAP_PASSWORD_HASH" not in server["environment"]
PY

printf 'Local Authentik Compose, layered env, dependency, loopback, issuer, image, secret and production-manifest checks passed.\n'
