---
status: accepted
---

# Introduce tenants, memberships and row-level security

Shadow becomes a multi-tenant service on the platform model of Yearclock. This
ADR fixes the tenancy concepts that the other SaaS-platform decisions
(authentication, billing, legal, platform console) depend on. It replaces the
"Initial Authorization" section of [ADR-004](0004-authentication.md), whose
trust-all-users baseline holds only for one company's internal use.

## Context

Today every signed-in User may read and change every Organisation, and `users.role`
is an application-wide `admin` or `consultant`. ADR-004 states that this must be
revisited before admitting users outside the trust model. Admitting other
companies is the goal of the SaaS transition (`.scratch/saas-platform/PLAN.md`).

"Organisation" already means the modelled organisation (`CONTEXT.md`). Yearclock's
tenant concept is also called Organization, so reusing that name would blur two
unrelated ideas and break the MCP tool names and routes (`list_organisations`,
`/shadow/:orgId`).

## Decision

1. **Name.** The subscribing company is a **Tenant** in code and APIs (`tenants`,
   `tenant_memberships`, `TenantRole`) and **Company / Yritys** in the user
   interface. Code copied from Yearclock is renamed mechanically
   `organization` → `tenant`. An Organisation stays the modelled organisation
   and is owned by exactly one Tenant.
2. **Accounts and roles.** `users` stays the account table and gains an
   `account_class`: `customer` or `platform`. A customer account has any number
   of independent **memberships**, each with the role `owner`, `admin` or
   `member`. Removing a membership never deletes the account or affects its other
   memberships. A Tenant always has at least one Owner. Platform accounts
   (`platform_admin`, `support_agent`) never hold memberships and use only the
   platform console.
3. **Role matrix.** A Member reads and edits every Organisation of the Tenant,
   as a `consultant` does today. An Admin also manages people, the MCP
   connection and support access. An Owner also manages billing, ownership and
   deletion of the Tenant. Per-Organisation permissions (viewer or editor) are
   outside this decision.
4. **Explicit tenant route.** Tenant API and browser routes carry the tenant
   identifier (`/api/v1/tenants/{tenant_id}/…`, `/tenants/:tenantId/…`). The
   backend verifies the caller's membership and role on every request and never
   relies on a mutable active-tenant value in the session. Identifiers of
   Tenants and of the other platform tables are UUIDs, so they cannot be guessed.
5. **Isolation in two layers.** Authorization is checked in the backend, and
   PostgreSQL row-level security is the second line of defence. Application code
   runs under the `NOLOGIN NOBYPASSRLS` role `shadow_app` and sets the context
   (`app.current_user_id`, `app.current_tenant_id` and the like) per transaction.
   Tenant-owned tables carry a `tenant_id` (denormalised on tables that are
   reached through a Scenario) and an RLS policy on it. Missing context or a
   foreign tenant yields no rows and a `404`, not a `403`.
6. **Scoping rules.** An Organisation key is unique within its Tenant, not
   globally. The default Metamodel has `tenant_id` NULL and is readable by all
   Tenants. Support staff reach tenant data only through explicit,
   time-limited support access (decided with the platform console).
7. **Staging.** Tenancy arrives in steps so that each is shippable: a request
   context and the role without policies, then the schema with `tenant_id`
   columns and a backfill, then the tenant routes, and lastly the policies.
   Until the policies exist, the backend checks are the only isolation.
8. **Existing data.** Migration creates one Tenant for the company that runs
   Shadow today and moves all data to it. `admin` becomes `admin`, `consultant`
   becomes `member`, and the bootstrap administrator becomes `owner`.

## Consequences

- Every business route changes its path and gains a membership check. The
  frontend gains a tenant context and selector.
- Cross-tenant tests (a foreign tenant returns `404`) are required for every
  route, and database-level tests for the policies.
- Billing, legal acceptance, invitations and the platform console all hang off
  the Tenant, which is why this ADR is accepted before the platform foundation.
- Rejected: naming the Tenant "Organization" as in Yearclock, because it forces
  renaming the modelled Organisation and the MCP tools; one database per Tenant,
  because Shadow's operating model is one shared PostgreSQL instance.
- Open for later ADRs: the `complimentary` billing state (ADR-018), MCP
  authentication and per-tenant switches, and platform support access.

Replaces the "Initial Authorization" section of ADR-004.
