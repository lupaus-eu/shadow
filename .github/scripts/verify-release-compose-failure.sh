#!/usr/bin/env bash

set -euo pipefail

: "${BACKEND_IMAGE:?Set BACKEND_IMAGE to the locally built release image}"

BACKEND_IMAGE="$(docker image inspect --format '{{.Id}}' "${BACKEND_IMAGE}")"
export BACKEND_IMAGE
# The frontend is never started; any local image satisfies interpolation.
export FRONTEND_IMAGE="${BACKEND_IMAGE}"
export POSTGRES_DB="shadow_gate"
export POSTGRES_USER="postgres"
export POSTGRES_PASSWORD="postgres"
export DATABASE_URL="postgresql://postgres:postgres@database:5432/shadow_gate"
export OIDC_DISCOVERY_URL="https://login.microsoftonline.com/tenant-id/v2.0/.well-known/openid-configuration"
export OIDC_ISSUER="https://login.microsoftonline.com/tenant-id/v2.0"
export OIDC_CLIENT_ID="test-client"
export OIDC_CLIENT_SECRET="test-secret"
export PUBLIC_ORIGIN="https://app.example.test"
# Interpolated for the profile-only operational services, which are not started.
export DOCKER_SOCKET_GID="0"
export SHADOW_BACKUP_PUBLIC_KEY="/nonexistent/backup-public-key.asc"
# Disposable project subnet so a concurrent development stack is unaffected.
export SHADOW_EDGE_SUBNET="172.30.158.0/24"
export SHADOW_EDGE_IP_RANGE="172.30.158.128/25"
export SHADOW_CADDY_IPV4="172.30.158.2"

gate_project="task059g-gate-${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
compose() {
  docker compose --project-name "${gate_project}" --env-file /dev/null \
    --file docker-compose.production.yml "$@"
}

cleanup() {
  # Removes only this disposable project's containers, networks and volume.
  compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

compose up --detach --wait database >/dev/null
compose run --rm --no-deps migration python migrate.py up
compose exec -T database \
  psql --username postgres --dbname shadow_gate \
  --command "UPDATE schema_migrations SET checksum = repeat('0', 64) WHERE version = 1;" \
  >/dev/null

set +e
compose up --no-build --pull never --abort-on-container-exit --exit-code-from migration \
  migration backend prediction-worker frontend
set -e

migration_container="$(compose ps --all --quiet migration 2>/dev/null)"
if [[ -z "${migration_container}" ]]; then
  echo "Production Compose did not create the migration container." >&2
  exit 1
fi

migration_status="$(docker inspect --format '{{.State.ExitCode}}' "${migration_container}")"
if [[ "${migration_status}" == "0" ]]; then
  echo "Production Compose unexpectedly succeeded with invalid migration history." >&2
  exit 1
fi

for service in backend prediction-worker frontend; do
  service_container="$(compose ps --all --quiet "${service}" 2>/dev/null)"
  if [[ -n "${service_container}" ]]; then
    service_started_at="$(docker inspect --format '{{.State.StartedAt}}' "${service_container}")"
    service_running="$(docker inspect --format '{{.State.Running}}' "${service_container}")"
    if [[ "${service_started_at}" != "0001-01-01T00:00:00Z" || "${service_running}" != "false" ]]; then
      echo "${service} started even though the migration service failed." >&2
      compose ps --all
      exit 1
    fi
  fi
done

echo "Migration failure returned nonzero and prevented backend/prediction-worker/frontend startup."
