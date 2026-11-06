# Database

The full generated schema is in [`dbml/yearclock.dbml`](dbml/yearclock.dbml) (see [`dbml/README.md`](dbml/README.md)). This page explains the decisions behind it.

## Engine

PostgreSQL stores all persistent Yearclock application data.

For the first release, Yearclock and Authentik share one PostgreSQL instance but use separate logical databases, owners, credentials, connection pools, migration histories, and restore procedures. Neither service reads or writes the other's database. Authentik may move to a dedicated PostgreSQL instance later without changing the OIDC boundary.

## Ownership

The Yearclock database owns:

- User Account profiles linked to Authentik identities
- Organizations, memberships, and roles
- Yearclocks, Lanes, Categories, Events, Series, and Occurrences
- External Signal selections and Recommendations when those phases are implemented
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
- FastAPI enforces Organization and Yearclock role authorization.
- PostgreSQL row-level security independently restricts tenant-owned rows to the active Organization.
- Each request transaction sets trusted database context for the authenticated User Account, active Organization, and optional Support Access grant.
- Application transactions assume the non-superuser, non-`BYPASSRLS`
  `yearclock_app` runtime role before querying. The migration owner grants this
  role the required table privileges, while forced RLS also applies when the
  login role owns the tables.
- Migrations and background jobs use narrowly scoped service roles rather than the normal request role.
- Organization identifiers supplied by clients are never trusted without membership and role checks.

## Current implementation status

Docker Compose provisions the Yearclock PostgreSQL database and an isolated
local integration-test database. Alembic migrations `0001`–`0020` own:

- append-only Audit Events and PostgreSQL-backed outbox and job primitives
- customer authentication, account classes, and platform roles
- Organization activation, forced RLS, the restricted `yearclock_app` runtime
  role, seat capacity, and Invitations (`owner`, `admin`, `member` roles)
- Yearclocks, Lanes, per-Yearclock access grants, Categories, Events, Event
  Series, and Occurrence overrides
- recoverable Event deletion, subscription access state, Support Access
  requests, Organization deletion state, and resource versions

The request context carries an optional Support Access identifier, but no route
sets it yet, so Support Access does not currently participate in RLS.

Background workers first need to know which Organizations have due work.
Migration `0021` adds permissive, SELECT-only `*_worker_enumerate` policies on
`organizations` and `event_series` that apply only when a transaction sets
`app.worker_scope = 'enumerate'` (`RequestContext.worker_scope`). Request
handlers never set it; workers read identifiers under it and then act in each
Organization's normal RLS context.

`notifications` and `notification_preferences` (Yearclock V2 P8) add the
recipient to the Organization policy: a row is visible and changeable only when
`recipient_user_id` (or `user_id`) is the request's user. The code that writes
a notification for someone else, and the purge, switch on the transaction-local
`app.notification_write` flag for those statements only; the cleanup job runs
under `app.worker_scope = 'notifications'`. Support Access never reads them.

Migration `0022` replaces the separate Occurrence title and date override
columns with `series_occurrences.overrides` (JSONB) and adds
`event_series.effective_from` and `event_series.version` for Series segments.

Migration `0025` enables row-level security on `audit_events` and grants the
application role SELECT on it, scoped to the current Organization.

Migration `0026` adds `platform_enrollments` and
`oidc_login_attempts.audience`. The Platform Admin Organization list reads
Organization rows under the read-only `enumerate` worker scope and counts
members and Yearclocks in each Organization's own context; it never reads
content.

Migration `0027` enforces Support Access in PostgreSQL. The function
`app_support_grant_allows(needs_write)` is true when the transaction carries
no `app.current_support_access_id`, or when that id names an approved,
unexpired grant of the current Organization (with `write` scope for writes).
Restrictive policies on `yearclocks`, `lanes`, `categories`, `events`,
`event_series`, `series_occurrences`, and `yearclock_access_grants` AND this
check with the Organization policies, so a support transaction fails closed the
moment its grant expires or is revoked. `support_access_requests` gains RLS
(visible to its Organization and to the requesting agent), check constraints
on scope, status, and `requested_hours` (1–24), and decision timestamps.

Migration `0028` makes Organization deletion enforceable. It fixes
`ck_organizations_status` (which rejected `pending_deletion`) to also allow
`purged`, and adds `organizations.purged_at`. `app_organization_live(id)`
backs restrictive policies: content tables require an active Organization,
and memberships and invitations require one whenever an Organization context
is set, so an Owner can still find and restore their Organization. The
`purge` worker scope passes these checks, alone may delete Support Access
requests and Invitations, and may empty `audit_events.change_summary` (the
append-only trigger allows only that change).

Migration `0030` adds `yearclock_visits` (membership, Yearclock, Organization,
user, time) for the recently opened list. Rows cascade away with the
membership, the Yearclock, and the Organization. RLS shows a row only to its
own user inside the current Organization, and only while the Organization is
live.

Migration `0031` adds `labels` (Organization, name, colour, version) with a
unique index on `(organization_id, lower(name))`, a palette-format colour
check, and the content-table RLS set: the Organization policy, the
live-Organization check, and the Support Access checks. Organization purge
deletes the Organization's Labels.

Migration `0032` adds `event_labels` (Event, Label, Organization), which
cascades with its Event or Label and carries the content-table RLS set.

Migration `0033` adds `series_labels` (Series segment, Label, Organization)
with the same cascades and RLS as `event_labels`. Occurrence Label overrides
live in `series_occurrences.overrides["label_ids"]`.

Migration `0034` makes `categories.yearclock_id` nullable: a NULL value marks
an Organization Category. A partial unique index keeps Organization Category
names unique per Organization ignoring case. Organization purge deletes them.

Migration `0035` adds `yearclocks.start_month` (1–12, default 1), which sets
the default Planning Window.

Migration `0036` adds `yearclocks.show_week_ring` and
`yearclocks.show_quarter_ring` (both default false).

Migration `0037` adds `lanes.tint` (palette colour or NULL) and `lanes.height`
(`normal` or `tall`, default `normal`).

Migration `0038` adds `lanes.source_lane_id` for Linked Lanes (Yearclock V2). It references `lanes.id` with `ON DELETE CASCADE`, so removing the Source Lane or purging its Yearclock removes the link. A check forbids a Lane from being its own source, and the column is indexed. The application enforces the rest: the source is an own Lane of another Yearclock of the same Organization, and no Event or Series ever uses a Linked Lane. RLS on `lanes` is unchanged, because links never leave the Organization.

Migration `0039` adds `event_revisions` (Yearclock V2): the state of an Event after each change (`snapshot`), with `kind`, `reason`, `reason_detail`, `actor_account_id`, `actor_kind` (`member`, `support`, or `system`), `changed_fields`, and the Series of an Occurrence. Rows cascade with their Event, Yearclock, and Organization, carry the content-table RLS set, and are written by session hooks in `app/revisions.py`: after each flush they note the created or changed Events and the reason set by the route, and before commit they store one row per Event whose state differs from its latest revision. Bulk SQL changes (Label merge and delete) report their Events with `mark_changed`. The migration writes one `baseline` revision for every existing Event before enabling RLS. At most `LIMIT_REVISIONS_PER_EVENT` rows are kept per Event.

Migration `0040` adds `yearclock_visits.previous_visited_at` (Yearclock V2). Each visit upsert moves the old `visited_at` into it and returns it, so the planner can mark what others changed since the Previous Visit.

Migration `0041` adds `yearclocks.organization_access` (`none`, `viewer`, or `editor`; default `none`) for Organization-wide Access (Yearclock V2). The access rule in `app/access.py` reads it for every member.

Migration `0042` adds `member_groups` (Organization, name unique ignoring case, version) and `member_group_members` (Group, membership, Organization), which cascade with the Group, the membership, and the Organization (Yearclock V2). Both carry the Organization and live-Organization RLS policies and a restrictive policy that hides them from Support Access sessions.

Migration `0043` adds `yearclock_group_grants` (Organization, Yearclock, Group, role, version), unique per Yearclock and Group (Yearclock V2). It cascades with the Yearclock and the Group, and has the same RLS set as the Group tables. Only `app/access.py` and the access routes read it; a guard test enforces this.

Migration `0044` adds `invitation_groups` (Invitation, Group, Organization) for the Groups an invited person joins on acceptance (Yearclock V2). It cascades with both and has the Group tables' RLS set.

Migration `0049` adds `legal_acceptances` (ADR-0041): Organization, accepting User Account (kept as null if the account is removed), `accepted_by_email` (a snapshot, so the evidence names who agreed after they leave), `document_key`, `version`, `locale`, `accepted_at`, and `request_id`; unique per Organization, key, and version. It has the Organization RLS policy and the Support Access restriction but deliberately no live-Organization policy: rows are written while the Organization is still pending activation, and the Organization purge does not delete them (contract evidence). It also adds `legal_announcements` (`document_key`, `version`, `announced_at`; no Organization), which makes the announcement of a published version idempotent.
