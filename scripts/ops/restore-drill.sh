#!/bin/sh
# Restore drill: restore each dump into its own scratch database, owned by its
# own service role, verify it, and drop it again. Production data is untouched.
#
#   scripts/ops/restore-drill.sh backups/shadow-<stamp>.dump backups/authentik-<stamp>.dump
set -eu

COMPOSE=${COMPOSE:-docker compose}
ADMIN_USER=${POSTGRES_USER:-shadow}
AUTHENTIK_USER=${AUTHENTIK_POSTGRES_USER:-authentik}
SHADOW_DUMP=$1
AUTHENTIK_DUMP=$2

psql_admin() { $COMPOSE exec -T db psql -v ON_ERROR_STOP=1 -X -q -t -A -U "$ADMIN_USER" -d postgres "$@"; }

drill() {
    name=$1 owner=$2 dump=$3 query=$4
    scratch="restore_drill_$name"
    psql_admin -c "DROP DATABASE IF EXISTS $scratch" -c "CREATE DATABASE $scratch OWNER $owner"
    $COMPOSE exec -T db pg_restore --no-owner --role="$owner" -U "$ADMIN_USER" -d "$scratch" < "$dump"
    result=$($COMPOSE exec -T db psql -v ON_ERROR_STOP=1 -X -t -A -U "$ADMIN_USER" -d "$scratch" -c "$query")
    psql_admin -c "DROP DATABASE $scratch"
    [ -n "$result" ] || { echo "$name restore verification returned nothing" >&2; exit 1; }
    echo "$name restore OK: $result"
}

drill shadow "$ADMIN_USER" "$SHADOW_DUMP" \
    "SELECT 'schema ' || version_num || ', organizations ' || (SELECT count(*) FROM organizations) FROM alembic_version"
drill authentik "$AUTHENTIK_USER" "$AUTHENTIK_DUMP" \
    "SELECT 'users ' || count(*) FROM authentik_core_user"
