# Database

The full generated schema is in [`dbml/shadow.dbml`](dbml/shadow.dbml) (see [`dbml/README.md`](dbml/README.md)). This page explains the decisions behind it.

## Engine

PostgreSQL stores all persistent Shadow application data.

For the first release, Shadow and Authentik share one PostgreSQL instance but use separate logical databases, owners, credentials, connection pools, migration histories, and restore procedures. Neither service reads or writes the other's database. Authentik may move to a dedicated PostgreSQL instance later without changing the OIDC boundary.

## Ownership

The Shadow database owns:

- User Account profiles linked to Authentik identities
- Organizations, memberships, and roles
- Models with their metamodel, versions, nodes, and connections
- Metrics with monthly values and formulas
- Simulations (forecast points) and the findings and action proposals derived from them
- local Stripe subscription projections
- purchased Organization Seat capacity and Invitation reservations
- support access and audit records
- deletion lifecycle state

Authentik remains authoritative for credentials and identity sessions. Stripe remains authoritative for subscription and payment state.

## Application persistence

- SQLAlchemy 2 provides ORM models, queries, and transaction boundaries.
- Psycopg 3 provides synchronous PostgreSQL access.
- Alembic owns application schema migrations.
- Each request uses one database session and transaction.
- Trusted RLS context is set at the start of the request transaction.
- API schemas remain separate from ORM models.
- Explicit SQL is used for RLS policies, database constraints, and complex queries where it is clearer than ORM expressions.

## Tenant isolation

- Tenant-owned tables use shared schemas and carry a required `organization_id`.
- FastAPI enforces Organization role authorization.
- PostgreSQL row-level security independently restricts tenant-owned rows to the active Organization.
- Each request transaction sets trusted database context for the authenticated User Account, active Organization, and optional Support Access grant.
- Application transactions assume the non-superuser, non-`BYPASSRLS`
  `shadow_app` runtime role before querying. The migration owner grants this
  role the required table privileges, while forced RLS also applies when the
  login role owns the tables.
- Migrations and background jobs use narrowly scoped service roles rather than the normal request role.
- Organization identifiers supplied by clients are never trusted without membership and role checks.

## Current implementation status

Docker Compose provisions the Shadow PostgreSQL database and an isolated
local integration-test database. Alembic migrations `0001`–`0049` (platform base) own:

- append-only Audit Events and PostgreSQL-backed outbox and job primitives
- customer authentication, account classes, and platform roles
- Organization activation, forced RLS, the restricted `shadow_app` runtime
  role, seat capacity, and Invitations (`owner`, `admin`, `member` roles)
- subscription access state, Support Access
  requests, Organization deletion state, and resource versions

The request context carries an optional Support Access identifier, but no route
sets it yet, so Support Access does not currently participate in RLS.

Background workers first need to know which Organizations have due work.
Migration `0021` adds a permissive, SELECT-only `*_worker_enumerate` policy on
`organizations` that apply only when a transaction sets
`app.worker_scope = 'enumerate'` (`RequestContext.worker_scope`). Request
handlers never set it; workers read identifiers under it and then act in each
Organization's normal RLS context.

`notifications` and `notification_preferences` add the
recipient to the Organization policy: a row is visible and changeable only when
`recipient_user_id` (or `user_id`) is the request's user. The code that writes
a notification for someone else, and the purge, switch on the transaction-local
`app.notification_write` flag for those statements only; the cleanup job runs
under `app.worker_scope = 'notifications'`. Support Access never reads them.

Migration `0025` enables row-level security on `audit_events` and grants the
application role SELECT on it, scoped to the current Organization.

Migration `0026` adds `platform_enrollments` and
`oidc_login_attempts.audience`. The Platform Admin Organization list reads
Organization rows under the read-only `enumerate` worker scope and counts
members and models in each Organization's own context; it never reads
content.

Migration `0027` enforces Support Access in PostgreSQL. The function `app_support_grant_allows(needs_write)` is true when the transaction carries no `app.current_support_access_id`, or when that id names an approved, unexpired grant of the current Organization (with `write` scope for writes). Restrictive policies on content tables AND this check with the Organization policies, so a support transaction fails closed the moment its grant expires or is revoked. `support_access_requests` is visible to its Organization and to the requesting agent.

Migration `0028` makes Organization deletion enforceable. It fixes
`ck_organizations_status` (which rejected `pending_deletion`) to also allow
`purged`, and adds `organizations.purged_at`. `app_organization_live(id)`
backs restrictive policies: content tables require an active Organization,
and memberships and invitations require one whenever an Organization context
is set, so an Owner can still find and restore their Organization. The
`purge` worker scope passes these checks, alone may delete Support Access
requests and Invitations, and may empty `audit_events.change_summary` (the
append-only trigger allows only that change).

Migration `0049` adds `legal_acceptances` (ADR-0041): Organization, accepting User Account (kept as null if the account is removed), `accepted_by_email` (a snapshot, so the evidence names who agreed after they leave), `document_key`, `version`, `locale`, `accepted_at`, and `request_id`; unique per Organization, key, and version. It has the Organization RLS policy and the Support Access restriction but deliberately no live-Organization policy: rows are written while the Organization is still pending activation, and the Organization purge does not delete them (contract evidence). It also adds `legal_announcements` (`document_key`, `version`, `announced_at`; no Organization), which makes the announcement of a published version idempotent.

Migration `0050` drops the Yearclock product tables; the platform base keeps only
platform tables.

Migrations `0051`–`0058` add the Shadow tables. Each carries `organization_id`, the
Organization RLS policy, the live-Organization check (0028), and the Support Access
check (0027), and cascades away with its Organization.

- `0051` `models`, `node_types`, `connection_types`, `allowed_connections`, `nodes`,
  `connections`. The metamodel belongs to the model and is seeded from
  `backend/app/default_metamodel.json` (ADR-0043). Composite foreign keys keep every
  reference inside one Organization and one model.
- `0052` `model_versions`: a baseline per model and forked versions, each holding a
  complete graph. `nodes.origin_node_id` records where a node came from so the change
  list against the base can be computed and a merge can re-point it (ADR-0045).
- `0053` `metrics` and `metric_values`: a metric belongs to a version and either holds
  monthly values or a formula over other metrics of the version.
- `0054` `simulations` and `simulation_points`: a forecast run of a version with its
  method, adjustments, history, forecast, and bands.
- `0055` `recommendations`: action proposals derived from a simulation, with a status
  (open, accepted, dismissed) and a `kind` (`rule`, later `ai`).
- `0056` lets `simulations.method` be `prophet` (ADR-0042).
- `0057` adds `simulations.ai_summary` and `ai_generated_at` (ADR-0044).
- `0058` renames them to `analysis_summary` and `analysis_summary_at`, adds `analysis_summary_author` (the person, or `agent:<client>`), and deletes the `recommendations` of kind `ai`. Agents write the summary and `agent` proposals through MCP (ADR-0047).
- `0059` adds `mcp_calls`: one content-free row per MCP tool call (person, agent program, tool, read or write, outcome, duration), row-level secured by Organization; the application role may delete only successful read rows, under the `mcp_read_log` worker scope (ADR-0047).
- `0060` adds the model timeline tables (ADR-0048): `model_lines` (the Base line and Scenarios, with parent and branch event), `timeline_events` (dated, ordered by date then `seq`), `event_changes` (ordered change steps as JSONB) and `node_positions` (per line and node). All have `organization_id` and row-level security. A branch event cannot be deleted while a line branches from it (foreign key `RESTRICT`), and a line with Scenarios cannot be deleted. Nothing reads them until the version data is migrated.
