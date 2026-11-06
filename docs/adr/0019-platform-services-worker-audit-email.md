---
status: proposed
---

# Add platform services: audit log, worker and outbox, email, notifications

The SaaS transition (ADR-016) needs backend services that every later feature
(invitations, legal notices, billing, the platform console) builds on. Shadow
takes them from Yearclock, which the same team maintains, with names and
behaviour kept so that later changes can be ported mechanically. This ADR grows
as the platform-foundation tickets land; it is accepted by a human once all of
its parts are written.

## Audit log (ticket 02)

Security-relevant actions are recorded in the append-only table `audit_events`,
written in the transaction of the action it records. The actor and the tenant
come from the transaction's request context (`app.current_user_id`,
`app.current_tenant_id`), never from the caller's arguments. A trigger rejects
`UPDATE`, `DELETE` and `TRUNCATE`, and the application role is granted only
`INSERT` and `SELECT`. This protects against accidental SQL, not against code
that resets the role inside the process. Writing an event without a request
context raises an error instead of recording it unattributed. When the MCP
interface changes data, `audit_source()` stores the provenance (channel and
client) under the reserved summary key `source` of every entry written during
the tool call (ADR-015); a caller's summary may not use that key. `target_id` is text because Shadow's entities are keyed by bigint and
the platform's by UUID. The log has no tenant foreign key until the tenants
table exists; row-level security limits reads to the tenant with the tenant
routes. Existing mutations do not write audit events yet; each feature adds
them where it changes the action.

## Worker, job queue and outbox (ticket 03)

A second process, `python -m app.platform.worker`, runs background work. The
prediction worker (ADR-012) stays separate and unchanged. Work is queued in
PostgreSQL (`background_jobs`, and `outbox_messages` for email): enqueueing is
idempotent through a unique key, rows are claimed with `FOR UPDATE SKIP LOCKED`
so several workers never take the same row, a failed job is retried with
bounded exponential backoff up to five attempts, and a claim that is never
finished (a crashed worker) becomes claimable again after
`QUEUE_CLAIM_TIMEOUT_SECONDS`; Yearclock has no such recovery. A running
handler holds a row lock, so only a crashed worker's row is taken over, and a
worker that lost its claim changes nothing. Idempotency keys are unique per
tenant. Each job runs in
its own transaction as `shadow_app` under the job's tenant context. Features
register a handler per job type and, for timed work, a scheduler; the worker
holds no feature logic itself. In production the service is defined behind the
Compose profile `worker` and no deploy command starts it until the production
runtime adopts it (SaaS plan step 086A). The `health-check` subcommand verifies
the database connection.

Part of ADR-016's platform foundation.
