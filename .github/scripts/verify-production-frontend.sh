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
    --env CADDY_TRUSTED_PROXY_CIDRS=172.29.0.0/24 \
    "${FRONTEND_IMAGE}" \
    caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile \
    >/dev/null 2>&1; then
    echo "Production frontend accepted invalid PUBLIC_ORIGIN: ${invalid_origin}" >&2
    exit 1
  fi
done

run_id="${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
backend_network_name="task039g-backend-${run_id}"
edge_network_name="task039g-edge-${run_id}"
untrusted_network_name="task039g-untrusted-${run_id}"
backend_name="task039g-backend-${run_id}"
frontend_name="task039g-frontend-${run_id}"

cleanup() {
  docker rm --force "${frontend_name}" "${backend_name}" >/dev/null 2>&1 || true
  docker network rm "${backend_network_name}" "${edge_network_name}" \
    "${untrusted_network_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "${backend_network_name}" >/dev/null
docker network create "${edge_network_name}" >/dev/null
docker network create "${untrusted_network_name}" >/dev/null
edge_network_cidr="$(docker network inspect --format '{{(index .IPAM.Config 0).Subnet}}' "${edge_network_name}")"

docker run --detach --rm \
  --name "${backend_name}" \
  --network "${backend_network_name}" \
  --network-alias backend \
  --volume "${PWD}/.github/scripts/mock-production-backend.py:/tmp/mock-production-backend.py:ro" \
  --entrypoint python \
  "${python_image}" \
  /tmp/mock-production-backend.py >/dev/null

docker run --detach --rm \
  --name "${frontend_name}" \
  --network "${backend_network_name}" \
  --network-alias frontend \
  --env PUBLIC_ORIGIN=https://app.example.test \
  --env "CADDY_TRUSTED_PROXY_CIDRS=${edge_network_cidr}" \
  "${FRONTEND_IMAGE}" >/dev/null

docker network connect --alias frontend "${edge_network_name}" "${frontend_name}"
docker network connect --alias frontend "${untrusted_network_name}" "${frontend_name}"

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
  --network "${edge_network_name}" \
  --env PROXY_TEST_MODE=trusted \
  --volume "${PWD}/.github/scripts/verify-production-frontend-client.py:/tmp/verify-production-frontend-client.py:ro" \
  --entrypoint python \
  "${python_image}" \
  /tmp/verify-production-frontend-client.py

docker run --rm \
  --network "${untrusted_network_name}" \
  --env PROXY_TEST_MODE=untrusted \
  --volume "${PWD}/.github/scripts/verify-production-frontend-client.py:/tmp/verify-production-frontend-client.py:ro" \
  --entrypoint python \
  "${python_image}" \
  /tmp/verify-production-frontend-client.py

logs="$(docker logs "${frontend_name}" 2>&1)"
for secret in secret-code secret-state secret-error secret-description \
  credential-secret credential-cookie csrf-header-secret; do
  if grep --fixed-strings --quiet "${secret}" <<<"${logs}"; then
    echo "Caddy access logs exposed ${secret}." >&2
    exit 1
  fi
done
if ! grep --fixed-strings --quiet '"X-Csrf-Token":"REDACTED"' <<<"${logs}"; then
  echo "Caddy access logs did not retain the redacted CSRF header marker." >&2
  exit 1
fi
for expected in 'code=REDACTED' 'state=REDACTED' 'error=REDACTED' \
  'error_description=REDACTED' 'visible=kept'; do
  if ! grep --fixed-strings --quiet "${expected}" <<<"${logs}"; then
    echo "Caddy access logs did not preserve the expected redacted URI metadata: ${expected}" >&2
    exit 1
  fi
done

echo "Production frontend host, proxy, SPA, health, header and log boundaries passed."
