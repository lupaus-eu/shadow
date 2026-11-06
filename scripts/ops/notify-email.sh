#!/bin/sh
# Send a plain-text email through Scaleway Transactional Email, the same service and
# credentials the application uses (SCW_SECRET_KEY, SCW_DEFAULT_PROJECT_ID, and the
# SCW_TEM_* settings in .env.production). Used for backup and disk alerts.
#
#   scripts/ops/notify-email.sh "<subject>" "<text>"
#
# Does nothing when BACKUP_ALERT_EMAIL is empty. A failed send is reported on stderr and
# returns non-zero, so callers decide whether it matters.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$HERE/lib-backup-env.sh"

SUBJECT=${1:?usage: notify-email.sh <subject> <text>}
TEXT=${2:-}
[ -n "${BACKUP_ALERT_EMAIL:-}" ] || exit 0
: "${SCW_SECRET_KEY:?SCW_SECRET_KEY is not set in .env.production}"
: "${SCW_DEFAULT_PROJECT_ID:?SCW_DEFAULT_PROJECT_ID is not set in .env.production}"
: "${SCW_TEM_DEFAULT_SENDER_EMAIL:?SCW_TEM_DEFAULT_SENDER_EMAIL is not set in .env.production}"
REGION=${SCW_TEM_REGION:-fr-par}
API=${SCW_TEM_API_BASE_URL:-https://api.scaleway.com/transactional-email/v1alpha1/regions}

# Escape a string for a JSON value: backslash, quote, and line breaks.
json() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | awk 'NR > 1 { printf "\\n" } { printf "%s", $0 }'
}

BODY=$(printf '{"project_id":"%s","from":{"email":"%s","name":"%s"},"to":[{"email":"%s"}],"subject":"%s","text":"%s"}' \
    "$(json "$SCW_DEFAULT_PROJECT_ID")" "$(json "$SCW_TEM_DEFAULT_SENDER_EMAIL")" \
    "$(json "${SCW_TEM_DEFAULT_SENDER_NAME:-Shadow}")" "$(json "$BACKUP_ALERT_EMAIL")" \
    "$(json "$SUBJECT")" "$(json "$TEXT")")

curl -fsS -m 20 -o /dev/null -X POST "$API/$REGION/emails" \
    -H "X-Auth-Token: $SCW_SECRET_KEY" -H "Content-Type: application/json" \
    --data "$BODY"
