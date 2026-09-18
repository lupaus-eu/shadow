# ADR-013: Shared Entra Registration And Local HTTPS Deployment

Status: Accepted; runtime and rollout pending TASK-059B through TASK-059G

Date: 2026-09-11

Amended: 2026-09-17 for UpCloud, direct Caddy TLS, direct Entra in both
application environments and Ubuntu 26.04 LTS. Subsequent approved amendment
restores initial daily encrypted on-server backups with 7-day retention,
backup identifiers and restore-rehearsal evidence requirements. The subsequent
destination amendment selects `/opt/postgres-backups` on the same server initially,
superseding the off-server requirement without removing the remaining release gates.

Amended: 2026-09-18 to record Ofelia for operational scheduling and its mandatory
Docker control-plane hardening, pending implementation and verification in G/E/F.

# Context And Supersession

The earlier unmerged version of this ADR selected local Authentik federation,
Coolify/Traefik, an external PostgreSQL resource and Ubuntu 24.04 LTS. Those
choices are superseded by this amendment. The previous TASK-059A implementation
record and completed authentication QA remain historical evidence only.

This decision supersedes ADR-003's Coolify topology and external-database
requirement; ADR-004/005's local Authentik and separate-registration provisions;
and ADR-006's Authentik TLS/federation target. Initial backup jobs, daily encrypted
on-server backups, backup identifiers and restore-rehearsal evidence remain
required. Retention is **7 days**, replacing the historical 14-day proposal.
The intervening no-initial-backup decision is superseded. Historical verification
records retain their original scope; they do not prove backup implementation.

ADR-002's paired migrations, ADR-003's immutable release/migration contract,
ADR-004's backend-owned identity/session/authorization model, ADR-005's two
environments and ADR-012's single prediction worker remain active.

# Decision

## Origins And Shared Registration

| Purpose | Development | Production |
| --- | --- | --- |
| Public origin | `https://app.localhost` | `https://schatten.lupaus.eu` |
| Entra Web callback | `https://app.localhost/api/v1/auth/callback` | `https://schatten.lupaus.eu/api/v1/auth/callback` |
| Post-logout return | `https://app.localhost/login` | `https://schatten.lupaus.eu/login` |

Both FastAPI instances connect **directly to Entra** using the existing
single-tenant confidential Web registration in the organisation tenant. Keep
its client ID, separate environment secrets and independent application
databases. Register both exact Web callbacks and allow the respective
post-logout return URIs; these return pages are not front-channel logout
handlers. No wildcard callbacks, SPA/public-client conversion or generic
`common`/`organizations` authorities are introduced.

`PUBLIC_ORIGIN` is public configuration, not a secret; use an exact origin
without a path or trailing slash. Host-only cookies and DNS remain separate.
Never redirect production DNS to a development machine. Store secrets only in
gitignored private local configuration or protected production secret storage,
with separate owners and rotation records. No credentials are created here.

Separate secrets still authenticate the same application identity. Permissions,
consent, enterprise-app assignments and callbacks are shared; credentials are
not restricted to their environment's callback. Assignment policy must cover
designated local testers and production users. This coupling and the effect a
compromised development credential could have on production are accepted.

## Claims And Application Identity

Use the exact tenant-specific issuer and request only `openid profile email`.
There are no Graph calls and no requirement for an `email_verified` claim
(`OIDC_REQUIRE_VERIFIED_EMAIL=false` in both environments). Missing email still
prevents first linking. A validated email is accepted for first linking only
within the existing small-company, single-tenant administrator trust model.

Retain Authorization Code + PKCE, state/nonce/browser binding, guarded first
linking to exactly one active pre-provisioned User, permanent case-sensitive
`(issuer, subject)` ownership, database roles, opaque application sessions,
CSRF/exact Origin checks, revocation and audit rules. React receives no provider
tokens. Login never creates a User. No group/app-role mapping, refresh-token
storage, `offline_access`, SCIM or forward-auth is added.

Preserve old Authentik identity rows without rewriting their issuer or subject.
A new Entra identity goes through normal guarded linking; sharing registration
does not copy identities or sessions between databases. TASK-059B supplies
explicit local-only provisioning of a designated Entra admin even for an
existing seeded development database, without weakening the production
bootstrap's empty-users-table rule or committing personal emails.

Authentik callbacks and the delegated Graph `User.Read` permission used for its
`/me` mapping are absent from the target configuration. Their actual removal
from Entra is an authorized setup action under TASK-059F, after checking for
remaining consumers and coordinating the local cutover. Remove only unused
entries/grants; do not revoke another consumer's access. OIDC scopes remain.

## Hosting, TLS And Runtime

The production host is an **UpCloud server running Ubuntu 26.04 LTS**, with
Docker Engine and Compose. Caddy directly owns public TLS and persistent
certificate storage. `auth.lupaus.eu` is not needed. There is no Authentik in
either target environment, no Traefik, Coolify or new staging environment.

```text
Development: https://app.localhost -> loopback Caddy -> Vite / FastAPI -> Entra
Production:  https://schatten.lupaus.eu -> Caddy (React) -> FastAPI -> Entra
                                                          |
                                      private PostgreSQL 18 container
                                      + one prediction worker + migration job
```

Local Caddy routes `/api` and `/api/*` directly to FastAPI and other traffic,
including Vite HMR WebSockets, to Vite. Retain strict Host/forwarded headers,
callback-log redaction, browser security headers and secure host-only cookies.
Bind development ingress and any exposed development ports to loopback. Reuse
valid local CA material where possible and separate application TLS tooling
from Authentik; do not delete old volumes or reset existing application data.

Production exposes Caddy HTTP/HTTPS (80/443) and restricts SSH to authorized
operators. API, migration job, single worker and PostgreSQL have no public
ports or domains. Fix and sanitize forwarded headers at Caddy; FastAPI trusts
only its actual Caddy peers, with no broad private-network trust. No upstream
Traefik trust is needed. Preserve migration-success gates for API/worker and
backend health gating frontend readiness, including the certificate-issuance
and readiness behavior to be verified under G.

PostgreSQL 18 initially runs in Docker with private networking and persistent
storage. **Persistent volumes survive container replacement but are not backups.**
Initial release requires daily encrypted on-server PostgreSQL backup jobs writing
to **`/opt/postgres-backups`** with **7-day retention**, identifiable completed
backups and successful isolated restore-rehearsal evidence. Protect encryption
keys separately from backup files and document recovery access; no secrets enter
evidence. These same-host backups do not protect against host or disk loss;
that initial limitation is accepted. Off-server replication is deferred, not a
release gate. Reuse the cloud-init-created `/opt/postgres-backups` directory;
preserve existing contents and verify ownership, permissions and job mounts in F.
G implements tooling, E verifies procedures and F activates them under approval.

Before each production release, record a completed pre-change backup identifier
and latest successful restore-verification evidence. Missing/failed backups or
missing restore evidence block release. For a fresh first installation, enable
backups before initialization, capture a pre-migration baseline, then back up
the migrated/seeded/bootstrap database and rehearse its restoration to an isolated
target before release acceptance. Never rehearse by overwriting production.

A later move to UpCloud Managed PostgreSQL requires a separate migration plan
covering data transfer, connection/TLS and session-level advisory-lock needs,
cutover/rollback, backup placement and continuity of encryption, 7-day retention
and restore verification. Evaluate off-server protection in that separate plan.
Managed-service migration is deferred; initial backup protection is not.

## Operational Scheduler And Docker Control Boundary

Select a dedicated **Ofelia** container for daily PostgreSQL backups and weekly
Docker maintenance. Its Docker job execution and file-based configuration let
reviewed schedules travel with the Compose release. Host cron/systemd timers
would avoid a separate scheduler container but add host-managed configuration;
Ofelia is selected to keep operational configuration in the release contract.
Application predictions continue to use ADR-012's single worker. Ofelia is not
an application job platform. See the [Ofelia documentation](https://github.com/mcuadros/ofelia).

Docker socket access is host-administrator-equivalent authority, including
access to other containers and their secrets. A socket mounted `:ro` does **not**
make Docker API operations read-only. Container hardening and separated secret
mounts reduce exposure but cannot contain a compromised Docker API client.
This operational trust boundary must be explicit in the runbook and release
review. See [Docker daemon security](https://docs.docker.com/engine/security/).

G must implement and test these requirements; E documents the checks and F
verifies the deployed configuration before enabling the schedules:

- Pin Ofelia and operational job images by digest, record their provenance,
  and review updates; no floating tags. Preload required images during release.
- Give Ofelia no published ports and `network_mode: none`. Use only the local
  Unix socket; never expose a Docker TCP listener or route it through Caddy.
  Mount it only into Ofelia and any explicitly documented Docker-cleanup runner,
  never the frontend, API, worker, migration or database-backup runner. Do not
  broaden host socket permissions; use only the required socket group access.
- Use a read-only, operator-owned job configuration with explicit commands and
  targets; do not enable Docker-label auto-discovery or accept application/user
  input as commands. Only authorized host operators may change this configuration.
- Require a read-only container root filesystem, `cap_drop: [ALL]`,
  `no-new-privileges`, non-root execution with the required socket group, and no
  privileged mode or host PID/IPC/network namespaces. Limit writable scratch
  space to declared temporary mounts. Apply these controls to job runners too;
  a backup runner may join only the private database network it needs.
- Mount configuration/scripts read-only. Among scheduled jobs, only the backup
  runner receives the required database credential, encryption material and writable
  `/opt/postgres-backups` destination; mount keys read-only outside that directory.
  Do not mount application secrets, database data directories, Caddy storage or
  the host root into operational containers. The scheduler needs no directly
  mounted secrets or backup output; Docker access still defeats secret isolation.

Schedules require an explicit timezone, safe failure reporting and exclusion
locks; weekly cleanup must not overlap a release, build, backup or restore.
Preserve persistent volumes, backup files and current/previous release artifacts.
Seven-day backup retention remains distinct from Docker resource cleanup.
G tests the effective container settings, including runners started through the
Docker API; Compose settings alone do not prove those runners are hardened.
If a selected image/job mode cannot meet these requirements, stop for a reviewed
amendment rather than silently weakening them.

Revisit or replace Ofelia through a reviewed decision if it cannot be maintained
securely, needs broader access, or no longer has required operational jobs.
Moving PostgreSQL to a managed service does not itself retire maintenance or
backup obligations: verify replacement scheduling and recovery evidence before
disabling the existing jobs. Runtime and real scheduler activation remain pending.

## Builds And Releases

Initially build on UpCloud from an approved exact commit using reproducible,
locked inputs. Freeze immutable frontend/backend image references; API,
migration and worker use the same backend artifact. Deploy those artifacts
without rebuilding. Keep matching previous release artifacts for coordinated
application rollback where compatible with the already migrated schema.

Memory exhaustion, sustained swap/CPU pressure affecting the app, excessive
build time or failed builds trigger reassessment and possible GitHub Actions /
GHCR builds using the same image contract. This does not implement automatic
deployment or an off-server workflow. Releases require explicit human approval.

Application rollback never runs automatic down migrations, deletes volumes,
resets or restores the database, and cannot recover lost database contents.
Use expand/contract schema changes; if older images are incompatible, stop and
escalate for a separately approved forward fix. A first rollout with no stable
release has no application rollback target. QA uses simulated OIDC and
disposable databases locally, separately recorded real-Entra browser checks,
and narrow authorized production smoke tests.

## Explicit Initial Data

The non-user metamodel content of `db/init/002_seed_development_data.sql` is
approved production reference data: default metamodel/version, node and edge
types, attributes and connection rules. Development Users and example business
data remain forbidden in production; never execute the full development seed.

Explicit first initialization is **migrations -> reference seed -> administrator
bootstrap**, then smoke verification. These are not application-startup hooks.

- TASK-059C provides `python -m app.seed_reference_data` in the backend image,
  sharing the development SQL/JSON through existing Psycopg and transaction-local
  JSON input. Serialize atomic initialization; insert only if there is no active
  default metamodel, otherwise preserve it unchanged. Create no Users or business
  records. The CLI needs database configuration only.
- TASK-059D provides interactive `python -m app.bootstrap_admin` with database
  configuration only. Validate name/email and create one fixed-role admin only
  when the entire users table is empty, including soft-deleted rows. Serialize
  check/insert, permit existing reference data, use the nullable bootstrap audit
  actor, and create no identities/sessions. Log no personal input or secrets.
  First direct-Entra login performs normal guarded identity linking.

Subsequent Users use existing administration. No manual production SQL or
alternate login admission path is introduced.

# Implementation Status And Follow-Up

This amendment changes documentation only. The checked-in local runtime still
uses HTTP application ingress and Authentik until B; the release configuration
still contains the Coolify/HTTP-Caddy adapter until G. Historical QA results do
not verify the accepted target, and provider setup has not occurred.

| Task | Delivery | Dependency |
| --- | --- | --- |
| [A](../../tasks/TASK-059A-shared-entra-local-https-architecture.md) | Architecture/policy amendment | None |
| [B](../../tasks/TASK-059B-local-https-direct-entra.md) | Local HTTPS and direct Entra, Authentik retirement | A |
| [C](../../tasks/TASK-059C-production-reference-data-seed.md) | Shared reference seed | A |
| [D](../../tasks/TASK-059D-production-admin-bootstrap.md) | Empty-users-table administrator CLI | A; C for final sequence verification |
| [G](../../tasks/TASK-059G-upcloud-docker-runtime.md) | Production runtime, build/release and backup tooling | A |
| [E](../../tasks/TASK-059E-upcloud-docker-runbook-qa.md) | Integrated runbook and QA | B/C/D/G |
| [F](../../tasks/TASK-059F-first-production-rollout.md) | Authorized setup and first rollout | E and explicit operational approval |

TASK-059H is not created: production Authentik is excluded. After documentation
review, B is implemented on its own task branch. Acceptance of this ADR does
not authorize tenant/DNS changes, production writes or deployment.

# Options And Consequences

Direct Entra removes the extra identity-provider operation and makes both
application flows use the same provider policy. Interactive local login now
requires tenant access and explicit pre-provisioning; offline automated tests
use simulated OIDC. HTTPS development requires local certificate trust and a
free loopback port 443, and cannot prove production DNS/TLS/secret correctness.

Separate registrations would offer stronger permission and assignment isolation;
the approved plan accepts the coupling of one shared registration. Identical
origins were rejected to preserve cookie/DNS separation. Migration to managed
PostgreSQL is deferred; the operator owns initial host/database
maintenance and the required backup/restore procedures. Backups reduce recovery
risk but application rollback alone cannot recover lost contents. Server builds
reduce initial infrastructure while immutable artifacts preserve a route to
off-server builds.

# Related

- [Deployment](../DEPLOYMENT.md) and [local development](../LOCAL-DEVELOPMENT.md)
- [ADR-002](ADR-002-database-migrations.md), [ADR-003](ADR-003-coolify-deployment.md)
- [ADR-004](ADR-004-authentication.md), [ADR-005](ADR-005-production-only-environments.md), [ADR-006](ADR-006-local-authentik-entra-federation.md)
- [ADR-012](ADR-012-background-prediction-requests.md)
