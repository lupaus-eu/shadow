#!/bin/sh
set -eu

if [ ! -r /usr/local/share/ca-certificates/schatten-local-authentik.crt ]; then
  printf '%s\n' 'Missing local Authentik CA certificate.' >&2
  printf '%s\n' 'Run scripts/setup-local-authentik-tls.sh before starting Docker Compose.' >&2
  exit 1
fi

update-ca-certificates >/dev/null

exec uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000
