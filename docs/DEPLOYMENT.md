# Deployment

## Accepted Plan And Current Implementation

[ADR-013](decisions/ADR-013-shared-entra-local-https-deployment.md) selects
UpCloud **Ubuntu 26.04 LTS**, Docker Engine/Compose, direct Caddy TLS and direct
Entra in development and production. Initially PostgreSQL 18 runs in Docker;
**daily encrypted on-server backups with 7-day retention are required**.
This document records the accepted plan, not a completed
deployment or authorization to change providers, credentials or production data.

The checked-in release manifests/Caddy configuration still implement the earlier
Coolify/Traefik -> HTTP frontend/Caddy:8080 topology with an external database;
local development still uses HTTP application ingress and Authentik. Do not
use those manifests as if this target were implemented. B migrates local runtime,
G replaces the production adapter, C/D add initialization commands, E supplies
tested operational commands/QA, and F performs separately approved setup/rollout.
Earlier platform/federation choices are superseded. Initial backup identifiers
and restore-rehearsal evidence remain release gates; the no-backup exception
is withdrawn.

## Release Topology

```text
UpCloud Ubuntu 26.04 LTS: Docker Engine + Compose

Browser --HTTPS :443--> Caddy (React SPA; persistent TLS storage)
                         +-- /api --> FastAPI :8000 --> Entra
                                       |
                                       +--> private PostgreSQL 18 (persistent volume)
Migration job ------------------------------> PostgreSQL
One prediction worker ----------------------> PostgreSQL
Ofelia scheduler ---------------------------> backup and Docker maintenance jobs
```

Caddy owns public TLS for `https://schatten.lupaus.eu` and HTTP :80 for the
required certificate/redirect flow. Restrict SSH to authorized operators.
Only Caddy publishes application ports. API, migration job, worker and database
have no public ports or domains. No Authentik, Traefik, Coolify, forward-auth,
`auth.lupaus.eu` or new staging environment is required.

Frontend and backend are separate immutable images built from the same release
commit. API, migration and worker share the backend artifact. Successful migration
gates API/worker startup; backend health gates frontend readiness. Preserve
one database-only prediction worker, its advisory lock, shutdown and health
contract. G verifies cold start, certificate issuance, persistent storage,
health/restart and host-reboot behavior without a circular dependency.

## Initial Database And Required Backups

Use private PostgreSQL 18 in Compose with persistent storage and secret-safe
credentials. Never mount or execute the development-user seed in production.
Persistent volumes survive container replacement but **are not backups**.
Initial release requires **daily encrypted on-server PostgreSQL backups in
`/opt/postgres-backups` with 7-day retention**, completed backup identifiers and
successful restore-rehearsal
evidence. This restores the earlier backup requirements, replaces the historical
14-day retention proposal and supersedes the intervening no-backup decision.

G delivers the backup job/scheduling and restore tooling; E supplies and tests
the runbook; F configures `/opt/postgres-backups`, protected encryption keys,
permissions, schedule and retention, then records actual verification. Use a
dedicated Ofelia container in Compose for the daily backup schedule and the
weekly Docker maintenance schedule. Ofelia is an operational scheduler only;
it is not a generic application background-job platform. Its selection and
mandatory security contract are recorded in
[ADR-013](decisions/ADR-013-shared-entra-local-https-deployment.md#operational-scheduler-and-docker-control-boundary).

Before activation, verify digest-pinned scheduler/job images, an operator-owned
read-only job file with explicit targets and no label auto-discovery, no published
ports and Ofelia's `network_mode: none`. Use the local Unix socket only, confined
to Ofelia and a documented cleanup runner; no TCP Docker listener or broadened
socket permissions. Docker API access is host-administrator-equivalent: mounting
the socket `:ro` does not restrict API writes, and container restrictions do not
contain a compromised API client.

Verify read-only root filesystems, `cap_drop: [ALL]`, `no-new-privileges`,
non-root users with only necessary socket group access, no privileged/host
namespaces and only declared temporary writable mounts. Check effective settings
of API-created job containers as well as Compose services. Among scheduled jobs,
only the backup runner receives private database networking, required database/encryption credentials
and writable `/opt/postgres-backups`; config/scripts/keys are read-only and keys
stay outside backup output. Ofelia needs no directly mounted secrets or backup
output. No operational container mounts host root, PostgreSQL data or Caddy
storage. These mount boundaries do not isolate secrets from Docker API authority.
Preload pinned job images during release. E records disposable verification; F
checks the deployed settings before enabling schedules. An unmet control blocks
activation pending a reviewed amendment, not an undocumented privilege increase.

Protect keys separately from backup files and document recovery access. Record
successful file-write/integrity outcomes, backup identifier/time, retention
results and failures without data or secrets. A created directory alone proves
no backup job.

### Scheduled Docker Maintenance

Ofelia must also run a weekly, timezone-explicit Docker cleanup job to prevent
unused runtime and build artifacts from consuming the small host's disk. The job
may remove stopped containers, dangling/expired build artifacts and other
explicitly job-owned unused resources. It must not use `docker system prune
--volumes`, delete PostgreSQL data or Caddy certificate storage, prune
`/opt/postgres-backups`, or remove the current release or retained previous
stable release images needed for rollback. Avoid broad `docker system prune -a`
unless an equivalent release-aware protection mechanism is proven.

Document the cleanup scope and retention window, provide an inspection or
dry-run path, report failures, and prevent overlap with releases, builds,
backups and restores. Docker cleanup is separate from the seven-day backup-file
retention policy and must not be treated as a database-backup mechanism.

The initial destination is on the same host, superseding the earlier off-server
requirement. Host or disk loss can destroy the database and its backups together;
this limitation is accepted. Off-server replication is future work, not an
initial-release requirement. Retain encryption, seven-day retention and all
backup/restore evidence gates.

Before each production release, record a completed pre-change backup identifier
and latest successful restore-rehearsal evidence. Missing/failed backup completion
or missing successful restore evidence blocks release. Verify restoration by
retrieving and decrypting a stored backup into an isolated PostgreSQL target,
then checking schema and data integrity; never overwrite production for rehearsal.
For first installation, enable backups and take a pre-migration baseline before
initialization; after migrations -> reference seed -> administrator bootstrap,
back up that initialized database and rehearse its restoration before acceptance.
An empty-database restore alone does not verify the initialized application data.

A later move to UpCloud Managed PostgreSQL requires a separate migration plan
for data transfer, connection/TLS/session advisory locks, cutover/rollback and
backup placement and continuity of encryption, 7-day retention and restore
verification, including evaluation of off-server protection. Selecting a managed
service does not silently remove these gates.
Application rollback cannot recover lost database contents; production restoration
requires separate explicit approval and impact review.

## Shared Entra Registration

Reuse the existing single-tenant confidential Web registration and client ID.
Both FastAPI instances connect directly to the exact tenant-specific issuer.

| Purpose | Development | Production |
| --- | --- | --- |
| Public origin | `https://app.localhost` | `https://schatten.lupaus.eu` |
| Entra Web callback | `https://app.localhost/api/v1/auth/callback` | `https://schatten.lupaus.eu/api/v1/auth/callback` |
| Post-logout return | `https://app.localhost/login` | `https://schatten.lupaus.eu/login` |

Register the exact Web callbacks and allow the post-logout return URIs. A `/login`
return page is not a front-channel logout handler. Do not add wildcards, generic
Entra authorities or SPA/public-client mode. `PUBLIC_ORIGIN` is public configuration,
not a secret, and has no path or trailing slash.

Use separate development/production secrets in protected environment storage,
with independent rotation and owners. Application databases/cookies are separate.
All secrets authenticate the same app identity: permissions, consent,
enterprise-app assignments and callbacks are shared, not environment-isolated.
Ensure designated local testers and production users can use that enterprise app.

Request only `openid profile email`; make no Graph calls and do not require an
`email_verified` claim (`OIDC_REQUIRE_VERIFIED_EMAIL=false`). Missing email still
blocks first linking. Retain validated tenant issuer, PKCE, state/nonce/browser
binding, guarded first linking to a pre-provisioned User, permanent exact
`(issuer, subject)`, database roles, sessions, revocation, CSRF/Origin and audit
rules. No Users are created during login and React receives no provider tokens.

Authentik callbacks and its Graph `User.Read` permission are excluded from target
configuration. Actual removal is authorized F setup only after checking remaining
consumers and coordinating cutover. Preserve OIDC scopes and unrelated consumers.
Old Authentik identities are retained unchanged; a new Entra identity uses normal
guarded linking. B provides explicit local-only admin provisioning even when a
development database already has seeded Users; it does not relax D's production
empty-users-table rule. Real-Entra browser results are separate from mock tests.

## Required Configuration Contract (Implementation Pending B/G)

| Setting | Contract |
| --- | --- |
| `BACKEND_IMAGE`, `FRONTEND_IMAGE` | Frozen matching release artifacts, verified IDs/digests |
| `DATABASE_URL` | Secret private PostgreSQL connection, shared by API/migration/worker |
| PostgreSQL credentials/storage | Private production configuration and persistent volume; exact wiring delivered by G |
| `OIDC_DISCOVERY_URL`, `OIDC_ISSUER` | Exact tenant-specific HTTPS metadata/issuer |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | Shared confidential app ID, production's own secret |
| `PUBLIC_ORIGIN` | `https://schatten.lupaus.eu`, exact canonical application Host |
| `TRUSTED_CADDY_PEER_CIDRS` | Only actual private Caddy peers trusted by FastAPI |
| Caddy certificate storage | Persistent writable certificate/account storage with least privilege |

The target has no upstream Traefik and needs no Coolify edge trust. The current
`CADDY_TRUSTED_PROXY_CIDRS` edge-specific setting is retired/reworked under G;
never substitute all private ranges. Caddy strips browser forwarding headers
and sends fixed Host/scheme plus the verified client address to FastAPI.
Production retains secure cookies, `APP_ENV=production`, disabled CORS, the
existing RS256/session/transaction limits and same-origin API behavior.

## Host Setup And Build/Release Contract

### Existing Cloud-Init Baseline (Operator-Reported)

The operator reports that the UpCloud Ubuntu 26.04 LTS host has already been
set up using cloud-init. Use that existing host; E/F now document verification
and remaining application setup, not a repeat of initial provisioning. The
following summarizes the supplied configuration without copying SSH keys or
treating the pasted YAML as a tested provisioning artifact:

| Area | Supplied cloud-init configuration |
| --- | --- |
| OS maintenance | Package update/upgrade; timezone `Europe/Helsinki`; unattended-upgrades installed and enabled |
| Operator account | Default cloud user retained; `deploy` with authorized SSH keys, locked password, `sudo`/`docker` groups and passwordless sudo |
| SSH | `ssh_pwauth: false`; `disable_root: false`; SSH service enabled |
| Docker | Docker's Ubuntu APT repository; Engine, CLI, containerd, Buildx and Compose plugins; Docker service enabled |
| Firewall | UFW enabled; deny incoming, allow outgoing; allow OpenSSH and TCP 80/443 |
| Fail2ban | Enabled SSH jail; five attempts, ten-minute window, one-hour ban |
| Memory | 2 GiB `/swapfile` with fstab entry; swappiness 10 and VFS cache pressure 50 |
| Directories | `/opt/apps`, `/opt/caddy`, `/opt/postgres-backups` created |

This is supplied setup information, not a recorded live host audit. F verifies
cloud-init completion/errors, actual OS/tool versions and effective settings
before rollout. Do not rerun cloud-init, recreate/format swap, reinstall Docker
or overwrite existing host files as a routine deployment step.

The remaining checks must distinguish configuration intent from effective state:

- Verify key login for `deploy` in a fresh session, effective SSH password and
  keyboard-interactive settings, and default-user/root access. The supplied
  `disable_root: false` does not establish disabled root SSH access; record its
  actual policy rather than claiming it is disabled. `deploy` is a privileged
  operator account, not an application service identity. Validate any authorized
  SSH change before reload and keep a working session to avoid lockout.
- The OpenSSH UFW allow rule has no source restriction in the supplied config.
  Verify actual host/provider IPv4/IPv6 rules and document any remaining
  restriction to operator networks; do not claim it is already source-restricted.
  Check Docker-published ports separately: UFW alone does not establish container
  privacy. Keep API/worker/migration/PostgreSQL ports unpublished.
- Verify swap/sysctl, free disk/memory, fail2ban's SSH jail and update settings,
  including reboot policy. Existing swap is not evidence that builds will fit.
- Confirm directory ownership and choose explicit certificate/database volume
  mappings under G. A created directory is not an attached persistent volume.
  Reuse cloud-init-created `/opt/postgres-backups` for the selected on-server
  backup destination. Preserve existing contents; G/F verifies ownership,
  permissions and the backup-runner mount; Ofelia needs no output mount. Directory
  creation alone is not backup evidence: verify daily encrypted backup files and 7-day retention there.

Cloud-init option semantics are documented in the
[module reference](https://docs.cloud-init.io/en/latest/reference/modules.html);
Docker describes the [UFW interaction](https://docs.docker.com/engine/network/packet-filtering-firewalls/#docker-and-ufw).

### Remaining Setup And Builds

E supplies tested verification and remaining-setup commands; G provides runtime
tooling that uses the installed Engine/Compose. Under the existing approval
boundaries, F configures missing DNS, Caddy TLS/storage, private PostgreSQL,
GitHub read-only source access, protected environment files and application
deployment. Verify source-checkout tools such as Git are available; the supplied
package list does not explicitly install Git. Make only necessary, reviewed
host changes. Store secrets privately, never in image layers, source control
or rendered Compose/log evidence.

Initially build on UpCloud from an approved exact commit and locked inputs.
Record commit/tool versions and matching immutable frontend/backend image
references, then freeze and verify their IDs/digests. Obtain release approval
and deploy those artifacts **without rebuilding**. Retain prior matched release
artifacts; mutable tags alone are insufficient release identity.

The existing image contexts are repository root for backend and `frontend/`
for frontend. G updates portable Compose/image checks and removes active Coolify
adapter checks, preserving equivalent migration, ingress, worker and secret
validation coverage. Existing checks against the old manifests do not prove the
new topology. Tests use disposable data and simulated OIDC without tenant secrets.

OOM/failing builds, sustained memory/swap/CPU contention affecting the app or
unacceptable build duration trigger reassessment. GitHub Actions/GHCR can later
build the same artifact contract, followed by approved deployment of frozen
images. No automatic deployment or off-server workflow is implemented here.

## First Initialization (Commands Pending C/D)

For a fresh database, the explicit order is:

1. Apply reviewed forward migrations through the release backend image.
2. Run `python -m app.seed_reference_data` from that artifact. It shares the
   existing development seed's non-user metamodel SQL/JSON, inserts atomically
   only when no active default exists, and otherwise preserves it unchanged.
3. Run interactive `python -m app.bootstrap_admin` from that artifact in a private
   operator terminal. Validate the designated Entra name/email; create one fixed
   admin only when the entire users table is empty, including soft-deleted rows.
4. First direct-Entra login links the pre-provisioned admin normally. Provision
   subsequent Users through existing admin functionality, then run limited smoke.

C/D are database-only commands, create no identities/sessions and do not initialize
OIDC. No personal input in command arguments/evidence. They never run automatically
on application startup. Subsequent releases run migrations, not first-admin
bootstrap. Never run the full `002_seed_development_data.sql` in production.

This is a fresh-install plan. Existing untracked production database adoption is
outside it and requires a separate reviewed procedure; historical baseline/
backup safeguards are not permission to auto-baseline or overwrite existing data.

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

## Manual Release Gate And Narrow Smoke

E integrates B/C/D/G and verifies commands against disposable infrastructure.
F requires E and explicit operational approval. Before deployment:

1. Record passing target-commit CI/local checks for the changed scope, including
   simulated OIDC and production-style Compose/ingress/worker verification.
2. Complete separately recorded real local direct-Entra browser checks after
   authorized setup. Historical Authentik/federation evidence is not equivalent;
   local success does not prove production DNS/TLS/secret correctness.
3. Freeze matching image references and record approval, target commit and
   previous stable references, or the explicit first-release absence. Confirm
   schema compatibility and failure/stop path. Record a completed pre-change
   backup identifier and latest successful restore-rehearsal evidence; missing
   evidence blocks release. First-install baseline and post-initialization
   verification follow the required-backups procedure above.
4. Deploy without rebuilding, respecting migration and health gates, and execute
   first initialization only for a fresh database as described above.
5. Use designated pre-provisioned admin/consultant accounts and isolated records
   for login/callback/session/logout, database-role enforcement and one prediction
   flow. For first rollout or auth/provider changes, verify a designated unmatched
   account fails generically without creating a User, identity or session.
6. Record tester/time, commit, artifacts, initialization and smoke results plus
   sanitized evidence, backup identifiers and restore-verification location.
   Confirm daily encrypted on-server backups and 7-day retention are active.
   A failed check stops release acceptance and invokes the failure decision below.

Do not run broad automated production suites, destructive tests, load/rate-limit
experiments, spoofing, secret injection, migration-failure tests or database
rollback experiments. Do not record personal identities, tokens or secrets.

## Stable References, Failure And Application Rollback

Stable references are manually managed immutable annotated SemVer tags such as
`v0.1.0`, with promotion under human ownership. Record each tag's commit and
matching backend/frontend artifact IDs/digests. No tag operation is authorized
by this document.

On migration failure, stop the new release, inspect sanitized output, correct
the reviewed cause and retry forward. On application/worker/smoke failure, stop
new submissions and inspect safe request summaries. Preserve durable queued
requests and avoid running a mismatched worker. Interrupted running requests
become visibly failed without automatic retry; cancelling requests become
cancelled. Record safe request identifiers and require manual resubmission where
appropriate, without snapshots or personal data.

Deploy older matched frontend/API/worker images together only after confirming
compatibility with all applied forward migrations. Use expand/contract changes
and retain their compatibility window. Otherwise stop/escalate for a separately
approved forward fix. First rollout has no previous stable application target.

Never automatically run down migrations, delete volumes, reset or restore the
database. Application rollback leaves successful migrations in place and cannot
recover lost database contents. Restoration from backup is a separate operation
requiring explicit authorization and impact review; a failed deploy or smoke
test never triggers automatic database restoration.

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

## Delivery Sequence

[A](../tasks/TASK-059A-shared-entra-local-https-architecture.md) precedes
[B](../tasks/TASK-059B-local-https-direct-entra.md),
[C](../tasks/TASK-059C-production-reference-data-seed.md),
[D](../tasks/TASK-059D-production-admin-bootstrap.md) and
[G](../tasks/TASK-059G-upcloud-docker-runtime.md). D uses C for final sequence
verification. [E](../tasks/TASK-059E-upcloud-docker-runbook-qa.md) integrates them;
[F](../tasks/TASK-059F-first-production-rollout.md) follows E and explicit
operational approval. No production-Authentik task H is created.
