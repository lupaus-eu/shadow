# Deployment

This document describes the production-only baseline from ADR-003, ADR-004 and
ADR-005. It is an operator runbook, not authorization to create provider
resources, enter production secrets, deploy, create tags, take/restore backups
or execute production QA.

## Release Topology

Schatten publishes one HTTPS origin:

```text
browser -> Coolify TLS edge -> frontend/Caddy :8080 -> backend/FastAPI :8000
                                                     -> PostgreSQL
                                                     -> Microsoft Entra ID
prediction worker ---------------------------------> PostgreSQL
```

Only `frontend` receives the public application domain. Caddy serves the built
React SPA, provides history fallback and reverse-proxies `/api`. Backend,
prediction worker, one-shot migration and database ports remain internal. Caddy
listens only on unprivileged internal HTTP port `8080`; it neither obtains
certificates nor publishes container ports 80/443. Coolify terminates public
TLS.

The release has two immutable, commit-specific artifacts:

- backend image: API, prediction worker, `migrate.py` and repository SQL
  migrations
- frontend image: built SPA and pinned official Caddy

Migration, API and prediction worker use the same backend image and
`DATABASE_URL`. The migration command is `python migrate.py up`; it receives
only database configuration and does not import or initialize the FastAPI/OIDC
application. API and worker start only after migration exits zero, and frontend
starts only after backend is healthy. The worker receives no OIDC, session or
public-origin settings and publishes no port. Forward migrations are never
automatically rolled back.

Authentik is absent from every release/Coolify manifest. It is local-only,
including TASK-040's optional Authentik-to-Entra federation.

![Authentication deployment components](diagrams/generated/component-authentication-topology.svg)

## Files

```text
backend/Dockerfile                 backend API, worker and migration artifact
frontend/Dockerfile                Vite build and Caddy production artifact
frontend/Caddyfile                 provider-neutral same-origin ingress policy
frontend/caddy-entrypoint.sh       derives the allowed Host from PUBLIC_ORIGIN
docker-compose.release.yml         shared release lifecycle and environment
docker-compose.production.yml      portable immutable-image contract
docker-compose.coolify.yml         thin Coolify image-tag/health adapter
docs/qa/AUTHENTICATION-QA-CHECKLIST.md
docs/qa/PREDICTION-WORKER-RUNTIME-QA.md
```

The Caddy runtime is official
`caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648`
and uses only standard modules. Upgrade it deliberately: inspect the target
patch's official multi-platform digest, review Caddy security/release notes,
update the Dockerfile, then rerun the image and live ingress checks.

## Required Configuration

Production Compose has no development auth fallback. It fails interpolation if
any required value is absent:

| Variable | Service | Contract |
| --- | --- | --- |
| `BACKEND_IMAGE` | production manifest | Immutable backend commit tag/digest |
| `FRONTEND_IMAGE` | production manifest | Immutable frontend commit tag/digest |
| `DATABASE_URL` | migration + backend + prediction worker | Secret PostgreSQL URL |
| `OIDC_DISCOVERY_URL` | backend only | Tenant-specific HTTPS discovery URL |
| `OIDC_ISSUER` | backend only | Exact, case-sensitive single-tenant issuer |
| `OIDC_CLIENT_ID` | backend only | Confidential web application client ID |
| `OIDC_CLIENT_SECRET` | backend only | Secret-manager value, never committed |
| `PUBLIC_ORIGIN` | backend + frontend | Exact HTTPS origin, no path or trailing slash; frontend derives its allowed Host from it |
| `TRUSTED_CADDY_PEER_CIDRS` | backend only | Internal Caddy peer CIDR(s), comma-separated |
| `CADDY_TRUSTED_PROXY_CIDRS` | frontend only | Coolify edge CIDR(s), space-separated for Caddy |

Use one browser-canonical lowercase literal DNS or IP host. Do not use
wildcards, multiple hosts, whitespace or any explicit port; Coolify terminates
public HTTPS on the standard authority. The frontend derives its sole allowed
Host from `PUBLIC_ORIGIN`, so non-canonical or malformed origins fail startup
and the proxy and backend cannot be configured with different application
hosts. Callback and post-logout URIs are fixed from that origin:

```text
${PUBLIC_ORIGIN}/api/v1/auth/callback
${PUBLIC_ORIGIN}/login
```

The release fixes `APP_ENV=production`, `SESSION_COOKIE_SECURE=true`, scopes
`openid profile email`, signing algorithm `RS256`, callback path, 30-minute
idle timeout, eight-hour absolute lifetime and ten-minute login transaction.
Production CORS middleware is disabled; no wildcard or credentialed cross-origin
policy is configured.

`CADDY_TRUSTED_PROXY_CIDRS` must contain only the actual Coolify edge network,
not all private ranges. Caddy uses strict right-to-left trusted-proxy parsing.
It removes browser-supplied `Forwarded`, `X-Forwarded-*` and
`X-Schatten-Client-IP`, then sends FastAPI the fixed public Host and HTTPS
scheme plus Caddy's parsed client address. FastAPI accepts that address only
when its immediate peer belongs to `TRUSTED_CADDY_PEER_CIDRS`. Record the
deployment-specific networks without credentials in the change record.

## Build And Portable Verification

Build from these exact contexts:

```bash
docker build --target production -t schatten-backend:local -f backend/Dockerfile .
docker build --target production -t schatten-frontend:local -f frontend/Dockerfile frontend
```

Validate the artifact and release boundary using non-production values:

```bash
env \
  BACKEND_IMAGE=schatten-backend:local \
  FRONTEND_IMAGE=schatten-frontend:local \
  DATABASE_URL=postgresql://user:password@database:5432/schatten \
  OIDC_DISCOVERY_URL=https://login.microsoftonline.com/tenant-id/v2.0/.well-known/openid-configuration \
  OIDC_ISSUER=https://login.microsoftonline.com/tenant-id/v2.0 \
  OIDC_CLIENT_ID=test-client \
  OIDC_CLIENT_SECRET=test-secret \
  PUBLIC_ORIGIN=https://app.example.test \
  TRUSTED_CADDY_PEER_CIDRS=172.30.0.0/24 \
  CADDY_TRUSTED_PROXY_CIDRS=172.29.0.0/24 \
  docker compose -f docker-compose.production.yml config --quiet

.github/scripts/verify-production-compose.sh
BACKEND_IMAGE=schatten-backend:local \
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/disposable_database \
  .github/scripts/verify-production-worker.sh
FRONTEND_IMAGE=schatten-frontend:local \
  .github/scripts/verify-production-frontend.sh
```

The worker check must target a migrated disposable PostgreSQL database. It
checks the production image's numeric non-root worker, database-only settings,
dedicated health command, exclusive ownership, automatic restart, shutdown
configuration and safe lifecycle logs. The PostgreSQL pytest harness separately
proves durable queue, cancellation and interrupted-request recovery behavior.
The live frontend check uses an isolated Docker network and mock internal API.
It covers Caddyfile adaptation/startup, health, exact Host, forwarded-header
overwrite, security headers, SPA fallback and query-log redaction.

## Ingress Response And Logging Policy

Caddy access logs retain useful method, path, query, status, client and timing
metadata. Its query filter replaces every value for `code`, `state`, `error`
and `error_description` with `REDACTED` on every path. Default Caddy
credential-header redaction remains enabled; do not enable `log_credentials`.

The repository Caddyfile enforces:

```text
Strict-Transport-Security: max-age=31536000
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'
```

HSTS deliberately omits `includeSubDomains` and `preload`. The CSP style and
image exceptions are limited to the current UI's inline layout styles and
repository CSS data image. Any new external source requires security and
architecture review.

## Entra App Registrations

Use one single-tenant organisation directory and two separate confidential
**Web** app registrations outside this repository:

- a local-federation registration owned by TASK-040, containing only the local
  Authentik callback, its own secret and any minimal Graph permission Authentik
  requires; restrict its enterprise application to designated test accounts
  where tenant policy supports assignment
- a production registration containing only the exact Schatten callback and
  post-logout URIs shown above and its own production secret

Do not share secrets, redirect URI sets or permissions between registrations.
For the production registration:

1. Do not register Schatten as an SPA/public client.
2. Do not add wildcard, localhost or local Authentik URIs.
3. Use tenant-specific discovery and issuer values. `common`, `organizations`
   and `consumers` authorities are forbidden.
4. Request only `openid profile email`. Do not request `offline_access`, Graph
   permissions, provider groups or app roles.
5. Store its secret only in Coolify or the approved secret manager. Record the
   owner and expiry/rotation process, never the value.
6. Pre-provision designated active Schatten Users with matching internal emails.
   Missing email or no unique active match fails generically.
7. After first login, treat exact `(issuer, subject)` as permanent. Email is not
   consulted for subsequent identity ownership or authorization.

The Entra email assertion is accepted only for guarded first linking in the
small-company, single-tenant administrator trust model. External/guest users or
a broader trust boundary require an ADR review before provisioning.

Creating registrations, credentials or tenant policy remains human-owned.
TASK-039G does not perform those operations.

## Coolify Configuration

Configure the Git-backed resource with `/docker-compose.coolify.yml`. Coolify's
predefined `COOLIFY_RESOURCE_UUID` and `SOURCE_COMMIT` create:

```text
schatten-backend-${COOLIFY_RESOURCE_UUID}:${SOURCE_COMMIT}
schatten-frontend-${COOLIFY_RESOURCE_UUID}:${SOURCE_COMMIT}
```

Enter the required configuration above in Coolify, marking database URL and
OIDC client secret as secrets. Assign the application domain only to
`frontend:8080`. Do not assign a domain or public port to backend, prediction
worker or migration. The migration service retains `exclude_from_hc: true`;
frontend, backend and prediction worker use their respective image/service
health checks. Caddy, backend and worker run as numeric user/group `10001:10001`.
The worker's standard Compose fields can be validated locally, but Coolify must
parse and exercise the manifest before rollout; standard Compose parsing does
not prove provider-specific behavior such as `exclude_from_hc`.

Coolify Compose deployment is not rolling or zero-downtime. Plan a maintenance
window where availability is required.

## Existing Database Adoption Gate

Before enabling deployment for an existing production database:

1. Disable automatic deployment and take a verified restorable backup.
2. Inspect `schema_migrations` and compare the actual schema with repository
   migrations; never infer the level from the latest filename alone.
3. For a verified non-empty untracked database only, run the explicit matching
   image command `python migrate.py baseline NNN`.
4. Run `python migrate.py up` from that image and require a successful no-op.
5. Record backup, baseline and result without credentials.

Never automate `baseline` or use it for a fresh empty database.

## Production Deployment And Smoke

There is no staging or pre-production application environment. Every production
deployment requires a change record and this sequence:

1. Require green CI, backend/frontend production image builds, production
   Compose and worker lifecycle checks, migration failure gating,
   ingress/security checks, the broad local Authentik QA checklist and the
   prediction-worker runtime QA record.
2. Before the first production rollout and whenever authentication, provider or
   OIDC configuration changes, also require TASK-040's local
   Authentik-to-Entra smoke with designated accounts. Record that it is
   supplemental evidence: it does not test Schatten's direct production client,
   issuer, callback, secret or Coolify boundary.
3. Freeze the release candidate. Confirm a completed production backup and
   record its identifier plus the evidence location for the latest successful
   restore verification. Missing backup or restore-verification evidence blocks
   deployment.
4. Record the target commit SHA, matching backend/frontend image references
   (the worker uses the exact backend reference),
   intended stable SemVer tag if one exists, and current stable rollback tag
   with its commit and matching image references. For the first production
   rollout, explicitly record that no previous stable application release
   exists and that rollback means stopping the new application, not restoring
   the database automatically.
5. Obtain explicit human approval for this deployment. Merge or CI success is
   not deployment authorization.
6. Deploy API, frontend and worker together from the two matching
   commit-specific images through the existing Coolify topology. Require the
   migration -> API/worker startup gates and backend health -> frontend gate.
   Do not mix the new create API with an older frontend or omit its worker.
7. Run the limited direct-Entra production smoke with designated,
   pre-provisioned admin and consultant accounts and isolated test records:
   login, clean callback, session restoration, database role enforcement and
   logout. For the first rollout and authentication/provider changes, also
   confirm a designated unmatched account fails generically and creates no
   application session.
8. Record pass/fail, commit, tester, time, backup identifier and evidence
   location. Do not record names, personal email, credentials, codes, tokens,
   cookies, session/CSRF values or secrets.

Production is not a general QA environment. Do not run destructive tests,
failure injection, load/rate-limit tests, session-expiry waiting, broad
automated suites or tests against ordinary production records. Stop the release
and follow rollback policy when the limited smoke fails.

If direct Entra testing proves `SameSite=Strict` incompatible with supported
browsers, stop. Propose and obtain review for an ADR-004 amendment before
changing the application session cookie to `Lax`.

## Stable References, Failure And Rollback

Stable release/rollback references are manually managed, immutable annotated
SemVer Git tags such as `v0.1.0`. Tag creation and promotion timing are
human-owned and are not automated or prescribed here. A deployment record maps
each used stable tag to:

```text
tag -> commit SHA
    -> schatten-backend-${COOLIFY_RESOURCE_UUID}:${SOURCE_COMMIT}
       (API, prediction worker and migration)
    -> schatten-frontend-${COOLIFY_RESOURCE_UUID}:${SOURCE_COMMIT}
```

On migration failure, keep the deployment stopped, inspect credential-safe job
output, correct the reviewed cause and retry forward. Never run a down migration
automatically.

If application or worker health, or the production smoke, fails after
migrations succeed, first stop new submissions and inspect request summaries.
Queued requests are durable but must not be processed by a mismatched worker.
Any request interrupted while `running` becomes visibly failed without an
automatic retry; `cancelling` becomes cancelled. Record affected request IDs
without snapshots or personal data and require manual resubmission where
appropriate. Then select the documented stable rollback tag, resolve its
commit-specific backend and frontend images, and deploy API/frontend/worker
together. Successfully applied forward
migrations remain in place, so every release must preserve expand/contract
compatibility through its documented rollback window. If the older application
is incompatible with the current forward schema, stop and escalate instead of
deploying it or executing a down migration.

For the first production rollout, there is no older stable application image.
If that rollout fails, stop the new application and escalate; do not invent a
rollback tag or restore the database without separate authorization.

Database restoration is separate from application rollback. It requires its
own explicit human authorization and impact review and is never triggered
automatically by a failed deployment or smoke test.

## Security And Product Limits

- No organisation membership authorization; all active internal roles
  intentionally access all organisations.
- No back-channel logout or immediate provider revocation. A provider-disabled
  account can retain its Schatten session until admin revocation/user disablement
  or the 30-minute idle/eight-hour absolute limit.
- No provider group mapping, Graph access, refresh tokens, SCIM or provider
  access-token retention.
- Local logout is guaranteed; provider end-session is best effort.
- The in-memory public-auth limiter supports one backend replica. Multiple
  replicas require shared rate limiting and architecture review.

## Provider Replacement

A replacement deployment provider must preserve both artifact boundaries: run
the backend image migration command once with failure propagation, start API
and the single prediction worker from that same backend image only after
success, evaluate their separate health checks, then start the frontend/Caddy
image as the sole public ingress. Application code and the repository Caddyfile
must remain provider-neutral.
