#!/bin/sh
# Back up the Shadow and Authentik databases separately, each with its own
# owner credentials (ADR-0011). Dumps use the custom format for pg_restore.
#
#   scripts/ops/backup-databases.sh [backup-directory]
#
# Environment: COMPOSE (default "docker compose"), POSTGRES_DB, POSTGRES_USER,
# AUTHENTIK_POSTGRES_DB, AUTHENTIK_POSTGRES_USER, AUTHENTIK_POSTGRES_PASSWORD.
set -eu

COMPOSE=${COMPOSE:-docker compose}
BACKUP_DIR=${1:-backups}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
SHADOW_DB=${POSTGRES_DB:-shadow}
SHADOW_USER=${POSTGRES_USER:-shadow}
AUTHENTIK_DB=${AUTHENTIK_POSTGRES_DB:-authentik}
AUTHENTIK_USER=${AUTHENTIK_POSTGRES_USER:-authentik}
AUTHENTIK_PASSWORD=${AUTHENTIK_POSTGRES_PASSWORD:-authentik}

mkdir -p "$BACKUP_DIR"
umask 077

$COMPOSE exec -T db pg_dump --format=custom --no-password -U "$SHADOW_USER" -d "$SHADOW_DB" \
    > "$BACKUP_DIR/shadow-$STAMP.dump"
$COMPOSE exec -T -e PGPASSWORD="$AUTHENTIK_PASSWORD" db pg_dump --format=custom -h 127.0.0.1 -U "$AUTHENTIK_USER" -d "$AUTHENTIK_DB" \
    > "$BACKUP_DIR/authentik-$STAMP.dump"

for file in "$BACKUP_DIR/shadow-$STAMP.dump" "$BACKUP_DIR/authentik-$STAMP.dump"; do
    [ -s "$file" ] || { echo "backup failed: $file is empty" >&2; exit 1; }
done
echo "$BACKUP_DIR/shadow-$STAMP.dump"
echo "$BACKUP_DIR/authentik-$STAMP.dump"
