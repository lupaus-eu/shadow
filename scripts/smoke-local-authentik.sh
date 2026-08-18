#!/usr/bin/env bash
set -euo pipefail

readonly DISCOVERY_URL="http://auth.localhost:9000/application/o/schatten/.well-known/openid-configuration"
readonly EXPECTED_ISSUER="http://auth.localhost:9000/application/o/schatten/"

command -v curl >/dev/null || {
  printf 'curl is required\n' >&2
  exit 1
}
command -v python3 >/dev/null || {
  printf 'python3 is required\n' >&2
  exit 1
}

discovery_file="$(mktemp)"
jwks_file="$(mktemp)"
trap 'rm -f "${discovery_file}" "${jwks_file}"' EXIT

for attempt in $(seq 1 60); do
  if curl --fail --silent --show-error "${DISCOVERY_URL}" >"${discovery_file}"; then
    break
  fi
  if [[ "${attempt}" -eq 60 ]]; then
    printf 'Authentik discovery did not become ready within five minutes.\n' >&2
    exit 1
  fi
  sleep 5
done

jwks_url="$(python3 - "${discovery_file}" "${EXPECTED_ISSUER}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    discovery = json.load(source)

assert discovery["issuer"] == sys.argv[2], (
    f"unexpected issuer: {discovery.get('issuer')!r}"
)
assert "RS256" in discovery.get("id_token_signing_alg_values_supported", []), (
    "discovery does not advertise RS256"
)
print(discovery["jwks_uri"])
PY
)"

curl --fail --silent --show-error "${jwks_url}" >"${jwks_file}"
python3 - "${jwks_file}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    jwks = json.load(source)

keys = jwks.get("keys")
assert isinstance(keys, list) and keys, "JWKS contains no signing keys"
assert any(key.get("kty") == "RSA" for key in keys), "JWKS contains no RSA key"
PY

printf 'Authentik discovery issuer and RSA JWKS smoke checks passed.\n'
