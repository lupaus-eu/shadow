#!/bin/sh

set -eu

: "${PUBLIC_ORIGIN:?Set the exact public HTTPS origin}"
: "${CADDY_TLS_MODE:?Set CADDY_TLS_MODE to acme or internal}"

case "${CADDY_TLS_MODE}" in
  acme|internal) ;;
  *)
    echo "CADDY_TLS_MODE must be acme or internal" >&2
    exit 1
    ;;
esac

invalid_origin() {
  echo "PUBLIC_ORIGIN must contain one browser-canonical lowercase DNS or IP host without an explicit port" >&2
  exit 1
}

valid_ipv4() {
  printf '%s\n' "$1" | awk -F. '
    NF != 4 { exit 1 }
    {
      for (part = 1; part <= 4; part += 1) {
        if ($part !~ /^[0-9]+$/ || length($part) > 3 ||
            ($part != "0" && substr($part, 1, 1) == "0") || $part + 0 > 255) {
          exit 1
        }
      }
    }
  '
}

case "${PUBLIC_ORIGIN}" in
  https://*) ;;
  *)
    echo "PUBLIC_ORIGIN must be an HTTPS origin" >&2
    exit 1
    ;;
esac

PUBLIC_HOST="${PUBLIC_ORIGIN#https://}"
case "${PUBLIC_HOST}" in
  ""|*/*|*\?*|*\#*|*[[:space:]]*|*\**|*,*|*\\*|*@*|*%*) invalid_origin ;;
esac

case "${PUBLIC_HOST}" in
  \[*\])
    ipv6_and_rest="${PUBLIC_HOST#\[}"
    ipv6="${ipv6_and_rest%\]}"
    ;;
  \[*) invalid_origin ;;
  *)
    case "${PUBLIC_HOST}" in
      *:*) invalid_origin ;;
      *) dns_host="${PUBLIC_HOST}" ;;
    esac
    if [ "${#dns_host}" -gt 253 ] || ! printf '%s\n' "${dns_host}" | grep -Eq '^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$'; then
      invalid_origin
    fi
    if printf '%s\n' "${dns_host}" | grep -Eq '^(0x[0-9a-f]+|[0-9]+)(\.(0x[0-9a-f]+|[0-9]+))*$' && ! valid_ipv4 "${dns_host}"; then
      invalid_origin
    fi
    ;;
esac

if [ "${PUBLIC_HOST#\[}" != "${PUBLIC_HOST}" ]; then
  case "${ipv6}" in
    ""|*[!0-9a-f:.]*) invalid_origin ;;
    *:*) ;;
    *) invalid_origin ;;
  esac
fi

export PUBLIC_HOST
exec "$@"
