#!/bin/sh
# Run restic against the backup repository with the settings from `.env.production`.
#
#   scripts/ops/restic.sh snapshots
#   scripts/ops/restic.sh check
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$HERE/lib-backup-env.sh"
: "${RESTIC_REPOSITORY:?set BACKUP_SCW_BUCKET, BACKUP_SCW_REGION, and the key pair in .env.production}"
exec "${RESTIC:-restic}" "$@"
