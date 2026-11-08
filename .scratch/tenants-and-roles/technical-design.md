# Technical design: Companies (tenants) and roles

Status: wontfix

> **Closed as `wontfix` (2026-11-08).** Superseded by the Yearclock platform base that Shadow now runs on:
> Organizations (the paying account), memberships with the roles Owner, Admin and Member, row-level security
> by Organization, invitations and sign-in through Authentik already exist there (see
> `.scratch/saas-platform/`, `.scratch/authentik-sign-in/` and `docs/architecture/`). This feature was written
> for the previous Shadow code, now in `legacy/`, and its tickets 03 to 11 no longer apply to the current
> codebase. Tickets 01 and 02 were implemented in that earlier code.

Implements `PRD.md` and `domain-model.md` on ADR-016 (accepted). Builds on the platform foundation
(`app.platform`, `transaction_session`, `RequestContext`, `shadow_app`) and the Authentik sign-in
(`account_class`, `AUTH_*`). Yearclock (`../yearclock`, commit `6848e72`) is the model for the access
dependencies and membership routes (`access.py`, `membership_routes.py`, migrations `0004`/`0025`).

## Current and target state

- **Current:** one implicit company. Every business route requires a session of a `customer`
  account; `users.role` (`admin`/`consultant`) decides user administration only. Routes use
  `get_db_session` (the login role, no row-level security) with global paths
  `/api/v1/organisations/{organisation_key}/…` (51 operations), `/customers/{id}/…` (13), `/users` (6),
  `/ai/*` (8), notifications. MCP tools use their own sessions. The prediction worker uses the login
  role. `organisations.name` is unique globally.
- **Target:** companies and memberships; every company route under `/api/v1/tenants/{tenant_id}/…`;
  a per-request session that runs as `shadow_app` with the company context; row-level security on
  every company-owned table; accounts for new people created at sign-in; members API instead of the
  global Users API; the web application with a company address and selector.

## Domain

Owning domain: a new **Tenants** domain (`docs/architecture/domains/TENANTS.md`, created in ticket 01)
beside Users; Organisations, Customer, Forecasting and AI keep their tables, which gain `tenant_id`.

## Database (migration numbers reserved: 027, 028, 029, 030)

- **027 `tenants` and `tenant_memberships`** (ticket 01).
  `tenants(id UUID PK, name TEXT NOT NULL (non-blank, ≤200), status TEXT NOT NULL DEFAULT 'active'
  CHECK (status IN ('active')), created_time, modified_time)` — later steps extend the status check
  and add billing columns by their own migrations.
  `tenant_memberships(id UUID PK, tenant_id UUID NOT NULL REFERENCES tenants ON DELETE RESTRICT,
  user_id BIGINT NOT NULL REFERENCES users ON DELETE CASCADE, role TEXT NOT NULL CHECK (role IN
  ('owner','admin','member')), version INTEGER NOT NULL DEFAULT 1, created_time, modified_time,
  UNIQUE (tenant_id, user_id))`, index on `user_id`. Last-owner rule is enforced by the service in
  one transaction under `SELECT … FOR UPDATE` on the company's owner memberships and by a deferred
  constraint trigger as a second line. `users.role` becomes nullable (CHECK allows NULL).
  Backfill: when users, Organisations or Customers exist, create the company ("Reflector Oy", D1)
  and memberships: earliest `admin` → `owner`, other `admin` → `admin`, `consultant` → `member`
  (soft-deleted users get memberships too, so history stays coherent). Down drops both tables and
  restores NOT NULL on `role` where every row has one.
- **028 `tenant_id` on company-owned tables** (ticket 02). Tables (28): `organisations`, `customers`,
  `contacts`, `customer_addresses`, `scenarios`, `org_states`, `events`, `timeseries`,
  `timeserie_values`, `derived_metrics_equations`, `graph_nodes`, `graph_edges`, `metamodels`,
  `node_types`, `edge_types`, `type_attributes`, `allowed_connections`, `prediction_versions`,
  `prediction_requests`, `prediction_targets`, `prediction_model_results`, `prediction_points`,
  `ai_change_sets`, `ai_change_set_operations` (24 company tables; `metamodels` and its four child
  tables allow the default Metamodel's NULL).
  - Column `tenant_id UUID REFERENCES tenants(id)`; backfilled to the company; `NOT NULL` except for
    the Metamodel family.
  - **Roots** (`organisations`, `customers`): `DEFAULT app_tenant_id()` — the SQL function reads the
    transaction's company context and returns NULL when unset, so an insert without context fails the
    NOT NULL check (fail closed). **Children** get `tenant_id` from their parent by a
    `BEFORE INSERT` trigger (`scenarios` from `organisations`, `org_states`/`events`/`timeseries`/
    `graph_nodes`/`graph_edges`/`derived_metrics_equations` from `scenarios`, `timeserie_values` from
    `timeseries`, `contacts`/`customer_addresses` from `customers`, `prediction_*` and
    `ai_change_*` from their parents, Metamodel children from `metamodels`); the trigger overwrites
    any supplied value, so a child can never disagree with its parent, and application code needs no
    change for inserts. A `BEFORE UPDATE` trigger makes `tenant_id` immutable.
  - `organisations`: the unique index on `lower(name)` among active rows becomes
    `(tenant_id, lower(name))`; every other unique index of the 24 tables is reviewed and gains
    `tenant_id` where it is a business uniqueness (listed in the ticket); indexes `(tenant_id, …)` for
    the main list queries.
  - Platform tables (`audit_events`, `background_jobs`, `outbox_messages`, `notifications`) get a foreign
    key `tenant_id → tenants(id)`; they stay nullable (platform events).
  - `app_tenant_id()`, `app_user_id()`, `app_worker_scope()` helper functions (STABLE).
- **029 row-level security** (ticket 10): for the 24 tables `ENABLE` and `FORCE ROW LEVEL SECURITY` and
  one policy for `shadow_app`: `USING (tenant_id = app_tenant_id()) WITH CHECK (tenant_id =
  app_tenant_id())`; the Metamodel family `USING (tenant_id IS NULL OR tenant_id = app_tenant_id())
  WITH CHECK (tenant_id = app_tenant_id())`; the prediction tables add a permissive worker policy
  `USING (app_worker_scope() = 'predictions')`. `tenants`/`tenant_memberships`: select own memberships
  and the companies they belong to, write only inside the current company. `audit_events`: select
  `tenant_id = app_tenant_id()`, insert any; `notifications`: `recipient_user_id = app_user_id()`;
  `background_jobs`/`outbox_messages`: the worker scope and the current company. `users`, sessions,
  identities and the MCP OAuth tables are account data, not company data, and are not under policy.
- **030 drop `users.role`** (ticket 11): drops the column and its CHECK (down re-adds it nullable).

## Backend

- **Tenant session** (`app/core/tenancy.py`, ticket 03). `get_tenant_session` is a FastAPI dependency
  that reads the path parameter `tenant_id`, requires the business session, looks up the membership
  (login role; no membership or unknown company → 404 for the whole address; the lookup is the only
  statement outside the company context), and yields a `Session` bound to the login engine with an
  SQLAlchemy `after_begin` hook that, at the start of **every** transaction, runs `SET LOCAL ROLE
  shadow_app` and applies the `RequestContext` (user, company, the `app.request_context` marker).
  The hook is needed because the services call `session.commit()` several times per request and
  `SET LOCAL` ends with each transaction. The dependency also exposes `TenantAccess(user, tenant_id,
  role)`. Role dependencies: `require_tenant_member`, `require_tenant_admin` (admin or owner),
  `require_tenant_owner`. They replace `require_admin`/`require_business_admin`.
- **Routes** (tickets 04–06). The routers keep their functions: the module alias
  `SessionDependency` points at `get_tenant_session` and the routers get the prefix
  `/tenants/{tenant_id}` (FastAPI passes the path parameter to the dependency); services stay as they
  are apart from places that must not cross companies by explicit id (checked in the ticket) and
  from tests. Organisation keys stay random strings; `organisation_key` lookups are now naturally
  scoped by row-level security and by `WHERE` clauses that already exist. `GET /api/v1/tenants` lists
  the person's companies (`id`, `name`, `role`); `/auth/session` also returns them.
- **Accounts at sign-in** (ticket 03): `resolve_identity` creates an account (name from the claim or
  the email's local part, no role, `customer`, `en`) for a verified, unknown email when
  `AUTH_CREATE_ACCOUNTS` (default true) allows, in the same transaction as the identity link, and
  audits it; the IntegrityError of two concurrent first sign-ins refuses one.
- **Members API** (ticket 08): `/api/v1/tenants/{tenant_id}/members` GET (list), POST (add by email:
  `{email, name?, role}`), PATCH `/{user_id}` (`{role, expected_version}`), DELETE `/{user_id}`,
  POST `/{user_id}/sessions/revoke`; rules and codes of the domain model (404, 403, 409 for the last
  Owner, 409 for a version mismatch, 422 for validation); audit events `tenant.member_added`,
  `tenant.member_role_changed`, `tenant.member_removed`. It replaces the global Users API.
- **MCP** (ticket 07): `McpToolRuntime` gets its sessions from the same hook with the company
  resolved from the person's memberships (exactly one → implicit; none or several → a clear tool
  error naming the choice, until step 3b adds the argument); `allowed_scopes_for_role` stops reading
  `users.role` (every customer account gets read and write; the scopes retire in 3b).
- **Prediction worker** (ticket 06): claims and recovers requests under `worker_scope='predictions'`,
  then runs each request in its company's context.
- **Dev seed, `bootstrap_admin`, reference seed** (tickets 01, 02): the dev seed creates "Development
  Company" with `admin@example.local` as Owner and `consultant@example.local` as Member and sets the
  company context for the sample data; `bootstrap_admin` creates the account and, when no company
  exists, the first company with the person as Owner; the reference seed keeps writing the default
  Metamodel with a NULL company as the owner role.

## Frontend (ticket 09)

Routes `/tenants/:tenantId/shadow/:orgId/*` and `/tenants/:tenantId/…` for customers; `/` redirects a
person with one company into it, shows a company chooser for several and a "no company yet" page for
none; a company selector in the header; `AuthProvider` carries `tenants` and the current company; the
API client prefixes company paths; the Users tab becomes a Members tab for Admins and Owners; role
checks use the membership role. The frontend toolchain (`pnpm`) is required to implement and verify
this ticket; the other tickets need only the backend toolchain and Docker.

## Authentication and authorization

Authorization is the matrix of the domain model, checked in the backend per request; row-level
security is the second line. The login role (a database superuser in the current deployment) bypasses
policies, so no company data may be read through `get_db_session` any more; the remaining users of the
login-role session are account data (auth, sessions, identities, memberships lookup) and the migration
and seed tools. Ticket 10 adds a test that fails when a route reads a company table without the tenant
session.

## Errors

404 (no company, not a member, another company's object), 403 (role too low), 409 (last Owner,
version mismatch, duplicate), 422 (validation); the existing error envelope.

## Testing

- Per route family (tickets 04–06): two companies, two people; every operation of the family answers
  404 for the other company's data and cannot change it; unchanged behaviour for the own company;
  the authorization sweep (`test_api_authorization.py`) iterates the new paths with a member of
  one company and one with no company.
- Database level (tickets 02, 10): migrations up/down with data; trigger inheritance and immutability;
  fail-closed insert without context; row-level security per table with no, own and foreign context,
  for reads, writes and cross-company parent references; the worker scope; the default Metamodel.
- Concurrency (ticket 08): two simultaneous demotions of the last two Owners leave one Owner.
- MCP (ticket 07): a person with one company works; with two gets the error; another company's
  Organisation key answers not found.
- Frontend (ticket 09): vitest for routing, selector, no-company page, role-based visibility; browser
  check of the main path.
- Compose/runtime: `docker compose config`; the local stack run for the sign-in and a cross-company
  request through Caddy.

## Configuration

`AUTH_CREATE_ACCOUNTS` (default `true`) in `.env.example`, `docker-compose.yml` and the production
contract. No other change.

## Architecture effects

New domain and tables; every company route changes path; the backend's database access splits into
the login-role session (account data) and the tenant session (company data); the prediction worker
runs under row-level security. No new service or port.

## Documentation effects

- [x] `docs/admin/`, `docs/user/` — roles, members, companies (tickets 03, 08, 09)
- [x] `docs/operations/` — local-development (dev seed company), testing (tenancy tests) (tickets 01, 10)
- [x] `docs/architecture/` — `data/DATA-MODEL.md`, `DATABASE.md` (tables, policies), `domains/TENANTS.md` (new), `USERS.md`, `ORGANISATIONS.md`, `CUSTOMER.md`, `FORECASTING.md`, `AI.md`, `overview.md`, DB diagram, authentication sequence (tickets 01–10)
- [x] `docs/design/` — selector, no-company page (ticket 09)
- [x] `docs/adr/` — ADR-016 amendment (ticket 10)
- [x] `CONTEXT.md` — Tenant/Company, Membership, Role (ticket 01)
- [x] `.env.example` and the production contract — `AUTH_CREATE_ACCOUNTS` (ticket 03)

## Options and decision

| Option | Decision |
|---|---|
| `tenant_id` only on roots, policies by join | Rejected: joins on `timeserie_values` and `prediction_points` cost on every query; denormalised id with a parent-copy trigger keeps policies trivial and inserts unchanged. |
| Set the company in application code on every insert | Rejected: dozens of insert sites; the column default and the trigger make forgetting impossible and fail closed. |
| One transaction per request via `transaction_session` | Rejected: services commit several times per request; the `after_begin` hook re-applies the role and context at every transaction. |
| Keep old and new route paths side by side | Rejected: doubles the work and the test matrix; the frontend ticket follows the backend tickets and `main` is not released meanwhile (ADR-017). |
| Keep `users.role` as an admin flag | Rejected: two sources of authority; dropped by ticket 11. |
| Create the company through a UI now | Rejected: self-service signup is step 5; here the migration, the seed and the operator create it. |

## Tickets

01 tenants-and-memberships → 02 tenant-id-on-company-data → 03 tenant-access → 04 routes-organisations-and-customers
→ 05 routes-scenarios-and-structure → 06 routes-predictions-change-sets-and-worker → 07 mcp-company-context →
08 members-api → 09 frontend-company-context → 10 row-level-security → 11 drop-users-role.
04, 05 and 06 can follow 03 in any order; 07 needs 04–06; 08 needs 03; 09 needs 04–08; 10 needs 04–08;
11 needs 08, 09 and 07. Between ticket 04 and ticket 09 the web interface does not work against the new
routes; `main` is not released in that time (ADR-017).
