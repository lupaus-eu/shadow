# Technical design: Sign in with Authentik

Status: accepted

Implements the PRD (`PRD.md`), ADR-017 and ADR-0023 (both `accepted`). Source
of the copied parts: Yearclock `../yearclock` (commit `6848e72`): `authentik/`,
`docker-compose.yml`, `docs/runbooks/authentik-*.md`, `backend/app/oidc.py`.

## Current and target state

- **Current:** `backend/app/core/config.py` validates OIDC settings against
  `login.microsoftonline.com` and a tenant-specific Entra authority.
  `AuthlibOidcProvider` is provider-neutral (discovery, S256 PKCE, nonce, ID-token
  validation, `RS256` only). Login never creates a user: `resolve_identity` links
  by guarded email to a pre-provisioned `users` row. Sessions (`auth_sessions`)
  are server-side with hashed ids, `__Host-` cookies and CSRF. Local development
  needs a private Entra registration (`scripts/setup-local-entra.sh`,
  `.env.entra.local`). `users.role` is `admin` or `consultant`.
- **Target:** the same code authenticates against Authentik; no Entra anywhere.
  The local stack runs Authentik (server, worker, one-shot configuration) behind
  Caddy at `https://id.app.localhost`; blueprints create the web OIDC application,
  the MCP provider, the strong-authentication flows and the dev users. Accounts
  gain `account_class` and `locale`.

## Domain

Identity (Authentik) and account (`users`) stay separate. A `user_identities`
row links `(issuer, subject)` to a `users` row; the web client issuer is
`https://id.app.localhost/application/o/shadow/` (`per_provider`). Authority is
unchanged in this step (global `role`); tenants come in step 3 (ADR-016).

## Authentik configuration (blueprints in `authentik/`)

| File | Content | Source |
|---|---|---|
| `blueprints/shadow-identity-flows.yaml` | Enrollment behind an invitation stage (`AUTHENTIK_ENROLLMENT_OPEN`), email verification recorded as the verified ADDRESS in `shadow_verified_email`, a second-factor stage bound to enrollment before the login stage, TOTP and passkey (resident key, user verification required), mandatory MFA at login, recovery by email plus factor | copy |
| `blueprints/shadow-application.yaml` | `email` scope mapping (`email_verified` true only while the user's address equals the address recorded in `shadow_verified_email`); confidential web provider "Shadow" (auth code, implicit consent, exact redirect `OIDC_REDIRECT_URI`, exact logout URIs `FRONTEND_URL`), application `shadow` | copy |
| `blueprints/shadow-mcp-application.yaml` | Confidential provider "Shadow MCP" (`MCP_OIDC_CLIENT_ID/SECRET`), auth code and refresh token, explicit consent, strict redirect URIs `https://claude.ai/api/mcp/auth_callback` and `https://claude.com/api/mcp/auth_callback`, a regex redirect `http://(localhost|127\.0\.0\.1):[0-9]+/callback` for local clients such as Claude Code, scopes `openid profile offline_access`, `hashed_user_id`, `per_provider`; application `shadow-mcp` | copy, extended |
| `blueprints/shadow-brand.yaml` + `.css` | Brand title and stylesheet for the sign-in pages (minimal) | copy, reduced |
| `dev/shadow-dev-users.yaml` | Dev users (admin and member, verified email, TOTP preconfigured with a fixed dev secret, password from `AUTHENTIK_DEV_USER_PASSWORD`); mounted only by the local Compose project | new |
| `configure.sh` | Idempotent apply with fingerprint marker | copy |

The dev users are `consultant@example.local` and `admin@example.local`, the
emails that the development seed (`db/init/002_seed_development_data.sql`) already
provisions, so their first sign-in links to the seeded accounts. MFA stays enforced for them; their TOTP secret is a documented
dev-only value so that a developer can sign in without a phone.

## Database

- Migration **025** `025_add_auth_session_id_token`: `auth_sessions.id_token TEXT`
  NULL, kept only to send `id_token_hint` on logout and deleted with the session.
  Down drops it.
- Migration **026** `026_add_user_account_class_and_locale`: `users.account_class`
  (`customer` or `platform`, default `customer`, NOT NULL, check) and
  `users.locale` (`fi` or `en`, default `en`). Existing rows become `customer`.
  Down drops both.
- The Authentik logical database `authentik` is created by the one-shot
  `authentik-db-init` job (`docker/postgres/` script copied from Yearclock) in the
  same PostgreSQL container with its own role; not touched by Shadow migrations.

## Backend

- `core/config.py`: `validate_auth_configuration` drops the Entra host and tenant
  rules. New rules: `OIDC_ISSUER` and `OIDC_DISCOVERY_URL` are `https` (local
  `https://id.app.localhost` allowed), same origin, issuer path matches
  `/application/o/<slug>/`, no userinfo/query/fragment, `per_provider` issuer. New
  `OIDC_INTERNAL_BASE_URL` (optional `http://` host inside Docker): discovery and
  token calls go there with `Host` and `X-Forwarded-Proto` set to the public
  origin (Yearclock `oidc.py:_internal_url`/`_internal_request_headers`); metadata
  must still name the public issuer. `OIDC_REQUIRE_VERIFIED_EMAIL` defaults to
  `true`.
- `api/v1/auth/provider.py`: logout builds the Authentik `end-session/` URL with
  `id_token_hint` and an exact `post_logout_redirect_uri`; the validated ID token
  string is returned to the session creation.
- `api/v1/auth/service.py`: `create_session` stores the ID token; `resolve_identity`
  keeps guarded linking and, for an unknown verified email, raises the existing
  `AuthenticationError` (no account is created). The log redaction of
  `session_state` is dropped with Entra.
- `account_class`: session dependencies `require_customer_session` (existing business
  routes) and `require_platform_session` (placeholder for step 7, returns 403 for
  customers); `audience=customer|platform` is accepted by `/auth/login` and carried
  through the login transaction, only `customer` can complete today.
- MCP is untouched; `MCP_OIDC_*` settings are only read by the blueprint.

## Local runtime

- Compose adds `authentik-db-init`, `authentik-server`, `authentik-worker`,
  `authentik-config-init`, a dev-only blueprint mount, Authentik mail to Mailpit
  (`mailpit:1025`), fixed local IPs on the existing `local` network, and
  `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS` limited to the Caddy and backend peers
  (`172.28.59.2/32`, `172.28.59.3/32`; the backend's internal OIDC calls say the public scheme). The retired `authentik_*` volumes are replaced by the new
  ones; the cleanup is in the runbook, not automated.
- `local/Caddyfile` gains the host `id.app.localhost` (reverse proxy to
  `authentik-server:9000`, own CSP), the certificate (`scripts/setup-local-app-tls.sh`)
  gains that name, and the access log redaction covers the OIDC callback
  parameters.
- `make dev-up` no longer runs `scripts/setup-local-entra.sh`; the backend gets its
  `OIDC_*` values from `.env` defaults for the local Authentik.
- Production Compose, edge Caddy, Scaleway SMTP and backups of the Authentik
  database are step 086A/B; not in this design.

## Frontend

No new screens. The login redirect and the logout redirect already follow the
backend; the only change is removing Entra wording from the sign-in and error text.

## Authentication and authorization

Step 7 will also need an unsafe-request (CSRF and origin) variant of `require_platform_session`. Unchanged in this step: every business route requires a session; `admin` manages
Users; `admin` and `consultant` use every Organisation. A person without an
existing account gets the existing generic sign-in failure (`Identity resolution
failed`, which does not reveal whether an account exists), and nothing is created.

## Errors

Authentik errors during authorization (denied consent, unverified email) return to
the existing login error page with the stable codes already in use; an unverified
email gets the same generic `Identity resolution failed` as an unknown person (the sign-in
failure never reveals which). Discovery failures fail closed at login with
`503`, never fall back to another issuer.

## Testing

- Backend: config validation (accepted and rejected issuers, internal base URL
  rewrite, origin mismatch), provider (internal discovery, issuer mismatch, ID
  token, `id_token_hint` logout URL), service (linking by verified email, unverified
  refused, unknown refused and creating nothing, ID token stored and deleted),
  dependencies by account class, and migrations 025 and 026 (up, down, defaults).
- Authentik: the blueprints are applied in a real Authentik 2026.8.5 container
  (`make dev-up`); a script `scripts/verify-authentik-local.sh` checks that the web
  and MCP discovery documents and JWKS are served, that the MCP provider issuer
  differs from the web issuer, and that the redirect URIs of both providers are as
  declared (Authentik API with the bootstrap token).
- Browser/E2E: sign-in, enrollment through an invitation, TOTP and passkey (virtual
  authenticator), recovery, sign-out and the refused unknown person, as QA evidence
  in `docs/operations/qa/AUTHENTICATION-QA-CHECKLIST.md`.
- MCP provider: a real authorization-code sign-in with a pre-registered client
  (Claude Code with `--client-id/--client-secret/--callback-port`, and MCP Inspector;
  the claude.ai connector is recorded as untestable locally) recorded as QA
  evidence; the access token's `aud` equals the client id and `iss` the MCP
  issuer.
- Architecture: `docker compose config`, production compose verification (OIDC
  values), `make diagrams`.

## Configuration

New: `AUTHENTIK_VERSION`, `AUTHENTIK_SECRET_KEY`, `AUTHENTIK_POSTGRES_*`,
`AUTHENTIK_BOOTSTRAP_PASSWORD`, `AUTHENTIK_ENROLLMENT_OPEN`, `AUTHENTIK_BASE_URL`,
`AUTHENTIK_THEME_CSS_URL`, `AUTHENTIK_DEV_USER_PASSWORD`, `OIDC_INTERNAL_BASE_URL`,
`MCP_OIDC_ISSUER` (read in step 3b), `MCP_OIDC_CLIENT_ID`, `MCP_OIDC_CLIENT_SECRET`,
the web client of the blueprint `LOCAL_OIDC_CLIENT_ID`/`LOCAL_OIDC_CLIENT_SECRET`/`LOCAL_OIDC_REDIRECT_URI` (kept apart from the backend's `OIDC_*` while Entra files exist). Removed: everything in
`.env.entra.example`. Production values and the production env contract
(`docs/architecture/deployment.md`) are updated by ticket 05 (names) and step 086A
(deployment).

## Architecture effects

New containers (three) and a second host name in the local stack; a second OIDC
issuer for the MCP provider (verified in step 3b); `users` and `auth_sessions`
gain columns. No change to production runtime.

## Documentation effects

- [x] Update `docs/admin/` — invitations and recovery for operators (ticket 01)
- [x] Update `docs/operations/` or `docs/runbooks/` — Authentik local, invitations, upgrade, local development, QA checklists
- [x] Update `docs/architecture/` — diagrams (`component-authentication-topology`, `sequence-oidc-login`), deployment, stack, overview, `domains/USERS.md`, `data/DATA-MODEL.md`, `DATABASE.md`
- [x] Add or update `docs/adr/` — ADR-017, ADR-0023 (written), ADR-004/006/013 notes (ticket 05)
- [x] Update `CONTEXT.md` — account class (ticket 04)
- [x] Update `.env.example`

## Options and decision

| Option | Decision |
|---|---|
| Keep Entra for the company next to Authentik | Rejected (ADR-017). |
| Create accounts at first login now (PLAN 079C) | Rejected: until tenants exist every account sees all data; moved to 080B. |
| Own PostgreSQL instance for Authentik | Not needed: Authentik 2026.8.5 runs on the application's PostgreSQL 18 container (verified in ticket 01, 2026-11-06); same container, own database (Yearclock ADR-0011). |
| Verify MCP tokens in this step | No: step 3b; here only the provider and a real sign-in. |
| Dynamic client registration for MCP | Rejected (ADR-0023). |

## Tickets

01 authentik-local-stack (079A) → 02 mcp-provider (new, from 080H's blueprint) →
03 oidc-against-authentik (079B) → 04 account-class-and-audience (079C, reduced) →
05 remove-entra (079D). Tickets 02 and 03 can run in parallel after 01.
