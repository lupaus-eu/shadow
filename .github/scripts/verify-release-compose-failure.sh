#!/usr/bin/env bash

set -euo pipefail

: "${BACKEND_IMAGE:?Set BACKEND_IMAGE to the locally built release image}"

export FRONTEND_IMAGE="${BACKEND_IMAGE}"
export OIDC_DISCOVERY_URL="https://login.microsoftonline.com/tenant-id/v2.0/.well-known/openid-configuration"
export OIDC_ISSUER="https://login.microsoftonline.com/tenant-id/v2.0"
export OIDC_CLIENT_ID="test-client"
export OIDC_CLIENT_SECRET="test-secret"
export PUBLIC_ORIGIN="https://app.example.test"
export TRUSTED_CADDY_PEER_CIDRS="172.30.0.0/24"
export CADDY_TRUSTED_PROXY_CIDRS="172.29.0.0/24"

gate_run_id="${GITHUB_RUN_ID:-$$}"
gate_run_attempt="${GITHUB_RUN_ATTEMPT:-1}"
gate_project="task038-gate-${gate_run_id}-${gate_run_attempt}"
gate_network="${gate_project}_default"
gate_database_container="${gate_project}-database"
export DATABASE_URL="postgresql://postgres:postgres@${gate_database_container}:5432/schatten_gate"

cleanup() {
  docker compose \
    --project-name "${gate_project}" \
    --file docker-compose.production.yml \
    down --remove-orphans >/dev/null 2>&1 || true
  docker rm --force "${gate_database_container}" >/dev/null 2>&1 || true
  docker network rm "${gate_network}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create \
  --label "com.docker.compose.project=${gate_project}" \
  --label "com.docker.compose.network=default" \
  "${gate_network}" >/dev/null

docker run --detach --rm \
  --name "${gate_database_container}" \
  --network "${gate_network}" \
  --env POSTGRES_DB=schatten_gate \
  --env POSTGRES_USER=postgres \
  --env POSTGRES_PASSWORD=postgres \
  --health-cmd "pg_isready --username postgres --dbname schatten_gate" \
  --health-interval 1s \
  --health-timeout 5s \
  --health-retries 30 \
  postgres:18.0 >/dev/null

for attempt in $(seq 1 30); do
  if [[ "$(docker inspect --format '{{.State.Health.Status}}' "${gate_database_container}")" == "healthy" ]]; then
    break
  fi
  if [[ "${attempt}" == "30" ]]; then
    docker logs "${gate_database_container}"
    echo "Disposable PostgreSQL did not become healthy." >&2
    exit 1
  fi
  sleep 1
done

docker run --rm \
  --network "${gate_network}" \
  --env DATABASE_URL \
  "${BACKEND_IMAGE}" python migrate.py up

docker exec "${gate_database_container}" \
  psql --username postgres --dbname schatten_gate \
  --command "UPDATE schema_migrations SET checksum = repeat('0', 64) WHERE version = 1;" \
  >/dev/null

set +e
docker compose \
  --project-name "${gate_project}" \
  --file docker-compose.production.yml \
  up --no-build --pull never --abort-on-container-exit --exit-code-from migration
set -e

migration_container="$({
  docker compose \
    --project-name "${gate_project}" \
    --file docker-compose.production.yml \
    ps --all --quiet migration
} 2>/dev/null)"

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
  service_container="$({
    docker compose \
      --project-name "${gate_project}" \
      --file docker-compose.production.yml \
      ps --all --quiet "${service}"
  } 2>/dev/null)"

  if [[ -n "${service_container}" ]]; then
    service_started_at="$(docker inspect --format '{{.State.StartedAt}}' "${service_container}")"
    service_running="$(docker inspect --format '{{.State.Running}}' "${service_container}")"

    if [[ "${service_started_at}" != "0001-01-01T00:00:00Z" || "${service_running}" != "false" ]]; then
      echo "${service} started even though the migration service failed." >&2
      docker compose \
        --project-name "${gate_project}" \
        --file docker-compose.production.yml \
        ps --all
      exit 1
    fi
  fi
done

echo "Migration failure returned nonzero and prevented backend/prediction-worker/frontend startup."
