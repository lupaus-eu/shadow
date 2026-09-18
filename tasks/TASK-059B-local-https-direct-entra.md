# TASK-059B Local HTTPS And Direct Entra

## Source Plan And Dependencies

Approved UpCloud/Caddy/direct-Entra amendment in
[ADR-013](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md).
Depends on [TASK-059A](TASK-059A-shared-entra-local-https-architecture.md).
This replaces the earlier local-HTTPS/Authentik-federation specification.
Implementation follows documentation review on its own task branch.

## Goal

Develop at `https://app.localhost`, with local Caddy routing Vite and FastAPI
and FastAPI connecting directly to the shared Entra registration. Retire the
local Authentik runtime without losing existing application data or identities.

## Requirements

- Add loopback-only Caddy HTTPS at port 443 for `app.localhost`. Route `/api`
  and `/api/*` directly to backend HTTP; route remaining paths to Vite, including
  HMR WebSockets using the HTTPS origin and appropriate WSS port. Keep exposed
  development ports loopback-only and Vite host allowances narrowly scoped.
- Align `PUBLIC_ORIGIN`, `APP_URL` and `APP_ALLOWED_ORIGIN` to
  `https://app.localhost`; use secure, HttpOnly, host-only application cookies,
  existing SameSite/Path policy and exact CSRF/Origin checks.
- Preserve strict Host handling, fixed/sanitized forwarded headers and narrowly
  trusted actual Caddy peers. Retain security headers/CSP compatible with HMR;
  redact callback `code`, `state`, `error`, `error_description` values in logs.
- Separate application TLS generation/trust tooling from Authentik. Reuse valid
  local CA material where possible; inspect validity and hostname coverage,
  explain renewal/trust errors, and never overwrite valid keys unnecessarily.
  Mount only required leaf certificate/key into Caddy, not the CA private key.
- Remove Authentik services, federation overlay/configuration, runtime setup
  dependencies and obsolete helper entrypoints from the active local workflow.
  Update checks and documentation with equivalent direct-OIDC boundary coverage.
  Preserve application data, old Authentik volumes and identity rows. No
  `down -v`, volume deletion, database reset or automatic issuer rewriting.
- Configure the existing single-tenant confidential Web Entra registration
  directly in FastAPI with a development-only secret. Callback is
  `https://app.localhost/api/v1/auth/callback`; post-logout return is
  `https://app.localhost/login`. Production uses its distinct origin/secret.
- Use exact tenant-specific issuer and `openid profile email`, no Graph calls,
  `OIDC_REQUIRE_VERIFIED_EMAIL=false`, and existing guarded first-link checks.
  Missing/invalid config must produce actionable, credential-safe setup errors;
  do not silently fall back to Authentik or bypass authentication. Ordinary
  interactive local login requires tenant access; simulated tests do not.
- Document private/ignored secret input/storage, rotation and operator steps.
  Real tenant writes, callback cleanup and unused Graph permission removal
  require authorized setup with remaining-consumer checks under F.
- Provide explicit **local-only** provisioning of a designated Entra admin,
  including a development database already containing seeded Users. Specify a
  safe local invocation/guard and validate identity input and active-email
  uniqueness. Reuse User validation and deliberate operator intent; fail safely
  on ambiguous, conflicting or deleted-account cases. Do not commit personal
  email or put it in logs/command arguments. Do not create Users during login.
- Keep D's production bootstrap restricted to an entirely empty users table;
  this local provisioning path must not weaken that contract or become a public
  endpoint. Preserve seeded users and unrelated existing users without resets
  or implicit role changes. Document intentional selection/provisioning of the
  local administrator and verify its database role.
- Preserve old Authentik `(issuer, subject)` bindings unchanged. A new Entra
  identity links through the normal guarded flow to a matching pre-provisioned
  active User; no identity copy/relabel/rebinding or cross-database migration.
- Retain database authorization, sessions/revocation, CSRF, audit behavior and
  one prediction worker. Remove obsolete Authentik startup dependencies without
  creating a new application/provider startup cycle.

## Acceptance Criteria

- [ ] Local HTTPS, secure cookies, direct API routing and Vite HMR work.
- [ ] Exact Host/proxy trust, CSRF/Origin, security headers and callback-log
      redaction retain effective coverage.
- [ ] Local Compose/setup has no Authentik runtime dependency; existing data,
      old volumes and old identity ownership are preserved.
- [ ] Valid local CA material can be reused; trust/renewal and missing Entra
      configuration errors are actionable without leaking credentials.
- [ ] Explicit local-only admin provisioning works on fresh and already-seeded
      development databases without changing D's empty-table restriction.
- [ ] Simulated direct-Entra OIDC validates claim policy and guarded linking,
      and rejection cases create no User, identity or session.
- [ ] Real-Entra browser verification is separately recorded with date, commit,
      tester, environment and redacted result, or explicitly marked pending
      authorized provider setup. Mock tests do not count as that verification.
- [ ] No production operations, provider mutations, schema changes, real personal
      data in the repository or deletion of existing volumes.

## Testing

Read `docs/TESTING.md` and use simulated OIDC plus disposable PostgreSQL for
repeatable automated tests without tenant credentials. Cover exact issuer,
missing email, absence of `email_verified`, existing/new identity linking,
pre-provisioning on a populated dev database, non-admission, roles, sessions,
CSRF, logout, header spoofing and callback-log redaction. Verify local TLS/HMR
and failure diagnostics. Run relevant backend Ruff/pytest/pyright, frontend
lint/tests/build, Compose/configuration and affected setup-script checks.

Record live browser login, callback, guarded first-link, session, role and
logout separately using designated Entra accounts after authorized setup. If
unavailable during B, retain an explicit outstanding verification item for E/F;
this must be completed before rollout, not presented as a passed B check.

## Documentation And Scope Limits

Update local setup, environment examples, authentication QA and runtime status
in architecture/agent docs. Explain current Entra prerequisites and local-only
provisioning without committing personal input. Read ADR-004/013,
`docs/domains/USERS.md` and `docs/concepts/USER.md` before identity changes.

Production runtime belongs to G; seed and production bootstrap belong to C/D;
UpCloud resources, tenant/DNS writes and release belong to authorized F.
No new dependencies without approval. Record eventual Step 13 reviews under
`docs/ai-reviews/TASK-059B/`.
