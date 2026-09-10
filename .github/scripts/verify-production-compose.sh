#!/usr/bin/env bash

set -euo pipefail

declare -A values=(
  [BACKEND_IMAGE]="schatten-backend:test-commit"
  [FRONTEND_IMAGE]="schatten-frontend:test-commit"
  [DATABASE_URL]="postgresql://user:password@database:5432/schatten"
  [OIDC_DISCOVERY_URL]="https://login.microsoftonline.com/tenant-id/v2.0/.well-known/openid-configuration"
  [OIDC_ISSUER]="https://login.microsoftonline.com/tenant-id/v2.0"
  [OIDC_CLIENT_ID]="test-client"
  [OIDC_CLIENT_SECRET]="test-secret"
  [PUBLIC_ORIGIN]="https://app.example.test"
  [TRUSTED_CADDY_PEER_CIDRS]="172.30.0.0/24"
  [CADDY_TRUSTED_PROXY_CIDRS]="172.29.0.0/24"
)

compose_env=()
for name in "${!values[@]}"; do
  compose_env+=("${name}=${values[${name}]}")
done

env -i PATH="${PATH}" "${compose_env[@]}" \
  docker compose --env-file /dev/null --file docker-compose.production.yml \
  config --format json |
  python3 -c '
import json, sys
model = json.load(sys.stdin)
services = model["services"]
assert set(services) == {"migration", "backend", "prediction-worker", "frontend"}
for service in services.values():
    assert "ports" not in service
assert services["migration"]["environment"] == {
    "DATABASE_URL": "postgresql://user:password@database:5432/schatten"
}
assert services["migration"]["image"] == services["backend"]["image"]
worker = services["prediction-worker"]
assert worker["image"] == services["backend"]["image"]
assert services["backend"]["depends_on"]["migration"]["condition"] == "service_completed_successfully"
assert worker["depends_on"]["migration"]["condition"] == "service_completed_successfully"
assert services["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"
assert worker["command"] == ["python", "-m", "app.api.v1.predictions.worker"]
assert worker["environment"] == {
    "DATABASE_URL": "postgresql://user:password@database:5432/schatten"
}
assert worker["healthcheck"]["test"] == [
    "CMD", "python", "-m", "app.api.v1.predictions.worker", "health-check"
]
assert worker["restart"] == "unless-stopped"
assert worker["init"] is True
assert worker["stop_grace_period"] == "10s"
assert services["backend"]["environment"]["APP_ENV"] == "production"
assert services["backend"]["environment"]["PUBLIC_ORIGIN"] == "https://app.example.test"
assert services["frontend"]["environment"]["PUBLIC_ORIGIN"] == "https://app.example.test"
assert "PUBLIC_HOST" not in services["frontend"]["environment"]
assert services["backend"]["environment"]["SESSION_COOKIE_SECURE"] == "true"
assert services["backend"]["environment"]["OIDC_SCOPES"] == "openid profile email"
assert all("authentik" not in name.lower() for name in services)
'

for missing_name in "${!values[@]}"; do
  missing_env=()
  for name in "${!values[@]}"; do
    if [[ "${name}" != "${missing_name}" ]]; then
      missing_env+=("${name}=${values[${name}]}")
    fi
  done
  if env -i PATH="${PATH}" "${missing_env[@]}" \
    docker compose --env-file /dev/null --file docker-compose.production.yml \
    config --quiet >/dev/null 2>&1; then
    echo "Production Compose accepted missing ${missing_name}." >&2
    exit 1
  fi
done

echo "Production Compose requires every release, auth and proxy setting and preserves API/worker isolation and migration gates."
