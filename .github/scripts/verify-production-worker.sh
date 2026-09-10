#!/usr/bin/env bash

set -euo pipefail

: "${BACKEND_IMAGE:?Set BACKEND_IMAGE to the locally built release image}"
: "${DATABASE_URL:?Set DATABASE_URL to a migrated disposable PostgreSQL database}"

run_id="${GITHUB_RUN_ID:-$$}-${GITHUB_RUN_ATTEMPT:-1}"
worker_name="task057e-worker-${run_id}"
duplicate_name="task057e-worker-duplicate-${run_id}"

cleanup() {
  docker rm --force "${duplicate_name}" "${worker_name}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [[ "$(docker image inspect --format '{{.Config.User}}' "${BACKEND_IMAGE}")" != "10001:10001" ]]; then
  echo "Production backend/worker image is not configured for numeric user 10001:10001." >&2
  exit 1
fi

set +e
docker run --rm --network host \
  --env DATABASE_URL \
  "${BACKEND_IMAGE}" \
  python -m app.api.v1.predictions.worker health-check >/dev/null 2>&1
initial_health_status=$?
set -e
if [[ "${initial_health_status}" == "0" ]]; then
  echo "Worker health check reported healthy without a lock-owning worker." >&2
  exit 1
fi

docker run --detach \
  --name "${worker_name}" \
  --network host \
  --env DATABASE_URL \
  --init \
  --restart unless-stopped \
  --stop-timeout 10 \
  --health-cmd 'python -m app.api.v1.predictions.worker health-check' \
  --health-interval 1s \
  --health-timeout 3s \
  --health-retries 5 \
  --health-start-period 3s \
  "${BACKEND_IMAGE}" \
  python -m app.api.v1.predictions.worker >/dev/null

for attempt in $(seq 1 30); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "${worker_name}")"
  if [[ "${health}" == "healthy" ]]; then
    break
  fi
  if [[ "${health}" == "unhealthy" || "${attempt}" == "30" ]]; then
    docker inspect --format \
      'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}} restarts={{.RestartCount}}' \
      "${worker_name}"
    docker logs "${worker_name}"
    echo "Production prediction worker did not become healthy." >&2
    exit 1
  fi
  sleep 1
done

docker inspect "${worker_name}" | python3 -c '
import json
import sys

container = json.load(sys.stdin)[0]
assert container["Config"]["User"] == "10001:10001"
assert container["Config"]["Cmd"] == [
    "python", "-m", "app.api.v1.predictions.worker"
]
assert container["Config"]["Healthcheck"]["Test"] == [
    "CMD-SHELL", "python -m app.api.v1.predictions.worker health-check"
]
assert container["HostConfig"]["Init"] is True
assert container["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
assert container["Config"]["StopTimeout"] == 10
assert container["HostConfig"]["PortBindings"] == {}
environment_names = {item.split("=", 1)[0] for item in container["Config"]["Env"]}
assert "DATABASE_URL" in environment_names
assert not environment_names.intersection({
    "OIDC_DISCOVERY_URL",
    "OIDC_ISSUER",
    "OIDC_CLIENT_ID",
    "OIDC_CLIENT_SECRET",
    "PUBLIC_ORIGIN",
    "APP_ALLOWED_ORIGIN",
    "SESSION_COOKIE_SECURE",
})
'

set +e
docker run --name "${duplicate_name}" --network host \
  --env DATABASE_URL \
  "${BACKEND_IMAGE}" \
  python -m app.api.v1.predictions.worker >/dev/null 2>&1
duplicate_status=$?
set -e
if [[ "${duplicate_status}" == "0" ]]; then
  echo "A duplicate production worker unexpectedly acquired calculation ownership." >&2
  exit 1
fi
if ! docker logs "${duplicate_name}" 2>&1 \
  | grep --fixed-strings --quiet 'Prediction worker lock is already owned'; then
  echo "Duplicate worker did not emit the expected safe ownership log." >&2
  exit 1
fi

sleep 11
docker exec "${worker_name}" \
  python -c 'import os, signal; current=os.getpid(); candidates=((int(path), open(f"/proc/{path}/cmdline", "rb").read()) for path in os.listdir("/proc") if path.isdigit() and int(path) not in {1, current}); pid=next(pid for pid, command in candidates if b"app.api.v1.predictions.worker" in command and b"health-check" not in command); os.kill(pid, signal.SIGKILL)' >/dev/null
for attempt in $(seq 1 30); do
  restart_count="$(docker inspect --format '{{.RestartCount}}' "${worker_name}")"
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}}' "${worker_name}")"
  if (( restart_count >= 1 )) && [[ "${health}" == "healthy" ]]; then
    break
  fi
  if [[ "${attempt}" == "30" ]]; then
    docker inspect --format \
      'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}missing{{end}} restarts={{.RestartCount}}' \
      "${worker_name}"
    docker logs "${worker_name}"
    echo "Production prediction worker did not restart and reacquire healthy ownership." >&2
    exit 1
  fi
  sleep 1
done

logs="$(docker logs "${worker_name}" 2>&1)"
for forbidden in DATABASE_URL OIDC_CLIENT_SECRET input_snapshot test-secret; do
  if grep --fixed-strings --quiet "${forbidden}" <<<"${logs}"; then
    echo "Prediction worker lifecycle logs exposed forbidden configuration or snapshot data." >&2
    exit 1
  fi
done
for expected in 'Prediction worker acquired global ownership' \
  'Recovered abandoned active prediction requests'; do
  if ! grep --fixed-strings --quiet "${expected}" <<<"${logs}"; then
    echo "Prediction worker lifecycle logs omitted: ${expected}" >&2
    exit 1
  fi
done

docker stop --time 10 "${worker_name}" >/dev/null

echo "Production prediction worker non-root startup, health, isolation, exclusivity, restart, shutdown and safe-log checks passed."
