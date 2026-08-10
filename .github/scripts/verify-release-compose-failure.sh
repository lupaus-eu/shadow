#!/usr/bin/env bash

set -euo pipefail

: "${BACKEND_IMAGE:?Set BACKEND_IMAGE to the locally built release image}"

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
gate_status=$?
set -e

if [[ "${gate_status}" == "0" ]]; then
  echo "Production Compose unexpectedly succeeded with invalid migration history." >&2
  exit 1
fi

backend_container="$({
  docker compose \
    --project-name "${gate_project}" \
    --file docker-compose.production.yml \
    ps --all --quiet backend
} 2>/dev/null)"

if [[ -n "${backend_container}" ]]; then
  backend_started_at="$(docker inspect --format '{{.State.StartedAt}}' "${backend_container}")"
  backend_running="$(docker inspect --format '{{.State.Running}}' "${backend_container}")"

  if [[ "${backend_started_at}" != "0001-01-01T00:00:00Z" || "${backend_running}" != "false" ]]; then
    echo "Backend started even though the migration service failed." >&2
    docker compose \
      --project-name "${gate_project}" \
      --file docker-compose.production.yml \
      ps --all
    exit 1
  fi
fi

echo "Migration failure returned nonzero and prevented backend startup."
