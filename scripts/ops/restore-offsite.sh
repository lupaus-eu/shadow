#!/bin/sh
# Restore the newest (or a chosen) off-host backup into a directory, and
# optionally rehearse the restore into scratch databases.
#
#   scripts/ops/restore-offsite.sh <target-directory> [snapshot-id]
#   DRILL=1 scripts/ops/restore-offsite.sh /tmp/restore     # also run restore-drill.sh
#
# Uses the same configuration as backup-offsite.sh (`.env.production`, or the
# environment on a new host before the file has been restored). Restoring the dumps
# into the production databases is a manual step (docs/runbooks/backup.md).
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$HERE/lib-backup-env.sh"
RESTIC=${RESTIC:-restic}
COMPOSE=${COMPOSE:-docker compose -f $PROJECT_DIR/docker-compose.prod.yml --env-file $BACKUP_ENV_FILE}
export COMPOSE
TARGET=${1:?usage: restore-offsite.sh <target-directory> [snapshot-id]}
SNAPSHOT=${2:-latest}
: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY}"
export RESTIC_REPOSITORY

mkdir -p "$TARGET"
if [ "$SNAPSHOT" = latest ]; then
    $RESTIC restore latest --host yearclock --tag yearclock --target "$TARGET"
else
    $RESTIC restore "$SNAPSHOT" --target "$TARGET"
fi

yearclock_dump=$(find "$TARGET" -name 'yearclock-*.dump' | sort | tail -n 1)
authentik_dump=$(find "$TARGET" -name 'authentik-*.dump' | sort | tail -n 1)
[ -n "$yearclock_dump" ] && [ -n "$authentik_dump" ] || { echo "the snapshot holds no dump pair" >&2; exit 1; }
echo "yearclock dump: $yearclock_dump"
echo "authentik dump: $authentik_dump"

if [ "${DRILL:-0}" = 1 ]; then
    "$HERE/restore-drill.sh" "$yearclock_dump" "$authentik_dump"
fi
