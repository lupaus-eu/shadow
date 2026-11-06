#!/usr/bin/env bash

set -euo pipefail

declare -A values=(
  [BACKEND_IMAGE]="sha256:1111111111111111111111111111111111111111111111111111111111111111"
  [FRONTEND_IMAGE]="sha256:2222222222222222222222222222222222222222222222222222222222222222"
  [POSTGRES_DB]="shadow"
  [POSTGRES_USER]="shadow"
  [POSTGRES_PASSWORD]="password"
  [DATABASE_URL]="postgresql://shadow:password@database:5432/shadow"
  [OIDC_DISCOVERY_URL]="https://login.microsoftonline.com/tenant-id/v2.0/.well-known/openid-configuration"
  [OIDC_ISSUER]="https://login.microsoftonline.com/tenant-id/v2.0"
  [OIDC_CLIENT_ID]="test-client"
  [OIDC_CLIENT_SECRET]="test-secret"
  [PUBLIC_ORIGIN]="https://app.example.test"
  [DOCKER_SOCKET_GID]="988"
  [SHADOW_BACKUP_PUBLIC_KEY]="/opt/apps/shadow-config/backup-public-key.asc"
)

compose_env=()
for name in "${!values[@]}"; do
  compose_env+=("${name}=${values[${name}]}")
done

render() {
  env -i PATH="${PATH}" "$@" \
    docker compose --env-file /dev/null --file docker-compose.production.yml \
    --profile ops --profile scheduler config --format json
}

render "${compose_env[@]}" | python3 -c '
import json, sys
model = json.load(sys.stdin)
services = model["services"]
assert set(services) == {
    "database", "migration", "backend", "prediction-worker", "frontend",
    "ofelia", "backup-runner", "cleanup-runner",
}, set(services)
secrets = {"DATABASE_URL", "POSTGRES_PASSWORD", "OIDC_CLIENT_SECRET"}
for name, service in services.items():
    assert "build" not in service, name
    assert service.get("read_only") is True, name
    assert service.get("cap_drop") == ["ALL"], name
    assert "no-new-privileges:true" in service.get("security_opt", []), name
    assert not service.get("privileged"), name
    assert not service.get("cap_add"), name
    for field in ("pid", "ipc", "userns_mode"):
        assert service.get(field) != "host", (name, field)
    assert service.get("network_mode") != "host", name
    if name != "frontend":
        assert "ports" not in service, name
    socket_mounts = [
        volume for volume in service.get("volumes", [])
        if volume["target"] == "/var/run/docker.sock"
    ]
    assert bool(socket_mounts) == (name in {"ofelia", "cleanup-runner"}), name
    assert all(volume["source"] != "/" for volume in service.get("volumes", [])), name
    assert service.get("labels", {}).get("eu.lupaus.shadow.retain") == "true", name

ports = {(port["target"], port["published"], port["protocol"]) for port in services["frontend"]["ports"]}
assert ports == {(80, "80", "tcp"), (443, "443", "tcp")}, ports

backend_id = "sha256:" + "1" * 64
for name in ("migration", "backend", "prediction-worker"):
    assert services[name]["image"] == backend_id, name
    assert services[name]["pull_policy"] == "never", name
assert services["frontend"]["image"] == "sha256:" + "2" * 64
for name in ("database", "ofelia", "backup-runner", "cleanup-runner"):
    assert "@sha256:" in services[name]["image"], name

database = services["database"]
assert database["image"].startswith("docker.io/library/postgres:18.")
assert database["networks"] == {"data": None}
assert [v["target"] for v in database["volumes"]] == ["/var/lib/postgresql"]
assert database["volumes"][0]["source"] == "postgres_data"
assert model["networks"]["data"]["internal"] is True

assert services["migration"]["environment"] == {"DATABASE_URL": "postgresql://shadow:password@database:5432/shadow"}
assert services["migration"]["depends_on"]["database"]["condition"] == "service_healthy"
assert services["migration"]["networks"] == {"data": None}
for name in ("backend", "prediction-worker"):
    assert services[name]["depends_on"]["migration"]["condition"] == "service_completed_successfully", name
assert services["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"

backend = services["backend"]
assert set(backend["networks"]) == {"edge", "data"}
assert backend["environment"]["APP_ENV"] == "production"
assert backend["environment"]["PUBLIC_ORIGIN"] == "https://app.example.test"
assert backend["environment"]["APP_ALLOWED_ORIGIN"] == "https://app.example.test"
assert backend["environment"]["SESSION_COOKIE_SECURE"] == "true"
assert backend["environment"]["OIDC_SCOPES"] == "openid profile email"
assert backend["environment"]["OIDC_REQUIRE_VERIFIED_EMAIL"] == "false"
# ADR-015: MCP and its change-set review stay off unless the protected env
# file switches them on (TASK-069P); the client cap defaults to 10000.
assert backend["environment"]["MCP_ENABLED"] == "false"
assert backend["environment"]["MCP_CHANGE_SET_REVIEW_ENABLED"] == "false"
assert backend["environment"]["MCP_OAUTH_MAX_CLIENTS"] == "10000"
caddy_ip = services["frontend"]["networks"]["edge"]["ipv4_address"]
assert backend["environment"]["TRUSTED_CADDY_PEER_CIDRS"] == f"{caddy_ip}/32"
import ipaddress
edge = model["networks"]["edge"]["ipam"]["config"][0]
assert ipaddress.ip_address(caddy_ip) in ipaddress.ip_network(edge["subnet"])
assert ipaddress.ip_address(caddy_ip) not in ipaddress.ip_network(edge["ip_range"])

worker = services["prediction-worker"]
assert worker["command"] == ["python", "-m", "app.api.v1.predictions.worker"]
assert worker["environment"] == {
    "DATABASE_URL": "postgresql://shadow:password@database:5432/shadow",
    "DATABASE_POOL_SIZE": "5",
    "DATABASE_MAX_OVERFLOW": "10",
}
assert worker["networks"] == {"data": None}
assert worker["healthcheck"]["test"] == ["CMD", "python", "-m", "app.api.v1.predictions.worker", "health-check"]
assert {key: worker["healthcheck"][key] for key in ("interval", "timeout", "retries", "start_period")} == {
    "interval": "10s", "timeout": "10s", "retries": 5, "start_period": "30s",
}, worker["healthcheck"]
assert worker["restart"] == "unless-stopped"
assert worker["init"] is True
assert worker["stop_grace_period"] == "10s"
assert "deploy" not in worker or worker["deploy"].get("replicas", 1) == 1

frontend = services["frontend"]
assert frontend["environment"] == {"PUBLIC_ORIGIN": "https://app.example.test", "CADDY_TLS_MODE": "acme"}
assert frontend["sysctls"] == {"net.ipv4.ip_unprivileged_port_start": "80"}
assert [(v["source"], v["target"]) for v in frontend["volumes"]] == [("caddy_data", "/data")]
assert set(frontend["networks"]) == {"edge"}
for name in ("database", "backend", "prediction-worker", "frontend", "ofelia"):
    assert services[name]["restart"] == "unless-stopped", name
for name in ("migration", "backup-runner", "cleanup-runner"):
    assert services[name]["restart"] == "no", name

ofelia = services["ofelia"]
assert ofelia["profiles"] == ["scheduler"]
assert ofelia["network_mode"] == "none"
assert ofelia["user"] == "65534:988"
assert "--docker" not in ofelia["command"] and "-d" not in ofelia["command"]
assert "environment" not in ofelia or not set(ofelia["environment"]) & secrets
assert ofelia["environment"]["TZ"] == "Europe/Helsinki"
config = [v for v in ofelia["volumes"] if v["target"] == "/etc/ofelia/config.ini"]
assert len(config) == 1 and config[0]["read_only"] is True
assert len(ofelia["volumes"]) == 2

backup = services["backup-runner"]
assert backup["profiles"] == ["ops"]
assert backup["container_name"] == "shadow-backup-runner"
assert backup["networks"] == {"data": None}
assert set(backup["environment"]) & secrets == {"DATABASE_URL"}
assert backup["environment"]["BACKUP_RETENTION_DAYS"] == "7"
mounts = {v["target"]: v for v in backup["volumes"]}
assert set(mounts) == {"/opt/shadow-ops", "/backups", "/run/shadow/backup-public-key.asc", "/locks"}
assert mounts["/backups"]["source"] == "/opt/postgres-backups"
assert not mounts["/backups"].get("read_only")
for target in ("/opt/shadow-ops", "/run/shadow/backup-public-key.asc", "/locks"):
    assert mounts[target]["read_only"] is True, target
# Long-syntax binds default to create_host_path=false; some Compose versions
# omit the false value from rendered JSON, so only an explicit true fails.
assert all(v.get("bind", {}).get("create_host_path", False) is False for v in backup["volumes"])

cleanup = services["cleanup-runner"]
assert cleanup["profiles"] == ["ops"]
assert cleanup["container_name"] == "shadow-docker-cleanup"
assert cleanup["network_mode"] == "none"
assert cleanup["user"] == "65534:988"
assert not set(cleanup["environment"]) & secrets
for volume in cleanup["volumes"]:
    if volume["target"] != "/var/run/docker.sock":
        assert volume["read_only"] is True, volume["target"]

# ADR-019: the platform worker is defined but stays behind the "worker" profile
# until the production runtime adopts it, so no deploy tooling starts it yet.
assert "worker" not in services
assert set(model["volumes"]) == {"postgres_data", "caddy_data"}
text = json.dumps(model).lower()
for retired in ("coolify", "traefik", "authentik", "caddy_trusted_proxy"):
    assert retired not in text, retired
'

for missing_name in "${!values[@]}"; do
  missing_env=()
  for name in "${!values[@]}"; do
    if [[ "${name}" != "${missing_name}" ]]; then
      missing_env+=("${name}=${values[${name}]}")
    fi
  done
  if render "${missing_env[@]}" >/dev/null 2>&1; then
    echo "Production Compose accepted missing ${missing_name}." >&2
    exit 1
  fi
done

# The MCP switches and cap come only from the env file, with safe defaults;
# a literal value would bypass deploy-release's --mcp-approval gate.
for line in 'MCP_ENABLED: ${MCP_ENABLED:-false}' \
  'MCP_CHANGE_SET_REVIEW_ENABLED: ${MCP_CHANGE_SET_REVIEW_ENABLED:-false}' \
  'MCP_OAUTH_MAX_CLIENTS: ${MCP_OAUTH_MAX_CLIENTS:-10000}'; do
  grep -qxF "      ${line}" docker-compose.production.yml \
    || { echo "Production Compose must set ${line}" >&2; exit 1; }
done
render "${compose_env[@]}" MCP_ENABLED=true MCP_CHANGE_SET_REVIEW_ENABLED=true MCP_OAUTH_MAX_CLIENTS=20000 \
  | python3 -c '
import json, sys
environment = json.load(sys.stdin)["services"]["backend"]["environment"]
assert environment["MCP_ENABLED"] == "true"
assert environment["MCP_CHANGE_SET_REVIEW_ENABLED"] == "true"
assert environment["MCP_OAUTH_MAX_CLIENTS"] == "20000"
'

# The platform worker (profile "worker"): same image and hardening as the
# prediction worker, its own entry point, and no ports or secrets beyond the
# database URL. It is absent from the default render checked above.
env -i PATH="${PATH}" "${compose_env[@]}" \
  docker compose --env-file /dev/null --file docker-compose.production.yml \
  --profile worker config --format json | python3 -c '
import json, sys
services = json.load(sys.stdin)["services"]
worker = services["worker"]
assert worker["profiles"] == ["worker"]
assert worker["image"] == "sha256:" + "1" * 64 and worker["pull_policy"] == "never"
assert worker["command"] == ["python", "-m", "app.platform.worker"]
assert worker["environment"] == {
    "DATABASE_URL": "postgresql://shadow:password@database:5432/shadow",
    "DATABASE_POOL_SIZE": "5",
    "DATABASE_MAX_OVERFLOW": "10",
    "WORKER_SCHEDULE_INTERVAL_SECONDS": "3600",
    "QUEUE_CLAIM_TIMEOUT_SECONDS": "900",
}
assert worker["networks"] == {"data": None}
assert worker["healthcheck"]["test"] == ["CMD", "python", "-m", "app.platform.worker", "health-check"]
assert worker["read_only"] is True and worker["cap_drop"] == ["ALL"]
assert worker["security_opt"] == ["no-new-privileges:true"] and worker.get("privileged", False) is False
assert worker["labels"] == {"eu.lupaus.shadow.retain": "true"}
assert [volume["target"] for volume in worker.get("volumes", [])] == []
assert worker["tmpfs"] == ["/tmp:size=16m"], worker.get("tmpfs")
assert {key: worker["healthcheck"][key] for key in ("interval", "timeout", "retries", "start_period")} == {
    "interval": "10s", "timeout": "10s", "retries": 5, "start_period": "30s",
}
assert worker["stop_grace_period"] == "20s"
assert worker["restart"] == "unless-stopped" and worker["init"] is True
assert worker["depends_on"]["migration"]["condition"] == "service_completed_successfully"
assert not worker.get("ports")
'

echo "Production Compose requires every release, database, auth and scheduler setting and preserves private ports, hardening, isolation and migration gates; MCP stays off unless the env file switches it on."
