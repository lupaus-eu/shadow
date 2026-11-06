-- Append-only audit log (ADR-016, ticket 02). tenant_id has no foreign key
-- until the tenants table exists (migration 080A); support_access_id likewise.
-- target_id is text because Shadow's own entities use bigint identifiers.
CREATE TABLE audit_events (
    id UUID PRIMARY KEY,
    actor_user_id BIGINT REFERENCES users(user_id),
    tenant_id UUID,
    support_access_id UUID,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    occurred_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    request_id TEXT NOT NULL,
    change_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT ck_audit_events_action_non_blank CHECK (action ~ '[^[:space:]]'),
    CONSTRAINT ck_audit_events_action_length CHECK (char_length(action) <= 120),
    CONSTRAINT ck_audit_events_target_type_non_blank
        CHECK (target_type ~ '[^[:space:]]'),
    CONSTRAINT ck_audit_events_target_type_length
        CHECK (char_length(target_type) <= 120),
    CONSTRAINT ck_audit_events_target_id_non_blank CHECK (target_id ~ '[^[:space:]]'),
    CONSTRAINT ck_audit_events_target_id_length CHECK (char_length(target_id) <= 200),
    CONSTRAINT ck_audit_events_request_id_non_blank
        CHECK (request_id ~ '[^[:space:]]'),
    CONSTRAINT ck_audit_events_request_id_length
        CHECK (char_length(request_id) <= 120),
    CONSTRAINT ck_audit_events_change_summary_object
        CHECK (jsonb_typeof(change_summary) = 'object')
);

CREATE INDEX ix_audit_events_tenant_occurred
    ON audit_events (tenant_id, occurred_time DESC);
CREATE INDEX ix_audit_events_actor_user_id ON audit_events (actor_user_id);

CREATE FUNCTION reject_audit_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'audit events are append-only';
END;
$$;

CREATE TRIGGER audit_events_append_only
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation();

CREATE TRIGGER audit_events_no_truncate
    BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION reject_audit_event_mutation();

-- The application role may append and read, never change or remove.
REVOKE ALL ON audit_events FROM shadow_app;
GRANT SELECT, INSERT ON audit_events TO shadow_app;
