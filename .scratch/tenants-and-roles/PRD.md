# Feature: Companies (tenants) and roles

Status: ready-for-human

Step 3 of the SaaS plan (`.scratch/saas-platform/PLAN.md`, tasks 080A–080G). The concepts are fixed
by [ADR-016](../../docs/adr/0016-introduce-tenants-memberships-and-rls.md); open questions were
settled with the plan's recommendations on 2026-11-06 (see *Decisions*), except the one marked
*to confirm*.

## Goal

Several companies can use Shadow side by side without ever seeing each other's data. Every
Organisation, Customer and everything below them belongs to exactly one company (tenant), a person
belongs to a company through a membership with the role Owner, Admin or Member, and the database
itself refuses to show one company's rows to another. Today's single company keeps all its data and
its people.

## User

- **Member** of a company: reads and edits every Organisation, Customer and model of that company.
- **Admin**: a Member who also manages the company's people.
- **Owner**: an Admin who also holds ownership (billing and deletion arrive with steps 5 and 8).
- **A person without a company** (signed in through an Authentik invitation, not yet added anywhere).
- **The operator** (pre-provisions the first people; the platform console arrives with step 7).
- **An AI client** (Claude Code, claude.ai) acting as a Member through MCP.

## Use case

1. A person signs in. If they belong to one company they land in it; if to several they choose one;
   if to none they see that they have not been added to a company yet.
2. Inside a company they work as today: Organisations, scenarios, states, structure, timeseries,
   predictions, customers, AI change sets, all under that company's address
   (`/tenants/<company>/…`).
3. An Admin or Owner adds a person to the company by email, changes a member's role, and removes a
   member. An Owner is needed to appoint or remove another Owner; the last Owner cannot be removed.
4. Opening another company's address, or an Organisation or Customer id from another company,
   behaves exactly like opening something that does not exist (404). The same holds for AI clients.
5. A person who belongs to two companies sees only the chosen company's data at any moment and can
   switch from the company selector.

## Acceptance criteria

- [ ] After migration the existing data belongs to one company; every existing `admin` is an Admin (the earliest one the Owner) and every `consultant` a Member; nobody loses access; Organisation names stay unique within a company only.
- [ ] A signed-in person lists their companies; a company's routes require membership; a non-member gets 404 for the whole company address, a Member 403 for Admin-only actions.
- [ ] Every route for Organisations, scenarios, states, structure, timeseries, predictions, change sets and customers lives under `/api/v1/tenants/{tenant_id}/…`, and a test per route family shows that another company's data answers 404 and cannot be changed.
- [ ] PostgreSQL row-level security on every company-owned table enforces the same isolation: with no or another company's context a table returns no rows and refuses writes; the default Metamodel stays readable by all and writable by nobody through the application.
- [ ] A person Shadow does not know, with a verified Authentik identity, gets an account with no company at first sign-in and sees the "no company yet" page; nothing of any company is visible to them.
- [ ] Admins and Owners manage members (add by email, change role, remove) with the rules of the domain model; the last Owner is protected; every change is audited.
- [ ] The web application uses the company address, shows a company selector, and shows administration only to Admins and Owners.
- [ ] MCP keeps working for a person with exactly one company (that company is implicit); with several companies the tool answers with a clear error until step 3b adds an explicit company argument. MCP data is isolated like the web's.
- [ ] The prediction worker processes requests of every company, each under that company's context, and never mixes results.
- [ ] `users.role` no longer decides anything and is removed at the end of the step; the global Users API is replaced by the company's members API.

## Not in this version

- Invitations by email, accepting an invitation, leaving a company, ownership transfer with acceptance (step 6).
- Creating a company by self-service, billing, seats, subscription state (steps 5 and 6); here a company exists only through the migration, the dev seed and the operator.
- Company deletion, export and purge (step 8); renaming or other settings pages (step 6, `083C`).
- Per-Organisation permissions (a Member sees every Organisation of the company).
- Platform accounts, the console and support access to a company's data (step 7).
- An explicit company argument and MCP switches per company (step 3b).
- Finnish text for the new screens (i18n arrives with step 4's frontend work).

## Domain terms

- **Company / Tenant**: the subscribing company; code name `tenant`, shown as "Company" (ADR-016). Not an **Organisation**.
- **Membership**: a person's belonging to a company with a **Role** (`owner`, `admin`, `member`).
- **Tenant context**: the company and person a database transaction acts for.
- **Account class**, **Account**: as in ADR-016 and `CONTEXT.md`.

See `domain-model.md` for the rules, lifecycle and authorization matrix.

## Decisions (settled with the plan's recommendations, 2026-11-06)

| # | Decision |
|---|---|
| D1 | *To confirm:* the company the existing data is migrated to is named **"Reflector Oy"** (changeable by SQL until step 6 gives Owners a settings page); no other value is known to the repository. |
| D2 | Company identifiers are UUIDs in routes and URLs; there is no slug. |
| D3 | Migration: the earliest `admin` user becomes Owner, other `admin`s Admin, `consultant`s Member (ADR-016 §8). A database with no users gets no company; the dev seed and `bootstrap_admin` create one. |
| D4 | A verified Authentik identity Shadow does not know gets an account with no company at first sign-in (this replaces ticket 04's "never create"; guarded by the verified email and Authentik's invitation gate); setting `AUTH_CREATE_ACCOUNTS=false` restores refusal. |
| D5 | Routes `/api/v1/tenants/{tenant_id}/…`; web `/tenants/:tenantId/shadow/:orgId/*`; `/` leads a one-company person straight in. |
| D6 | The global Users API and `users.role` are replaced by the company's members API; `users.role` is dropped by the last ticket, after nothing reads it. |
| D7 | Until invitations (step 6) an Admin adds a person by email (creating the account if it does not exist; the person still needs an Authentik invitation to sign in). |
| D8 | Isolation in the database: `tenant_id` on every company-owned table, filled by the column default (company context) or, for child rows, by a trigger from the parent; one policy per table on `tenant_id`; a worker scope for the prediction worker. |
| D9 | Routes run under the application role through a per-request session whose role and context are re-applied at every transaction start (services commit more than once). |
| D10 | MCP interim: the implicit company for a person with one membership; error otherwise. |
| D11 | Membership and role changes, and account creation at sign-in, are audited with the platform audit log. |
| D12 | Tenant lifecycle states other than `active` (pending, pending deletion, canceled, read-only) are added by steps 5 and 8; here a tenant is `active`. |

## Documentation effects

- [x] `docs/admin/` — company roles and member management (tickets 03, 08)
- [x] `docs/user/` — companies, selector, no-company page (ticket 09)
- [x] `docs/operations/` — local development, testing (tickets 01, 10)
- [x] `docs/architecture/` — data model, database (RLS), domains (`TENANTS.md`, `USERS.md`, `ORGANISATIONS.md`, `CUSTOMER.md`, `AI.md`), overview, diagrams (tickets 01–10)
- [x] `docs/design/` — company selector and administration visibility (ticket 09)
- [x] `docs/adr/` — ADR-016 amended with the RLS mechanics (ticket 10)
- [x] `CONTEXT.md` — Tenant/Company, Membership, Role move to *Language* (ticket 01)
- [x] `.env.example` — `AUTH_CREATE_ACCOUNTS` (ticket 03)
- [ ] `docs/gdpr/`, `docs/legal/` — no effect in this step

## Open questions

- D1 (the company name) is the only item to confirm. Everything else follows ADR-016 and the plan.
