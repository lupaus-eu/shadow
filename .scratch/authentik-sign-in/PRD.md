# Feature: Sign in with Authentik

Status: accepted

Step 2 of the SaaS plan (`.scratch/saas-platform/PLAN.md`, tasks 079A–D). Open
questions were settled with the plan's recommendations on 2026-11-06 (see
*Decisions*); the user asked that the Authentik provider for MCP be part of
this step.

## Goal

People sign in to Shadow through Shadow's own Authentik instance, with a
passkey or a second factor, instead of Microsoft Entra. This is the identity
base the tenant, billing and platform work builds on. Existing Users keep their
accounts, data and history. Authentik also gets the OIDC provider that MCP
clients will use later (ADR-0023), so the identity setup is done once.

## User

- **A person invited to Shadow** (a future Member, Admin or Owner): enrolls,
  verifies their email, sets up a passkey or authenticator, and signs in.
- **An existing User** of today's Shadow (`admin` or `consultant`): signs in
  with Authentik and lands in their existing account.
- **The operator** (the person who runs Shadow; later the Platform Admin):
  issues invitations in Authentik and follows the runbooks.
- **A developer**: starts the local stack and signs in with seeded dev users.
- **An anonymous visitor**: reaches only the sign-in page.

## Use case

1. The operator creates an Authentik invitation for an email address and sends the link.
2. The invited person opens it, registers, verifies the email, and must set up a
   passkey or TOTP before sign-in completes.
3. They are sent to Shadow. If Shadow already knows the verified email (an existing
   User), the new identity is linked to that account; otherwise Shadow refuses
   sign-in for now (accounts for new people arrive with tenants, step 3).
4. Later sign-ins use the passkey (or password plus a second factor).
5. Signing out ends the Shadow session and the Authentik session.
6. A person who lost access recovers it through email plus a second factor.
7. A developer runs `make dev-up` and signs in at `https://app.localhost` as a seeded dev user.
8. The operator sees the "Shadow MCP" application in Authentik; its client id and
   secret are ready for the MCP work in step 3b. MCP clients keep working through
   today's OAuth server until then.

## Acceptance criteria

- [ ] Sign-in at Shadow redirects to Authentik at `https://id.app.localhost` (local) and works end to end with a passkey or password plus TOTP; a user without a second factor cannot finish signing in.
- [ ] Enrollment requires an invitation when `AUTHENTIK_ENROLLMENT_OPEN=false`, and verifies the email; Shadow accepts only verified emails (`email_verified`).
- [ ] An existing User signing in for the first time through Authentik is linked by verified email to their existing account and sees their data; a person with no existing account is refused with the existing generic sign-in failure (no account is revealed) and no account is created.
- [ ] Sign-out ends both sessions; sessions, cookies and CSRF protection behave as before.
- [ ] No Microsoft Entra configuration, script, documentation or test remains (history in `docs/archive/` and `docs/ai-reviews/` excepted); `OIDC_*` settings accept the Authentik issuer and reject unsafe ones.
- [ ] `make dev-up` brings up Authentik, Mailpit and the application; dev users and the Shadow OIDC application are created from blueprints; no manual console steps.
- [ ] The Authentik blueprint "Shadow MCP" creates a confidential provider and application (strict redirect URIs for claude.ai and claude.com, the loopback pattern for Claude Code, explicit consent, PKCE, `sub_mode: hashed_user_id`); its discovery document and JWKS are served; a real authorization-code sign-in with a pre-registered client is demonstrated with Claude Code or MCP Inspector (QA evidence), without changing the existing MCP behaviour.
- [ ] Accounts carry an account class (`customer` or `platform`) and a locale, and session dependencies can tell the classes apart, without changing what current Users can do.
- [ ] Runbooks exist for local Authentik, invitations and upgrades; the authentication diagrams show Authentik.

## Not in this version

- Tenants, memberships, creating accounts for new people, and removing `users.role` (step 3); a person without an existing account is refused until then.
- The platform console login (`audience=platform` flow) and platform enrollment (step 7); this step only prepares the account class and the dependency split.
- MCP token verification, tenant binding of MCP, and removal of Shadow's own OAuth server (steps 080I–080K).
- Production Authentik (compose, edge host `id.shadow.lupaus.eu`, Scaleway SMTP, backups) and deleting the Entra app registration (steps 086A, 087B); the local stack and blueprints are production-ready, but nothing is deployed.
- Finnish and English sign-in pages and a full brand design; a minimal brand only.
- Tenant invitations to join a company (step 6).

## Domain terms

- **Identity**: a person's Authentik account, linked to a Shadow **account** (`users` row) by issuer and subject.
- **Invitation** (Authentik): a link the operator creates that allows one enrollment. Not the same as a tenant invitation (step 6).
- **Account class**: `customer` (signs in to the application) or `platform` (operators; the console, step 7).
- **Web client / MCP client**: the two OIDC clients of Shadow in Authentik; the MCP one is for AI clients.

Account class, membership and tenant are defined in ADR-016; **Organisation** keeps its meaning in `CONTEXT.md`.

## Decisions (settled with the plan's recommendations, 2026-11-06)

| # | Decision |
|---|---|
| D1 | Own Authentik instance for Shadow, pinned to 2026.8.5; ADR-017. |
| D2 | Hosts: `id.app.localhost` locally, `id.shadow.lupaus.eu` in production. |
| D3 | Closed enrollment by invitation in production, open locally (P9). |
| D4 | MFA mandatory, passkeys preferred, recovery by email plus a factor. |
| D5 | Authentik in a separate logical database `authentik` in the same PostgreSQL container; if Authentik 2026.8 cannot use PostgreSQL 18, the ticket records it and uses a dedicated PostgreSQL 17 container for Authentik only. |
| D6 | Authentik mail via Mailpit locally and Scaleway Transactional Email (SMTP) in production. |
| D7 | Existing Users are linked by guarded verified-email linking; no account creation before tenants (changes PLAN task 079C, whose creation step moves to 080B, because today every account sees all data). |
| D8 | The MCP provider "Shadow MCP" is created now (ticket 02); token verification stays in 3b. Authority will come from tenant membership, not OAuth scopes (ADR-0023). |
| D9 | Dev users come from a dev-only blueprint with the password from `AUTHENTIK_DEV_USER_PASSWORD` in `.env.example`. |
| D10 | Logout uses `id_token_hint` stored with the session; logout redirect URIs are exact. |
| D11 | A minimal brand (application stylesheet, title) is included; no Finnish translations of Authentik pages. |

## Documentation effects

- [x] `docs/admin/` — operator guidance for invitations and recovery (ticket 01)
- [x] `docs/operations/` or `docs/runbooks/` — `authentik-local.md`, `authentik-invitations.md`, `authentik-upgrade.md`; `local-development.md`; QA checklists (tickets 01, 02, 05)
- [x] `docs/architecture/` — authentication topology and OIDC sequence diagrams, deployment, stack, overview, `USERS.md`, data model (tickets 01, 03, 04, 05)
- [x] `docs/adr/` — ADR-017 and ADR-0023 (written with this PRD), updates to ADR-004, 006, 013
- [x] `CONTEXT.md` — account class, platform account (ticket 04)
- [x] `.env.example` — Authentik, OIDC and MCP client settings (tickets 01, 02, 03)
- [ ] `docs/user/`, `docs/gdpr/`, `docs/legal/`, `docs/design/` — no effect in this step (Authentik becomes a processor of identity data when production adopts it; recorded with step 086A)

## Open questions

None. Verification items inside tickets: PostgreSQL 18 with Authentik (ticket 01), Claude Code and the claude.ai connector against the MCP provider (ticket 02).
