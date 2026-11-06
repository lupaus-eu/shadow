#!/usr/bin/env python3
"""Check that Compose files use Shadow's project name and host port range.

Shared development machines run several projects side by side. Each project
owns one host port range (see docs/architecture/docker.md). This check fails
when a Compose file:

- lacks the top-level `name: shadow`, or sets `container_name`;
- publishes a port without a `${SHADOW_*_PORT:-NNNN}` host variable, or
  uses the long port syntax;
- in the production file, leaves any service without a rotated `json-file`
  log (`max-size` and `max-file`), which could fill the host disk;
- resolves, with default values only, to a host port outside the range, a
  host address other than 127.0.0.1, or a port already used by another entry.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "shadow"
PORT_RANGE = range(8100, 8200)
PRODUCTION_FILE = "docker-compose.prod.yml"
DEFAULT_HOST = "127.0.0.1"
COMPOSE_GLOBS = ("docker-compose*.yml", "docker-compose*.yaml", "compose*.yml", "compose*.yaml")
REQUIRED_VARIABLE = re.compile(r"\$\{([A-Z0-9_]+):\?")
SHORT_PORT = re.compile(
    r'^"\$\{SHADOW_[A-Z_]*BIND_ADDRESS:-127\.0\.0\.1\}'
    r':\$\{SHADOW_[A-Z_]+_PORT:-(\d+)\}:(\d+)(/(tcp|udp))?"$'
)


def _port_entries(text: str) -> list[tuple[int, str]]:
    """Return (line number, entry) for every item under a `ports:` key."""
    entries = []
    indent = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        current = len(line) - len(line.lstrip())
        if stripped == "ports:":
            indent = current
            continue
        if indent is None or not stripped or stripped.startswith("#"):
            continue
        if current > indent and stripped.startswith("-"):
            entries.append((number, stripped[1:].strip()))
        elif current <= indent:
            indent = None
    return entries


def _resolved_config(path: Path) -> dict:
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG", "DOCKER_CONTEXT"}}
    # Required production secrets (${NAME:?message}) get placeholders so the
    # file resolves; they never affect published ports.
    env.update({name: "port-check" for name in REQUIRED_VARIABLE.findall(path.read_text(encoding="utf-8"))})
    result = subprocess.run(
        ["docker", "compose", "--env-file", os.devnull, "--project-directory", str(ROOT),
         "-f", str(path), "--profile", "*", "config", "--format", "json"],
        capture_output=True, text=True, env=env, check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker compose config failed for {path.name}:\n{result.stderr.strip()}")
    return json.loads(result.stdout)


def check(path: Path) -> list[str]:
    name = path.relative_to(ROOT).as_posix()
    errors = []
    for number, entry in _port_entries(path.read_text(encoding="utf-8")):
        if not SHORT_PORT.match(entry):
            errors.append(
                f"{name}:{number}: port {entry} must be written as "
                '"${SHADOW_BIND_ADDRESS:-127.0.0.1}:${SHADOW_<SERVICE>_PORT:-NNNN}:<container port>"'
            )

    config = _resolved_config(path)
    if config.get("name") != PROJECT_NAME:
        errors.append(f"{name}: top-level `name: {PROJECT_NAME}` is required")
    seen: dict[int, str] = {}
    production = path.name == PRODUCTION_FILE
    for service, spec in sorted(config.get("services", {}).items()):
        if "container_name" in spec:
            errors.append(f"{name}: service {service} sets container_name; rely on the project name instead")
        if production:
            logging = spec.get("logging") or {}
            options = logging.get("options") or {}
            if logging.get("driver") != "json-file" or not options.get("max-size") or not options.get("max-file"):
                errors.append(f"{name}: service {service} needs a json-file logging section with max-size and max-file")
        for port in spec.get("ports", []):
            published = int(port.get("published", 0) or 0)
            host = port.get("host_ip", "")
            label = f"{service} {published}->{port.get('target')}"
            if published not in PORT_RANGE:
                errors.append(f"{name}: {label} is outside {PORT_RANGE.start}-{PORT_RANGE.stop - 1}")
            if host != DEFAULT_HOST:
                errors.append(f"{name}: {label} binds to {host or 'all interfaces'} instead of {DEFAULT_HOST}")
            if published in seen:
                errors.append(f"{name}: {label} reuses host port {published} from {seen[published]}")
            seen[published] = service
    return errors


def main() -> int:
    files = sorted({path for pattern in COMPOSE_GLOBS for path in ROOT.glob(pattern)})
    if not files:
        print("No Compose files found.", file=sys.stderr)
        return 1
    errors = [error for path in files for error in check(path)]
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"Compose ports OK: {', '.join(p.name for p in files)} use {PORT_RANGE.start}-{PORT_RANGE.stop - 1} on {DEFAULT_HOST}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
