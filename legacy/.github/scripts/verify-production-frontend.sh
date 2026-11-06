#!/usr/bin/env bash

set -euo pipefail

: "${FRONTEND_IMAGE:?Set FRONTEND_IMAGE to the locally built frontend image}"

python_image="${PYTHON_IMAGE:-python:3.12-slim}"

if [[ "$(docker image inspect --format '{{.Config.User}}' "${FRONTEND_IMAGE}")" != "10001:10001" ]]; then
  echo "Production frontend image is not configured for numeric user 10001:10001." >&2
  exit 1
fi

for invalid_origin in \
  'https://*.example.test' \
  'https://app.example.test evil.example.test' \
  'https://APP.Example.Test' \
  'https://0x7f000001' \
  'https://app.example.test:443' \
  'https://app.example.test:8443'; do
  if docker run --rm \
    --env "PUBLIC_ORIGIN=${invalid_origin}" \
    "${FRONTEND_IMAGE}" \
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile \
    >/dev/null 2>&1; then
    echo "Production frontend accepted invalid PUBLIC_ORIGIN: ${invalid_origin}" >&2
    exit 1
  fi
done
if docker run --rm --env PUBLIC_ORIGIN=https://app.example.test --env CADDY_TLS_MODE=off \
  "${FRONTEND_IMAGE}" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  echo "Production frontend accepted an unsupported CADDY_TLS_MODE." >&2
  exit 1
fi
for mode in acme internal; do
  docker run --rm --env PUBLIC_ORIGIN=https://app.example.test --env "CADDY_TLS_MODE=${mode}" \
    "${FRONTEND_IMAGE}" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
done

run_id="${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
network_name="task059g-frontend-${run_id}"
backend_name="task059g-backend-${run_id}"
frontend_name="task059g-frontend-${run_id}"
volume_name="task059g-caddy-data-${run_id}"

cleanup() {
  docker rm --force "${frontend_name}" "${backend_name}" >/dev/null 2>&1 || true
  docker network rm "${network_name}" >/dev/null 2>&1 || true
  docker volume rm "${volume_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "${network_name}" >/dev/null

docker run --detach --rm \
  --name "${backend_name}" \
  --network "${network_name}" \
  --network-alias backend \
  --volume "${PWD}/.github/scripts/mock-production-backend.py:/tmp/mock-production-backend.py:ro" \
  --entrypoint python \
  "${python_image}" \
  /tmp/mock-production-backend.py >/dev/null

# Same effective hardening as docker-compose.production.yml; the internal
# issuer replaces public ACME for this offline check.
docker run --detach \
  --name "${frontend_name}" \
  --network "${network_name}" \
  --network-alias app.example.test \
  --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --sysctl net.ipv4.ip_unprivileged_port_start=80 \
  --tmpfs /config:uid=10001,gid=10001,mode=0700 --tmpfs /tmp:uid=10001,gid=10001,mode=0700 \
  --volume "${volume_name}:/data" \
  --env PUBLIC_ORIGIN=https://app.example.test \
  --env CADDY_TLS_MODE=internal \
  "${FRONTEND_IMAGE}" >/dev/null

for attempt in $(seq 1 30); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "${frontend_name}")"
  if [[ "${health}" == "healthy" ]]; then
    break
  fi
  if [[ "${health}" == "unhealthy" || "${attempt}" == "30" ]]; then
    docker inspect "${frontend_name}"
    docker logs "${frontend_name}"
    echo "Production frontend did not become healthy." >&2
    exit 1
  fi
  sleep 1
done

docker run --rm \
  --network "${network_name}" \
  --volume "${PWD}/.github/scripts/verify-production-frontend-client.py:/tmp/verify-production-frontend-client.py:ro" \
  --entrypoint python \
  "${python_image}" \
  /tmp/verify-production-frontend-client.py

logs="$(docker logs "${frontend_name}" 2>&1)"
for secret in secret-code secret-state secret-error secret-description \
  secret-session-state credential-secret credential-cookie csrf-header-secret \
  request-secret return-secret location-secret token-secret access-secret \
  refresh-secret verifier-secret; do
  if grep --fixed-strings --quiet "${secret}" <<<"${logs}"; then
    echo "Caddy access logs exposed ${secret}." >&2
    exit 1
  fi
done
for header in X-Csrf-Token Authorization Location; do
  if ! grep --fixed-strings --quiet "\"${header}\":\"REDACTED\"" <<<"${logs}"; then
    echo "Caddy access logs did not retain the redacted ${header} header marker." >&2
    exit 1
  fi
done
for expected in 'code=REDACTED' 'state=REDACTED' 'error=REDACTED' \
  'error_description=REDACTED' 'session_state=REDACTED' 'request=REDACTED' \
  'return_to=REDACTED' 'token=REDACTED' 'access_token=REDACTED' \
  'refresh_token=REDACTED' 'code_verifier=REDACTED' 'visible=kept'; do
  # Anchor on the separator so state= cannot match inside session_state=.
  if ! grep --extended-regexp --quiet "[?&]${expected}" <<<"${logs}"; then
    echo "Caddy access logs did not preserve the expected redacted URI metadata: ${expected}" >&2
    exit 1
  fi
done

echo "Production frontend non-root TLS, redirect, host, forwarded-header, SPA, health, header and log boundaries passed."
