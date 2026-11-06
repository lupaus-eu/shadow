# TASK-039G Production Authentication Deployment And QA

Status: Planned

## Source Plan

Approved TASK-039 plan amended by ADR-005: expose the completed application
through one HTTPS production origin, verify the release boundary locally and
define the human-controlled production deployment, smoke and rollback workflow
without performing a production release.

## Goal

Complete the deployable same-origin frontend/backend topology and its local QA
evidence, remove the obsolete staging and Entra development-tenant model, and
provide a safe production-only Entra release runbook.

## Requirements

- Depends on TASK-039A through TASK-039F.
- Add the pinned official Caddy production frontend target selected by ADR-004:
  - build the React SPA reproducibly and serve SPA history fallbacks
  - reverse-proxy `/api` to the backend without exposing backend ports
  - keep the repository-owned Caddyfile provider-neutral
  - listen only on the internal unprivileged HTTP port used by Coolify; the
    Coolify edge terminates public TLS
  - reject public Host values other than the configured application host
  - overwrite untrusted forwarded Host/proto headers and derive client address
    only through the documented Coolify-edge and Caddy-peer trust boundaries
  - provide an image health check without adding an application dependency
- Extend provider-neutral release Compose and the thin Coolify manifest so the
  frontend is the only public service and the backend/migration job retain
  ADR-003's immutable-image and startup-gating behavior.
- Build the frontend and backend as matching, immutable commit-specific release
  artifacts. Start backend only after the one-shot migration succeeds and
  frontend only after backend health succeeds.
- Keep Authentik absent from release/Coolify configuration.
- Require production auth configuration and secrets with no fallback: exact
  public origin and Host, tenant-specific discovery URL and issuer,
  confidential client ID and secret, proxy trust CIDRs, and exact callback and
  logout URIs.
- Inject OIDC configuration only into the backend API service. Migration must
  continue to require only database configuration and must not initialize OIDC.
- Define exactly two application environments:
  - local development/testing with repository-managed Authentik; TASK-040 may
    optionally federate that Authentik instance to Entra
  - production with Shadow connecting directly to the same organisation's
    single-tenant Entra directory
- Require separate confidential Web app registrations in that Entra tenant:
  one restricted local-federation registration and one production
  registration. Do not share secrets or callback sets between them.
- Do not register production Shadow as an SPA or request Graph permissions,
  provider groups, app roles or `offline_access`. Production requests only
  `openid profile email`; TASK-040 owns any minimal Graph permission required
  by Authentik's local Entra source.
- Keep Entra secrets in approved secret management. Do not create tenant
  resources, retrieve credentials or deploy from this task.
- Preserve Shadow's guarded first-link contract: missing email or no unique
  active matching User fails generically; exact `(issuer, subject)` is permanent
  after linking; the database remains the only role source.
- Disable production CORS. Keep backend, migration and database ports internal.
- Redact `code`, `state`, `error` and `error_description` query values in Caddy
  access logs and retain credential-header redaction.
- Enforce the reviewed HSTS, referrer, nosniff, frame and CSP policies against
  the built application.
- Add ADR-005, partially superseding only the environment/deployment portions
  of ADR-003 and ADR-004 while preserving their historical text.
- Update active architecture, Users/data, README, local development, testing,
  deployment and workflow documentation plus PlantUML/generated SVGs. Remove
  active staging, pre-production and Entra development-tenant instructions;
  leave completed historical tasks unchanged.
- Amend the QA checklist into separate local implementation evidence and
  human-owned production deployment/smoke evidence. Preserve any valid evidence
  already recorded; never record credentials or personal identity data.
- Retain the accepted limits: no organisation authorization, back-channel
  logout, immediate IdP revocation, provider group mapping, production Graph
  access, refresh tokens or SCIM; all-organisation access, guarded first-linking
  and the 30-minute idle/eight-hour absolute session bounds remain explicit.

## Production Deployment Contract

The operator runbook must require this sequence for every production release:

1. Pass CI, production image/Compose checks, migration failure gating,
   ingress/security checks and local Authentik QA.
2. Before the first production rollout and for authentication, provider or OIDC
   configuration changes, also pass TASK-040's local Authentik-to-Entra smoke
   with designated accounts. This is supplemental evidence and does not prove
   direct Shadow-to-Entra compatibility.
3. Freeze the release, confirm a completed production backup and record its
   identifier plus the latest successful restore-verification evidence.
4. Record target commit/image references and the current stable rollback tag,
   then obtain explicit human deployment approval. The first rollout records
   that there is no previous stable release and uses stop/escalate rather than
   an invented application rollback.
5. Deploy the matching commit-specific frontend and backend images through the
   existing Coolify topology.
6. Run a limited direct-Entra production smoke with designated, pre-provisioned
   admin and consultant accounts and isolated test records: login, clean
   callback, session restoration, database role enforcement and logout. For the
   first rollout and auth changes, also verify generic denial with a designated
   unmatched account.
7. Record pass/fail, commit, tester, time, backup identifier and evidence
   location only.

Production smoke must not run destructive tests, failure injection,
load/rate-limit tests, session-expiry waiting, broad automated suites or tests
against ordinary production records.

## Rollback Contract

- Use manually created, immutable annotated SemVer tags such as `v0.1.0` as
  stable release and rollback references. This task does not create tags,
  automate them or prescribe promotion timing.
- Record each stable tag's commit SHA and matching Coolify frontend/backend
  image references.
- Roll back both application images together to the selected stable commit.
- Keep successfully applied forward migrations in place. Releases must use
  expand/contract compatibility through their documented rollback window.
- If the older application is incompatible with the forward schema, stop and
  escalate. Do not automatically run a down migration.
- Database restoration is a separately authorized human operation and is never
  implied by application rollback.
- A failed first production rollout with no older stable release stops the new
  application and escalates; it does not invent a rollback tag or restore the
  database automatically.

## Acceptance Criteria

- [ ] The production SPA and `/api` are served from one public HTTPS origin.
- [ ] Only frontend/Caddy receives the public domain; backend, migration and
      database remain internal and preserve ADR-003 behavior.
- [ ] Production Compose fails configuration when required settings are absent
      and contains no development fallback or Authentik service.
- [ ] Active architecture and workflow define local Authentik, optional local
      Entra federation and direct-Entra production only, with no staging or
      separate Entra development tenant.
- [ ] Documentation requires separate local-federation and production app
      registrations in the same single-tenant Entra directory.
- [ ] Local QA covers wrong issuer/tenant, missing-email linking, browser token
      absence, callback binding/redaction, CSRF, rate limits, revocation,
      sessions, proxy trust and production security headers.
- [ ] The runbook gates every deployment on backup/restore evidence, stable
      rollback mapping and explicit human approval.
- [ ] The production smoke is narrow, safe, direct-Entra and required after
      every deployment; prohibited production tests are explicit.
- [ ] Application rollback changes both image references together, leaves
      forward migrations in place and separates database restoration.
- [ ] Documentation, diagrams and implementation agree on the non-BFF
      same-origin OIDC session architecture.
- [ ] No deployment, Entra/Coolify mutation, production data access, Git tag,
      backup or restore operation occurs while implementing TASK-039G.

## Out Of Scope

- Production release, secret entry, Entra/Coolify resource mutation or QA.
- TASK-040's local Authentik-to-Entra implementation.
- Creating or deleting external staging infrastructure.
- Implementing backup tooling, automated release tags or automated rollback.
- Database restoration or down-migration execution.
- Organisation membership authorization, Microsoft Graph use by production,
  refresh tokens, provider groups, back-channel logout or SCIM.
- New automated browser E2E tooling.

## Testing

Required:

- [ ] Backend Ruff, pytest and pyright
- [ ] Frontend lint, tests and production build
- [ ] Backend/frontend production image builds and health checks
- [ ] Caddy adaptation, exact-host, forwarded-header, security-header and log
      redaction checks
- [ ] Production/Coolify Compose configuration checks
- [ ] Release-migration failure-gating regression
- [ ] Local Authentik manual smoke and browser/storage/network inspection
- [ ] Both authentication PlantUML sources render to committed SVGs
- [ ] Active documentation/configuration search finds no obsolete staging,
      pre-production or Entra development-tenant workflow
- [ ] Runbook/checklist review covers backup evidence, stable-tag image mapping,
      human approval, limited production smoke and rollback separation

Commands must include:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright

cd ../frontend
pnpm lint
pnpm test
pnpm build

cd ..
docker build --target production -t shadow-backend:local -f backend/Dockerfile .
docker build --target production -t shadow-frontend:local -f frontend/Dockerfile frontend

env \
  BACKEND_IMAGE=shadow-backend:local \
  FRONTEND_IMAGE=shadow-frontend:local \
  DATABASE_URL=postgresql://user:password@database:5432/shadow \
  OIDC_DISCOVERY_URL=https://login.example.test/.well-known/openid-configuration \
  OIDC_ISSUER=https://login.example.test/tenant/v2.0 \
  OIDC_CLIENT_ID=test-client \
  OIDC_CLIENT_SECRET=test-secret \
  PUBLIC_ORIGIN=https://app.example.test \
  TRUSTED_CADDY_PEER_CIDRS=172.30.0.0/24 \
  CADDY_TRUSTED_PROXY_CIDRS=172.29.0.0/24 \
  docker compose -f docker-compose.production.yml config --quiet
```

## Documentation

Update `docs/architecture/overview.md`, `README.md`, `docs/operations/local-development.md`,
`docs/operations/testing.md`, `docs/architecture/deployment.md`, active Users/data/workflow guidance,
ADR cross-references, the QA checklist and authentication/deployment PlantUML
plus generated SVGs. Historical ADR/task text may retain superseded decisions
only with explicit ADR-005 context where needed.

## Notes For AI Agent

- Ala tee production-julkaisua tai muuta Entra/Coolify-resursseja.
- Ala lisaa Authentikia release- tai Coolify-manifesteihin.
- Ala luo tageja, ota tai palauta backupia tai suorita production-QA:ta.
- Pysahdy ADR-muutokseen ennen `SameSite`-paatoksen muuttamista.
