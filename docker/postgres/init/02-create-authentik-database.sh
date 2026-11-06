#!/bin/sh
set -eu

export PGUSER="${PGUSER:-${POSTGRES_USER}}"
export PGDATABASE="${PGDATABASE:-${POSTGRES_DB}}"
export PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD}}"

psql \
    --set=auth_database="${AUTHENTIK_POSTGRES_DB}" \
    --set=auth_user="${AUTHENTIK_POSTGRES_USER}" \
    --set=auth_password="${AUTHENTIK_POSTGRES_PASSWORD}" <<'SQL'
SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L',
    :'auth_user',
    :'auth_password'
)
WHERE NOT EXISTS (
    SELECT FROM pg_catalog.pg_roles WHERE rolname = :'auth_user'
)
\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L',
    :'auth_user',
    :'auth_password'
)
\gexec

SELECT format(
    'CREATE DATABASE %I OWNER %I',
    :'auth_database',
    :'auth_user'
)
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = :'auth_database'
)
\gexec

SELECT format(
    'ALTER DATABASE %I OWNER TO %I',
    :'auth_database',
    :'auth_user'
)
\gexec
SQL
