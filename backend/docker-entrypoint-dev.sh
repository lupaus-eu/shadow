#!/bin/sh
set -eu

exec uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000
