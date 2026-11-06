-- Revokes shadow_app's grants in this schema. The role itself is cluster-wide
-- and may be used by other schemas or databases, so it is kept.
DO $$
BEGIN
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM shadow_app',
        current_schema()
    );
    EXECUTE format(
        'ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON SEQUENCES FROM shadow_app',
        current_schema()
    );
    EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM shadow_app', current_schema());
    EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM shadow_app', current_schema());
    EXECUTE format('REVOKE ALL ON SCHEMA %I FROM shadow_app', current_schema());
END
$$;
