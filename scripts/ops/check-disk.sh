#!/bin/sh
# Disk usage alert: pings the heartbeat only while usage is below the threshold,
# so a full disk (or a dead host) raises the alert through the missed ping.
#
#   scripts/ops/check-disk.sh [path]
#
# Environment: BACKUP_ALERT_EMAIL (an email when the limit is passed, at most every six
# hours), DISK_HEARTBEAT_URL (a heartbeat check of its own, optional),
# DISK_MAX_PERCENT (default 80); both are read from `.env.production`.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$HERE/lib-backup-env.sh"

CHECK_PATH=${1:-${DISK_CHECK_PATH:-/var/lib/docker}}
[ -d "$CHECK_PATH" ] || CHECK_PATH=/
MAX=${DISK_MAX_PERCENT:-80}
USED=$(df -P "$CHECK_PATH" | awk 'NR==2 {gsub("%", "", $5); print $5}')

ping() {
    [ -n "${DISK_HEARTBEAT_URL:-}" ] || return 0
    curl -fsS -m 10 --retry 3 -o /dev/null "$DISK_HEARTBEAT_URL$1" || echo "heartbeat ping $1 failed" >&2
}

if [ "$USED" -ge "$MAX" ]; then
    echo "disk usage on $CHECK_PATH is ${USED}% (limit ${MAX}%)" >&2
    # One email per six hours, not one per check.
    STATE=${DISK_ALERT_STATE_FILE:-/var/tmp/shadow-disk-alert}
    if [ -z "$(find "$STATE" -mmin -360 2>/dev/null)" ]; then
        "$HERE/notify-email.sh" "Shadow disk is ${USED}% full on $(hostname)" \
            "Disk usage on $CHECK_PATH is ${USED}% (limit ${MAX}%). Free space or grow the disk." && touch "$STATE" || true
    fi
    ping /fail
    exit 1
fi
ping ""
echo "disk usage on $CHECK_PATH is ${USED}% (limit ${MAX}%)"
