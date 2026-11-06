-- ADR-016: application code runs under the NOLOGIN NOBYPASSRLS role shadow_app
-- (SET LOCAL ROLE per transaction). No row-level security policies yet (080G).
-- The role is cluster-wide, so creation is idempotent.
DO $$
BEGIN
    BEGIN
        CREATE ROLE shadow_app;
    EXCEPTION WHEN duplicate_object THEN
        NULL; -- created earlier or by a concurrent migration of another schema
    END;
END
$$;

-- Enforce the attributes whether or not the role pre-existed, so that a role
-- created elsewhere with BYPASSRLS or LOGIN cannot silently void ADR-016's
-- second line of defence.
ALTER ROLE shadow_app NOLOGIN NOBYPASSRLS NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- The migrating/owning role must be allowed to SET ROLE shadow_app.
GRANT shadow_app TO CURRENT_USER;

-- Grants are made for the schema the migration runs in, now and for tables and
-- sequences that later migrations create.
DO $$
BEGIN
    EXECUTE format('GRANT USAGE ON SCHEMA %I TO shadow_app', current_schema());
    EXECUTE format(
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO shadow_app',
        current_schema()
    );
    EXECUTE format(
        'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO shadow_app',
        current_schema()
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO shadow_app',
        current_schema()
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT USAGE, SELECT ON SEQUENCES TO shadow_app',
        current_schema()
    );
END
$$;

-- Migration history is not application data.
DO $$
BEGIN
    EXECUTE format('REVOKE ALL ON %I.schema_migrations FROM shadow_app', current_schema());
END
$$;
