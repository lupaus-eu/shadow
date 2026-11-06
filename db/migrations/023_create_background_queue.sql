-- Durable work queues for the worker (ADR-019, ticket 03): background jobs and
-- the email outbox. tenant_id has no foreign key until the tenants table
-- exists (migration 080A). shadow_app gets SELECT, INSERT, UPDATE, DELETE
-- from migration 021's default privileges.
CREATE TABLE background_jobs (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    job_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_time TIMESTAMPTZ,
    last_error TEXT,
    CONSTRAINT uq_background_jobs_tenant_key
        UNIQUE NULLS NOT DISTINCT (tenant_id, idempotency_key),
    CONSTRAINT ck_background_jobs_job_type
        CHECK (job_type ~ '[^[:space:]]' AND char_length(job_type) <= 120),
    CONSTRAINT ck_background_jobs_idempotency_key
        CHECK (idempotency_key ~ '[^[:space:]]' AND char_length(idempotency_key) <= 200),
    CONSTRAINT ck_background_jobs_payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_background_jobs_status
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    CONSTRAINT ck_background_jobs_attempts CHECK (attempts >= 0)
);

CREATE TABLE outbox_messages (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    topic TEXT NOT NULL,
    payload JSONB NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    available_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    claimed_time TIMESTAMPTZ,
    last_error TEXT,
    provider_message_id TEXT,
    CONSTRAINT uq_outbox_messages_tenant_key
        UNIQUE NULLS NOT DISTINCT (tenant_id, idempotency_key),
    CONSTRAINT ck_outbox_messages_topic
        CHECK (topic ~ '[^[:space:]]' AND char_length(topic) <= 120),
    CONSTRAINT ck_outbox_messages_idempotency_key
        CHECK (idempotency_key ~ '[^[:space:]]' AND char_length(idempotency_key) <= 200),
    CONSTRAINT ck_outbox_messages_payload_object CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_outbox_messages_status
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    CONSTRAINT ck_outbox_messages_attempts CHECK (attempts >= 0)
);

-- The idempotency key is unique per tenant (and among tenant-less system rows).
-- Claims scan only unfinished rows, so finished rows do not slow them down.
CREATE INDEX ix_background_jobs_claimable
    ON background_jobs (available_time, created_time, id)
    WHERE status IN ('pending', 'processing');
CREATE INDEX ix_outbox_messages_claimable
    ON outbox_messages (available_time, created_time, id)
    WHERE status IN ('pending', 'processing');
