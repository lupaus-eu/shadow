#!/bin/sh
# Dump both databases, copy the dumps encrypted to object storage with restic,
# apply retention, and report to a dead-man's switch (docs/runbooks/backup.md).
#
#   scripts/ops/backup-offsite.sh
#
# Configuration comes from the environment or from `.env.production` in the project
# directory (BACKUP_ENV_FILE overrides it; see scripts/ops/lib-backup-env.sh and the
# BACKUP_* section of .env.production.example). A failure emails BACKUP_ALERT_EMAIL (notify-email.sh);
# BACKUP_SUCCESS_EMAIL=true also reports every success, so a missing email is the alarm,
# and an optional BACKUP_HEARTBEAT_URL pings an external check.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$HERE/lib-backup-env.sh"
RESTIC=${RESTIC:-restic}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/shadow}
LOCAL_KEEP_DAYS=${LOCAL_KEEP_DAYS:-2}
KEEP_HOURLY=${KEEP_HOURLY:-24}
KEEP_DAILY=${KEEP_DAILY:-30}
KEEP_MONTHLY=${KEEP_MONTHLY:-6}
# Paths kept with the dumps; by default the production settings file, so a new host
# can be rebuilt (it is encrypted in the repository like the dumps).
if [ -z "${BACKUP_EXTRA_FILES+x}" ] && [ -f "$BACKUP_ENV_FILE" ]; then BACKUP_EXTRA_FILES=$BACKUP_ENV_FILE; fi
BACKUP_EXTRA_FILES=${BACKUP_EXTRA_FILES:-}
COMPOSE=${COMPOSE:-docker compose -f $PROJECT_DIR/docker-compose.prod.yml --env-file $BACKUP_ENV_FILE}
export COMPOSE

: "${RESTIC_REPOSITORY:?set RESTIC_REPOSITORY}"
if [ -z "${RESTIC_PASSWORD:-}" ] && [ -z "${RESTIC_PASSWORD_FILE:-}" ]; then
    echo "set RESTIC_PASSWORD (or RESTIC_PASSWORD_FILE) in .env.production" >&2
    exit 1
fi
export RESTIC_REPOSITORY

ping() {
    [ -n "${BACKUP_HEARTBEAT_URL:-}" ] || return 0
    curl -fsS -m 10 --retry 3 -o /dev/null "$BACKUP_HEARTBEAT_URL$1" || echo "heartbeat ping $1 failed" >&2
}

failed() {
    status=$?
    trap - EXIT
    echo "backup failed (exit $status)" >&2
    "$HERE/notify-email.sh" "Shadow backup FAILED on $(hostname)" \
        "The backup run at $(date -u +%Y-%m-%dT%H:%M:%SZ) failed with exit status $status. See: journalctl -u shadow-backup" || true
    ping /fail
    exit "$status"
}
trap failed EXIT

ping /start

mkdir -p "$BACKUP_DIR"
umask 077
dumps=$("$HERE/backup-databases.sh" "$BACKUP_DIR")

if ! $RESTIC cat config >/dev/null 2>&1; then
    echo "initializing the restic repository"
    $RESTIC init
fi

# shellcheck disable=SC2086
$RESTIC backup --host shadow --tag shadow $dumps $BACKUP_EXTRA_FILES
# Dump file names change on every run, so group by tag, not by path.
$RESTIC forget --prune --host shadow --tag shadow --group-by host,tags \
    --keep-hourly "$KEEP_HOURLY" --keep-daily "$KEEP_DAILY" --keep-monthly "$KEEP_MONTHLY"
$RESTIC check

find "$BACKUP_DIR" -name '*.dump' -mtime "+$LOCAL_KEEP_DAYS" -delete

trap - EXIT
ping ""
if [ "${BACKUP_SUCCESS_EMAIL:-false}" = true ]; then
    "$HERE/notify-email.sh" "Shadow backup OK on $(hostname)" "Backed up at $(date -u +%Y-%m-%dT%H:%M:%SZ): $(echo "$dumps" | tr '\n' ' ')" || true
fi
echo "backup OK: $(echo "$dumps" | tr '\n' ' ')"
