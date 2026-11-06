#!/bin/sh
# Creates Authentik's role and logical database in the application's PostgreSQL
# container (ADR-017); idempotent. Run by the one-shot authentik-db-init service
# with the PostgreSQL superuser of the application database.
set -eu

if [ "${AUTHENTIK_POSTGRES_USER}" = "${POSTGRES_USER}" ] || [ "${AUTHENTIK_POSTGRES_DB}" = "${POSTGRES_DB}" ]; then
    echo "Authentik must have its own role and database, not the application's." >&2
    exit 1
fi

export PGUSER="${PGUSER:-${POSTGRES_USER}}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD}}"

psql \
    --set=auth_database="${AUTHENTIK_POSTGRES_DB}" \
    --set=auth_user="${AUTHENTIK_POSTGRES_USER}" \
    --set=auth_password="${AUTHENTIK_POSTGRES_PASSWORD}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'auth_user', :'auth_password')
WHERE NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = :'auth_user')
\gexec

SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'auth_user', :'auth_password')
\gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'auth_database', :'auth_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'auth_database')
\gexec

SELECT format('ALTER DATABASE %I OWNER TO %I', :'auth_database', :'auth_user')
\gexec
SQL
