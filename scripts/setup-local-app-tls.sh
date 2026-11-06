#!/usr/bin/env bash
set -euo pipefail

readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly OUTPUT_DIRECTORY="${1:-${REPOSITORY_ROOT}/.local/app-tls}"
readonly LEGACY_CA_DIRECTORY="${REPOSITORY_ROOT}/.local/authentik-tls"
readonly LEAF_KEY="${OUTPUT_DIRECTORY}/app.localhost.key"
readonly LEAF_CERTIFICATE="${OUTPUT_DIRECTORY}/app.localhost.crt"
readonly RENEWAL_WINDOW_SECONDS=2592000

command -v openssl >/dev/null || { printf 'openssl is required\n' >&2; exit 1; }

certificate_has_app_hostname() {
  openssl x509 -noout -ext subjectAltName -in "$1" 2>/dev/null | grep -Fq 'DNS:app.localhost'
}

key_matches_certificate() {
  [[ "$(openssl x509 -noout -modulus -in "$1" 2>/dev/null | openssl sha256)" == "$(openssl rsa -noout -modulus -in "$2" 2>/dev/null | openssl sha256)" ]]
}

if [[ -r "${OUTPUT_DIRECTORY}/ca.crt" || -r "${OUTPUT_DIRECTORY}/ca.key" ]]; then
  readonly CA_DIRECTORY="${OUTPUT_DIRECTORY}"
elif [[ -r "${LEGACY_CA_DIRECTORY}/ca.crt" || -r "${LEGACY_CA_DIRECTORY}/ca.key" ]]; then
  readonly CA_DIRECTORY="${LEGACY_CA_DIRECTORY}"
else
  readonly CA_DIRECTORY="${OUTPUT_DIRECTORY}"
fi
readonly CA_CERTIFICATE="${CA_DIRECTORY}/ca.crt"
readonly CA_KEY="${CA_DIRECTORY}/ca.key"

if [[ -e "${LEAF_CERTIFICATE}" ]]; then
  if [[ ! -r "${LEAF_CERTIFICATE}" || ! -r "${LEAF_KEY}" ]]; then
    printf 'Application leaf certificate exists without its readable key in %s. Restore the matching key or deliberately rotate both leaf files.\n' "${OUTPUT_DIRECTORY}" >&2
    exit 1
  fi
  if [[ ! -r "${CA_CERTIFICATE}" ]]; then
    printf 'Application leaf material exists but its CA certificate is unavailable in %s. Do not replace keys blindly; restore the CA or deliberately rotate the local trust root.\n' "${CA_DIRECTORY}" >&2
    exit 1
  fi
  if ! openssl verify -CAfile "${CA_CERTIFICATE}" "${LEAF_CERTIFICATE}" >/dev/null || ! certificate_has_app_hostname "${LEAF_CERTIFICATE}" || ! key_matches_certificate "${LEAF_CERTIFICATE}" "${LEAF_KEY}"; then
    printf 'Application TLS material is invalid, signed by another CA, lacks app.localhost, or has a mismatched key. Refusing to overwrite it. Inspect and rotate it deliberately.\n' >&2
    exit 1
  fi
  if ! openssl x509 -checkend "${RENEWAL_WINDOW_SECONDS}" -noout -in "${LEAF_CERTIFICATE}" >/dev/null; then
    printf 'Application leaf certificate expires within 30 days. Keep the valid CA/key, deliberately remove only %s, then rerun this script to renew and re-check host trust.\n' "${LEAF_CERTIFICATE}" >&2
    exit 1
  fi
  printf 'Application TLS material already exists, is valid, and covers app.localhost: %s\n' "${OUTPUT_DIRECTORY}"
  printf 'Trust CA certificate on the host if browser trust is missing: %s\n' "${CA_CERTIFICATE}"
  exit 0
fi

if [[ -e "${LEAF_KEY}" ]] && ! openssl pkey -in "${LEAF_KEY}" -check -noout >/dev/null 2>&1; then
  printf 'Existing application leaf key is unreadable or invalid in %s. Refusing to overwrite it.\n' "${OUTPUT_DIRECTORY}" >&2
  exit 1
fi

umask 077
mkdir -p "${OUTPUT_DIRECTORY}"
temporary_directory="$(mktemp -d)"
trap 'rm -rf "${temporary_directory}"' EXIT

if [[ ! -e "${CA_CERTIFICATE}" && ! -e "${CA_KEY}" ]]; then
  if [[ "${CA_DIRECTORY}" != "${OUTPUT_DIRECTORY}" ]]; then
    printf 'Legacy CA material is incomplete in %s. Restore it or remove the incomplete legacy CA deliberately; this script will not overwrite it.\n' "${CA_DIRECTORY}" >&2
    exit 1
  fi
  openssl req -x509 -newkey rsa:3072 -sha256 -days 3650 -nodes -subj '/CN=Shadow Local Development CA' -addext 'basicConstraints=critical,CA:TRUE' -addext 'keyUsage=critical,keyCertSign,cRLSign' -keyout "${CA_KEY}" -out "${CA_CERTIFICATE}" >/dev/null 2>&1
  chmod 600 "${CA_KEY}"
  chmod 644 "${CA_CERTIFICATE}"
elif [[ ! -r "${CA_CERTIFICATE}" || ! -r "${CA_KEY}" ]]; then
  printf 'CA material is incomplete or unreadable in %s. Refusing to replace a possibly trusted key.\n' "${CA_DIRECTORY}" >&2
  exit 1
fi

if ! key_matches_certificate "${CA_CERTIFICATE}" "${CA_KEY}"; then
  printf 'CA certificate and key do not match in %s. Refusing to issue a leaf with an untrusted key.\n' "${CA_DIRECTORY}" >&2
  exit 1
fi

if ! openssl x509 -checkend "${RENEWAL_WINDOW_SECONDS}" -noout -in "${CA_CERTIFICATE}" >/dev/null; then
  printf 'The local CA in %s expires within 30 days. Rotate and re-trust that CA deliberately before creating an application leaf.\n' "${CA_DIRECTORY}" >&2
  exit 1
fi

if [[ -r "${LEAF_KEY}" ]]; then
  openssl req -new -sha256 -subj '/CN=app.localhost' -key "${LEAF_KEY}" -out "${temporary_directory}/app.localhost.csr" >/dev/null 2>&1
else
  openssl req -newkey rsa:3072 -sha256 -nodes -subj '/CN=app.localhost' -keyout "${LEAF_KEY}" -out "${temporary_directory}/app.localhost.csr" >/dev/null 2>&1
fi
printf '%s\n' 'basicConstraints=critical,CA:FALSE' 'keyUsage=critical,digitalSignature,keyEncipherment' 'extendedKeyUsage=serverAuth' 'subjectAltName=DNS:app.localhost' >"${temporary_directory}/app.localhost.ext"
openssl x509 -req -sha256 -days 825 -in "${temporary_directory}/app.localhost.csr" -CA "${CA_CERTIFICATE}" -CAkey "${CA_KEY}" -CAcreateserial -extfile "${temporary_directory}/app.localhost.ext" -out "${LEAF_CERTIFICATE}" >/dev/null 2>&1
chmod 600 "${LEAF_KEY}"
chmod 644 "${LEAF_CERTIFICATE}"
rm -f "${CA_DIRECTORY}/ca.srl"

printf 'Created or renewed the application leaf certificate in %s. Caddy receives only this leaf and key.\n' "${OUTPUT_DIRECTORY}"
printf 'Trust CA certificate on the host before browser testing: %s\n' "${CA_CERTIFICATE}"
printf 'Host trust is intentionally not changed automatically.\n'
