#!/usr/bin/env bash
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly OUTPUT_DIRECTORY="${1:-${REPOSITORY_ROOT}/.local/authentik-tls}"
readonly CA_KEY="${OUTPUT_DIRECTORY}/ca.key"
readonly CA_CERTIFICATE="${OUTPUT_DIRECTORY}/ca.crt"
readonly SERVER_KEY="${OUTPUT_DIRECTORY}/auth.localhost.key"
readonly SERVER_CERTIFICATE="${OUTPUT_DIRECTORY}/auth.localhost.crt"

command -v openssl >/dev/null || {
  printf 'openssl is required\n' >&2
  exit 1
}

if [[ -e "${CA_KEY}" || -e "${CA_CERTIFICATE}" || -e "${SERVER_KEY}" || -e "${SERVER_CERTIFICATE}" ]]; then
  if [[ -r "${CA_CERTIFICATE}" && -r "${SERVER_CERTIFICATE}" && -r "${SERVER_KEY}" ]] \
    && openssl verify -CAfile "${CA_CERTIFICATE}" "${SERVER_CERTIFICATE}" >/dev/null \
    && openssl x509 -checkend 2592000 -noout -in "${SERVER_CERTIFICATE}" >/dev/null; then
    printf 'Local Authentik TLS material already exists and is valid: %s\n' "${OUTPUT_DIRECTORY}"
    exit 0
  fi
  printf 'Refusing to overwrite incomplete, invalid or expiring TLS material in %s.\n' "${OUTPUT_DIRECTORY}" >&2
  printf 'Remove that exact directory only if you intend to replace and re-trust the local CA.\n' >&2
  exit 1
fi

umask 077
mkdir -p "${OUTPUT_DIRECTORY}"
temporary_directory="$(mktemp -d)"
trap 'rm -rf "${temporary_directory}"' EXIT

openssl req \
  -x509 \
  -newkey rsa:3072 \
  -sha256 \
  -days 3650 \
  -nodes \
  -subj '/CN=Schatten Local Development CA' \
  -addext 'basicConstraints=critical,CA:TRUE' \
  -addext 'keyUsage=critical,keyCertSign,cRLSign' \
  -keyout "${CA_KEY}" \
  -out "${CA_CERTIFICATE}" >/dev/null 2>&1

openssl req \
  -newkey rsa:3072 \
  -sha256 \
  -nodes \
  -subj '/CN=auth.localhost' \
  -keyout "${SERVER_KEY}" \
  -out "${temporary_directory}/auth.localhost.csr" >/dev/null 2>&1

printf '%s\n' \
  'basicConstraints=critical,CA:FALSE' \
  'keyUsage=critical,digitalSignature,keyEncipherment' \
  'extendedKeyUsage=serverAuth' \
  'subjectAltName=DNS:auth.localhost' \
  >"${temporary_directory}/auth.localhost.ext"

openssl x509 \
  -req \
  -sha256 \
  -days 825 \
  -in "${temporary_directory}/auth.localhost.csr" \
  -CA "${CA_CERTIFICATE}" \
  -CAkey "${CA_KEY}" \
  -CAcreateserial \
  -extfile "${temporary_directory}/auth.localhost.ext" \
  -out "${SERVER_CERTIFICATE}" >/dev/null 2>&1

chmod 600 "${CA_KEY}" "${SERVER_KEY}"
chmod 644 "${CA_CERTIFICATE}" "${SERVER_CERTIFICATE}"
rm -f "${OUTPUT_DIRECTORY}/ca.srl"

printf 'Created the local Authentik CA and server certificate in %s.\n' "${OUTPUT_DIRECTORY}"
printf 'Trust this CA on the host before browser testing: %s\n' "${CA_CERTIFICATE}"
printf 'Host trust is intentionally not changed automatically. See docs/LOCAL-DEVELOPMENT.md.\n'
