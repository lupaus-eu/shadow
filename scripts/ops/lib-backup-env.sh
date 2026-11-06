# Shared by backup-offsite.sh, restore-offsite.sh, and check-disk.sh (sourced, not run;
# the caller sets HERE to scripts/ops).
#
# Reads the production settings from the same file Docker Compose uses,
# `.env.production` in the project directory (override with BACKUP_ENV_FILE).
# The file is parsed line by line as KEY=value, never executed, so special
# characters in a secret are safe. Variables already set in the environment win.
# Lines may be quoted; `${VAR}` references and trailing comments are not expanded.
#
# The BACKUP_SCW_* settings are deliberately not the application's SCW_* ones: the
# backup uses a Scaleway project and key of its own, separate from transactional email.
PROJECT_DIR=$(cd "$HERE/../.." && pwd)
BACKUP_ENV_FILE=${BACKUP_ENV_FILE:-$PROJECT_DIR/.env.production}

if [ -f "$BACKUP_ENV_FILE" ]; then
    CR=$(printf '\r')
    while IFS= read -r line || [ -n "$line" ]; do
        line=${line%"$CR"}
        case $line in '' | '#'*) continue ;; esac
        case $line in [A-Za-z_]*=*) ;; *) continue ;; esac
        key=${line%%=*}
        value=${line#*=}
        case $key in *[!A-Za-z0-9_]*) continue ;; esac
        case $value in
            \"*\") value=${value#\"}; value=${value%\"} ;;
            \'*\') value=${value#\'}; value=${value%\'} ;;
        esac
        if [ -z "$(printenv "$key" 2>/dev/null || true)" ]; then
            export "$key=$value"
        fi
    done < "$BACKUP_ENV_FILE"
fi

# BACKUP_SCW_* follows the project's shared Scaleway convention (SCW_ACCESS_KEY,
# SCW_SECRET_KEY, SCW_DEFAULT_ORGANIZATION_ID, SCW_DEFAULT_PROJECT_ID), with a
# BACKUP_ prefix for the backup's own Scaleway project. The object-storage (S3)
# protocol that restic speaks authenticates with the key pair, the bucket, and the
# region only; the organization and project IDs are kept for the convention and for
# any Scaleway API call the backup may need later.
if [ -n "${BACKUP_SCW_BUCKET:-}" ]; then
    : "${BACKUP_SCW_REGION:?set BACKUP_SCW_REGION (the region of the bucket, for example fr-par)}"
    BACKUP_SCW_ENDPOINT=${BACKUP_SCW_ENDPOINT:-s3.$BACKUP_SCW_REGION.scw.cloud}
    : "${RESTIC_REPOSITORY:=s3:$BACKUP_SCW_ENDPOINT/$BACKUP_SCW_BUCKET${BACKUP_SCW_PREFIX:+/$BACKUP_SCW_PREFIX}}"
    : "${AWS_ACCESS_KEY_ID:=${BACKUP_SCW_ACCESS_KEY:-}}"
    : "${AWS_SECRET_ACCESS_KEY:=${BACKUP_SCW_SECRET_KEY:-}}"
    : "${AWS_DEFAULT_REGION:=$BACKUP_SCW_REGION}"
    export RESTIC_REPOSITORY AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION
fi
