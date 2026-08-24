#!/bin/sh
set -eu

apply_blueprint() {
  blueprint_path="$1"
  if ! ak apply_blueprint "${blueprint_path}" >/dev/null 2>&1; then
    printf 'Failed to apply Authentik Entra configuration. Check the local values and blueprint schema.\n' >&2
    exit 1
  fi
}

# Authentik includes submitted model attributes in validation errors, including
# consumer_secret. Suppress command output so a malformed local value or a
# future schema change cannot copy the Entra secret into Compose logs.
apply_blueprint /blueprints/schatten-entra.yaml
apply_blueprint /blueprints/schatten-entra-source.yaml
apply_blueprint /blueprints/schatten-entra-identification.yaml

printf 'Authentik Entra source configuration applied successfully.\n'
