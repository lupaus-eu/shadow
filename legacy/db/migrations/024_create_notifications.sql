-- In-app notifications (ADR-019, ticket 04): one row says that something
-- changed for one person; the text is built when it is read, from the type and
-- parameters. tenant_id has no foreign key until the tenants table exists.
CREATE TABLE notifications (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    recipient_user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    params JSONB NOT NULL DEFAULT '{}'::jsonb,
    dedupe_key TEXT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_time TIMESTAMPTZ,
    CONSTRAINT ck_notifications_type
        CHECK (type ~ '[^[:space:]]' AND char_length(type) <= 120),
    CONSTRAINT ck_notifications_params_object CHECK (jsonb_typeof(params) = 'object'),
    CONSTRAINT ck_notifications_dedupe_key
        CHECK (dedupe_key IS NULL OR (dedupe_key ~ '[^[:space:]]' AND char_length(dedupe_key) <= 200)),
    CONSTRAINT ck_notifications_read_after_created
        CHECK (read_time IS NULL OR read_time >= created_time)
);

CREATE INDEX ix_notifications_inbox
    ON notifications (recipient_user_id, created_time DESC, id DESC);
CREATE INDEX ix_notifications_created_time ON notifications (created_time);

-- A newer unread notification with the same key replaces the older one.
CREATE UNIQUE INDEX ux_notifications_unread_dedupe
    ON notifications (recipient_user_id, tenant_id, dedupe_key) NULLS NOT DISTINCT
    WHERE read_time IS NULL AND dedupe_key IS NOT NULL;
