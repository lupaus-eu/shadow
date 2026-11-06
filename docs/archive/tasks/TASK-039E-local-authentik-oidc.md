# TASK-039E Local Authentik OIDC Environment

Status: Planned

Supersession note: ADR-006 and TASK-040 replace this task's original local
`http://auth.localhost:9000` endpoint with `https://auth.localhost:9443`.

## Source Plan

Approved TASK-039 plan: daily local development uses a repository-managed,
Dockerized Authentik OIDC provider while integration testing uses real Entra.
Authentik must exercise the same OIDC application contract without pretending
to reproduce every Entra-specific claim.

## Goal

Provide a reproducible local identity environment that starts with Shadow's
normal Docker workflow, needs no production credentials, and supports a real
browser login against the backend endpoints from TASK-039C.

## Requirements

- Depends on accepted ADR-004. Full login smoke verification additionally
  depends on TASK-039C and TASK-039D.
- Extend local `docker-compose.yml` with a pinned supported Authentik 2026.5
  patch image, server and worker plus a dedicated Authentik PostgreSQL service
  and volumes.
- Do not share Shadow's application database/database user with Authentik,
  expose the Authentik database port, mount the Docker socket, or add Authentik
  to production/Coolify manifests.
- Make Authentik available to the host browser as
  `http://auth.localhost:9000` and give its server that Docker-network alias so
  the exact issuer is reachable from both the browser and backend container.
  Bind the published host port explicitly to `127.0.0.1`; do not expose local
  Authentik on the developer machine's external interfaces.
- Configure the backend locally with the per-provider discovery URL for the
  Shadow Authentik application, the local public origin
  `http://app.localhost:5173`, and callback
  `http://app.localhost:5173/api/v1/auth/callback` through the existing Vite
  proxy. Use `app.localhost` instead of bare `localhost` so Shadow's host-only
  development cookies are not sent to unrelated services on `localhost`.
- Add version-controlled Authentik blueprints/configuration that provision:
  - a Shadow application and confidential OAuth2/OIDC provider
  - exact callback and post-logout URIs
  - per-provider issuer mode
  - only `openid profile email` scopes
  - claim mappings required by the backend normalized identity contract
- Do not map Authentik groups to Shadow roles or emit Entra-specific `oid` or
  `tid` as application requirements.
- Seed at least one consultant and one admin identity whose verified emails
  match the application development users. Ensure the application, not the
  provider, remains the role source.
- Keep client secret, Authentik secret key, bootstrap token/admin credential and
  user passwords out of Git. Add a documented setup command/script that
  generates a gitignored local environment file; commit only placeholders.
- Prefer password hashes for bootstrap users. Never commit a reusable plaintext
  credential, even if described as development-only.
- Pin the exact image patch/digest selected during implementation and document a
  deliberate upgrade procedure; do not use `latest` or a floating major tag.
- Add health/readiness dependencies sufficient to avoid backend login attempts
  before Authentik is ready, without coupling backend process startup to
  Authentik migrations or internals.

## Acceptance Criteria

- [ ] A fresh developer checkout can generate local secrets and start the full
      stack using documented commands.
- [ ] Browser and backend observe the same exact Authentik issuer.
- [ ] Shadow is accessed through `app.localhost`, Authentik is bound only to
      loopback, and neither service receives the other's host-only cookies.
- [ ] Blueprint provisioning is repeatable and uses exact redirect URIs.
- [ ] Consultant and admin test identities complete real login and bind only to
      matching pre-created Shadow users.
- [ ] Tokens contain the standard claims needed by the adapter and do not grant
      application roles.
- [ ] No Authentik service, credential or database appears in production
      manifests.
- [ ] No Docker socket is mounted and no secret is tracked by Git.

## Out Of Scope

- Production Authentik.
- Entra tenant/app registration.
- Provider group authorization, MFA parity or Conditional Access simulation.
- Automated browser E2E tooling or a new frontend dependency.
- Application auth behavior beyond fixes strictly needed for documented
  provider interoperability; such fixes belong in TASK-039C/D.

## Implementation Notes

- Read ADR-004, Authentik's current Docker Compose, automated-install,
  blueprint and OAuth2/OIDC provider documentation, plus local-development and
  testing docs.
- Authentik documents a minimum local footprint of two CPU cores and 2 GB RAM;
  record this and give developers a documented way to stop the identity stack.
- Do not copy an upstream Compose file blindly. Keep only the services,
  settings and mounts justified by this local use case.

## Testing

Required:

- [ ] `docker compose config` validation
- [ ] Fresh-volume bootstrap test
- [ ] Authentik health, discovery and JWKS smoke checks
- [ ] Manual consultant/admin browser login and logout
- [ ] Guarded-link failure with an unmatched email
- [ ] Secret and production-manifest inspection

Commands must include the final documented Compose startup/teardown and smoke
requests. Destructive fresh-volume verification must target explicit disposable
test volumes, not the developer's normal volumes.

## Documentation

Update `.env` examples/ignore guidance, `docs/operations/local-development.md` and
`docs/operations/testing.md`. Final architecture diagrams and cross-environment runbook are
owned by TASK-039G.

## Notes For AI Agent

- Ala commitoi salaisuuksia tai testisalasanoja.
- Ala lisaa Authentikia production Compose -tiedostoihin.
- Ala mounttaa Docker socketia Authentik-workerille.
