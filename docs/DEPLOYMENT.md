# Deployment

## Accepted Plan And Current Implementation

[ADR-013](decisions/ADR-013-shared-entra-local-https-deployment.md) selects
UpCloud **Ubuntu 26.04 LTS**, Docker Engine/Compose, direct Caddy TLS and direct
Entra in development and production. Initially PostgreSQL 18 runs in Docker;
**daily encrypted on-server backups with 7-day retention are required**.
This document records the accepted plan, not a completed
deployment or authorization to change providers, credentials or production data.

TASK-059G implements the production runtime and tooling:
`docker-compose.production.yml` (direct-TLS Caddy, private PostgreSQL 18,
migration job, API, one prediction worker, Ofelia and hardened operational
runners), the frozen-image build/release commands in `deploy/bin/`, and the
encrypted backup, restore-rehearsal and Docker-cleanup jobs in `deploy/ops/`.
The Coolify adapter and `docker-compose.release.yml` are removed. Local
development uses loopback Caddy HTTPS and direct Entra (B); C/D provide the
initialization commands. TASK-059E supplies the integrated, disposably tested
operator procedure in [PRODUCTION-RUNBOOK.md](PRODUCTION-RUNBOOK.md) with
evidence in [UPCLOUD-RUNBOOK-QA.md](qa/UPCLOUD-RUNBOOK-QA.md). F performs the
separately approved host, DNS, tenant, backup activation and rollout by that
runbook. No production operation has been performed. Backup identifiers and
restore-rehearsal evidence remain release gates.

The ADR-013 amendment of 2026-09-29 (TASK-059H) replaces the host Git checkout
and GitHub deploy key with a manual "Deploy to production" GitHub Action that
uploads the exact `main` commit and a source manifest to an upload-only
account; a root-owned receiver verifies it against the manifest digest from the
run summary, and builds run from that verified copy with **no Git on the
server** (see
[ADR-013](decisions/ADR-013-shared-entra-local-https-deployment.md#source-delivery-without-git-on-the-server)).
H1 implemented the manifest, the receiver and the Git-free
`build-release --source` described in the command and storage tables below;
H2 implemented the upload gate and the workflow
([Source Delivery Workflow And Upload Account](#source-delivery-workflow-and-upload-account-task-059h2));
H3 added the server `deploy/Makefile`, the `service` command and the
integrated runbook for this path
([Server Makefile](#server-makefile-task-059h3)); F follows that runbook.

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
required certificate/redirect flow. SSH port 22 stays open for the
source-delivery Action; `AllowUsers deploy root schatten-upload` admits
`deploy` and key-only root from any address, and SSH accepts public keys only
(ADR-013 TASK-059J amendment).
Only Caddy publishes application ports. API, migration job, worker and database
have no public ports or domains. No Authentik, Traefik, Coolify, forward-auth,
`auth.lupaus.eu` or new staging environment is required.

Frontend and backend are separate immutable images built from the same release
commit. API, migration and worker share the backend artifact. Successful migration
gates API/worker startup; backend health gates frontend readiness. Preserve
one database-only prediction worker, its advisory lock, shutdown and health
contract. G's QA covers cold start, certificate issuance, persistent storage,
health/restart and host-reboot behavior without a circular dependency; see
[Production Runtime](#production-runtime-and-operator-commands-task-059g).

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

## Required Configuration Contract

The protected env file `/opt/apps/schatten-config/production.env` (mode `0600`,
owned by the operator running `deploy/bin/*`) is read by Compose for
interpolation and by the commands without being sourced. Never paste it or
rendered `docker compose config` output into evidence.

| Setting | Contract |
| --- | --- |
| `BACKEND_IMAGE`, `FRONTEND_IMAGE` | Never in the env file: `deploy/bin/*` passes the frozen image IDs from the release record |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Private PostgreSQL 18 initialization; use a URL-safe password such as `openssl rand -hex 32` |
| `DATABASE_URL` | Secret `postgresql://USER:PASSWORD@database:5432/DB`, shared by API/migration/worker and the backup runner |
| `OIDC_DISCOVERY_URL`, `OIDC_ISSUER` | Exact tenant-specific HTTPS metadata/issuer |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | Shared confidential app ID, production's own secret |
| `PUBLIC_ORIGIN` | `https://schatten.lupaus.eu`, exact canonical application Host |
| `DOCKER_SOCKET_GID` | Group ID of the host `/var/run/docker.sock` for Ofelia and the cleanup runner only |
| `SCHATTEN_BACKUP_PUBLIC_KEY` | Path of the backup encryption **public** key, outside `/opt/postgres-backups` |
| Optional `SCHATTEN_BACKUP_DIR`, `SCHATTEN_BACKUP_UID`/`GID` | Defaults `/opt/postgres-backups`, `10002:10002` |
| Optional `SCHATTEN_STATE_DIR`, `SCHATTEN_RELEASES_DIR` | Defaults `/opt/apps/schatten-state`, `/opt/apps/schatten-releases` |
| `SCHATTEN_OFELIA_CONFIG`, `SCHATTEN_DOCKER_SOCKET` | Leave unset in production (release job file, `/var/run/docker.sock`); disposable QA only. `verify-runtime-hardening` still checks the mounted job file |
| Optional `SCHATTEN_EDGE_SUBNET`, `SCHATTEN_EDGE_IP_RANGE`, `SCHATTEN_CADDY_IPV4` | Defaults `172.30.59.0/24`, `172.30.59.128/25`, `172.30.59.2`; change together only on subnet conflict, keeping the Caddy address outside the dynamic range |

`TRUSTED_CADDY_PEER_CIDRS` is derived in Compose as the fixed Caddy address
`/32` on the edge network; it is not operator configuration. There is no
upstream proxy, so the retired `CADDY_TRUSTED_PROXY_CIDRS` setting is gone and
Caddy treats the TCP peer as the client. Caddy strips browser forwarding headers
and sends fixed Host/scheme plus the peer address to FastAPI. Caddy certificate
and ACME account state persist in the `schatten_caddy_data` volume.
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
  `disable_root: false` keeps root's key usable, and the host's main
  `sshd_config` was observed to set `PermitRootLogin yes`; record the effective
  policy. Under TASK-059J root SSH stays, key-only (`prohibit-password`, set by
  the runbook 2.1 drop-in, which overrides the main file). `deploy` is a privileged
  operator account, not an application service identity. Validate any authorized
  SSH change before reload and keep a working session to avoid lockout.
- The OpenSSH UFW allow rule has no source restriction in the supplied config.
  Under the source-delivery amendment it stays open for GitHub-hosted runners;
  verify actual host/provider IPv4/IPv6 rules, and that `AllowUsers` and
  public-key-only settings are effective before relying on the open rule.
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

E supplies tested verification and remaining-setup commands in
[runbook sections 1-2](PRODUCTION-RUNBOOK.md#1-verify-the-existing-host-baseline-read-only),
including the read-only `audit-host`; G provides runtime tooling that uses the
installed Engine/Compose. Under the existing approval
boundaries, F configures missing DNS, Caddy TLS/storage, private PostgreSQL,
the upload-only account and GitHub `production` environment secrets for the
source-delivery Action, protected environment files and application
deployment. Git is not needed or used on the server for deployment; if it is
present, its presence is only recorded. `make` is required for
`deploy/Makefile` and is installed in F if the baseline lacks it. Make
only necessary, reviewed host changes. Store secrets privately, never in image layers, source control
or rendered Compose/log evidence.

Initially build on UpCloud from the manifest-verified source of an approved
exact commit and locked inputs.
Record commit/tool versions and matching immutable frontend/backend image
references, then freeze and verify their IDs/digests. Obtain release approval
and deploy those artifacts **without rebuilding**. Retain prior matched release
artifacts; mutable tags alone are insufficient release identity.

The image contexts are repository root for backend and `frontend/` for
frontend. G replaced the Coolify adapter checks with standard Compose, image and
disposable-daemon runtime checks (see `docs/TESTING.md`), preserving migration,
ingress, worker and secret coverage. Tests use disposable data and simulated
OIDC settings without tenant secrets.

OOM/failing builds, sustained memory/swap/CPU contention affecting the app or
unacceptable build duration trigger reassessment. GitHub Actions/GHCR can later
build the same artifact contract, followed by approved deployment of frozen
images. The source-delivery Action only copies files; no automatic deployment
or off-server build is implemented here.

### Source Delivery Workflow And Upload Account (TASK-059H2)

`.github/workflows/deploy-production.yml`, **"Deploy to production"**, is the
only way source reaches the host
([ADR-013](decisions/ADR-013-shared-entra-local-https-deployment.md#source-delivery-without-git-on-the-server)).
It starts only manually (`workflow_dispatch`). A first job without secrets fails
for any ref other than `refs/heads/main`; the upload job then runs in the
`production` environment with `permissions: contents: read`, one run at a time
(`concurrency: deploy-production`, never cancelling a running upload), and:

1. checks the secrets without printing them: `SSH_USER` must be
   `schatten-upload`, and `SSH_FINGERPRINT` must be a `SHA256:` fingerprint,
   because an empty one would make the action skip host-key verification;
2. checks out the commit with `actions/checkout` pinned by SHA (v5.1.0) and
   `persist-credentials: false`;
3. runs `.github/scripts/prepare-production-upload.sh release-source`, which
   calls `create-source-manifest.sh` and writes the commit, ref, run ID, upload
   folder and **manifest SHA-256** to the job summary;
4. downloads `drone-scp` 1.8.0, checks its recorded SHA-256 and hands that
   verified file to the action (`DRONE_SCP_RELEASE_URL=file://...` in
   `GITHUB_ENV`, which the action's entrypoint reads);
5. uploads with the developer-approved `appleboy/scp-action` v1.0.0, pinned as
   `ff85246acaad7bdce478db94a363cd2bf7c90345` (`source: release-source`,
   target `/opt/apps/schatten-upload/<commit>`, `overwrite: true`,
   `strip_components: 1`, `tar_tmp_path: /opt/apps/schatten-upload/`);
6. checks that the action was given the verified file's location and that the
   binary it ran has the same SHA-256, and appends "Upload completed" to the summary.

The action downloads `drone-scp` from a mutable GitHub release at run time, so
pinning the action alone does not pin that binary. Step 4 verifies the binary
**before** it ever sees `SSH_KEY`, and the action copies that verified file
instead of downloading again, so a changed release asset fails the run before
the upload. Step 6 checks the variable and the hash of the binary the action
ran, but it cannot see where the action copied it from. The disposable test
passes the variable to the entrypoint directly. In the first real run (F), the
upload step's log must therefore show
`Downloading drone-scp-1.8.0-linux-amd64 from file://.../drone-scp-release/v1.8.0`,
which confirms that `GITHUB_ENV` reaches the composite action. Accept only
uploads from successful runs. Changing the action, `drone-scp` or its inputs
requires developer approval, a new hash, the disposable test in
[TESTING.md](TESTING.md#source-delivery-workflow-and-upload-gate) and, if the
remote commands change, an `upload-gate` change.

GitHub `production` environment (created in F; deployment branches: `main`
only; environment secrets, not repository secrets):

| Secret | Value |
| --- | --- |
| `SSH_HOST` | Host name or public address of the UpCloud host |
| `SSH_USER` | `schatten-upload` (the workflow refuses anything else) |
| `SSH_KEY` | Private half of the dedicated upload key (Ed25519, no passphrase); never the `deploy` key |
| `SSH_PORT` | `22` |
| `SSH_FINGERPRINT` | `SHA256:...` of the host's **ECDSA** key: `ssh-keygen -l -E sha256 -f /etc/ssh/ssh_host_ecdsa_key.pub`. `drone-scp` 1.8.0 (Go x/crypto 0.37.0) prefers ECDSA P-256 over RSA and Ed25519, so with Ubuntu's default host keys the Ed25519 fingerprint fails with `host key fingerprint mismatch` |

`deploy/bin/upload-gate`, installed root-owned as `/usr/local/bin/upload-gate`,
is the forced command of the upload key. It matches the whole
`SSH_ORIGINAL_COMMAND` against the four commands the pinned action issues, as
captured in the disposable test, and runs its own fixed argv with the matched
paths, never the client's string:

| Captured command | Gate action |
| --- | --- |
| `scp -tr /opt/apps/schatten-upload/<10 letters/digits>.tar.gz` | `scp -t` (no directory records) to that new file; refused if the name exists |
| `mkdir -p /opt/apps/schatten-upload/<40-hex>` | Creates that folder `0750` (an existing real folder is accepted) |
| `tar -zxf <archive> --strip-components 1 --overwrite -C <folder>` | Refuses archives with members other than regular files and directories and folders that already hold anything else, then extracts with `--no-same-owner --no-same-permissions` |
| `rm -rf <archive>` | Removes only that regular file |

Everything else is refused with exit 1 and a short message, including the
action's `ver` probe (so it treats the host as Unix), shells, sftp, both scp
protocols, reads, other paths, extra words or spaces, and any other removal.
`restrict` removes port, agent and X11 forwarding and the pty. The gate uses
`umask 0027`, so `deploy` can read the upload through the group and other
accounts cannot. It runs one command at a time: it takes a non-blocking lock on
the upload area that the `scp`/`tar` it runs inherits, and refuses a parallel
session (`another upload-gate command is running`), so no session can replace
an archive or change a folder between the gate's checks and their use. The
action issues its commands one after another. `scp` and `tar` run under
`timeout --kill-after=10s 10m`, so even a session kept open on purpose releases
the lock after at most 10 minutes (the command then ends with exit 124); a real
upload of a few MB and its extraction take far less. Uploads, extractions and refusals are logged to syslog
(`upload-gate`, `auth.notice`).

Upload account setup for F, as root on the host after the SSH hardening
checks of [runbook 2.1](PRODUCTION-RUNBOOK.md#21-public-key-only-ssh-allowusers-and-port-22)
([runbook 2.2](PRODUCTION-RUNBOOK.md#22-operator-directory-upload-account-source-tools-and-github-environment)
gives the same steps with `sudo` and orders them with the tool bootstrap; the
upload key pair is created on an operator workstation and its private half goes
only into `SSH_KEY`):

```bash
# Login shell must be a real shell: sshd runs the forced command through it.
useradd --user-group --no-create-home --home-dir /home/schatten-upload --shell /bin/sh schatten-upload
passwd --lock schatten-upload
usermod --append --groups schatten-upload deploy
id schatten-upload   # only its own group; no sudo, docker, adm or deploy groups
# Root-owned home, .ssh and key file: the account cannot change its own restriction.
install -d -o root -g root -m 0755 /home/schatten-upload /home/schatten-upload/.ssh
install -d -o schatten-upload -g schatten-upload -m 0750 /opt/apps/schatten-upload
install -o root -g root -m 0755 <approved main tree>/deploy/bin/upload-gate /usr/local/bin/upload-gate
printf 'restrict,command="/usr/local/bin/upload-gate" %s\n' "$(cat schatten-upload.pub)" \
  >/home/schatten-upload/.ssh/authorized_keys
chown root:root /home/schatten-upload/.ssh/authorized_keys
chmod 0644 /home/schatten-upload/.ssh/authorized_keys
ssh-keygen -l -E sha256 -f /etc/ssh/ssh_host_ecdsa_key.pub   # SSH_FINGERPRINT
```

`deploy` must log in again for the new group. The account needs no sudo rule,
and no `deploy` group membership may be added to it. After the first receive,
the installed `upload-gate` must hash equal to its manifest entry, like
`schatten-receive`.

## Production Runtime And Operator Commands (TASK-059G)

This section describes the implemented tooling. The step-by-step procedure is
[PRODUCTION-RUNBOOK.md](PRODUCTION-RUNBOOK.md); F runs it only under explicit
operational approval. None of these commands provisions the host, installs
Docker, reruns cloud-init or changes swap.

### Services, Networks And Storage

| Service | Image | Network | Persistent state | Restart |
| --- | --- | --- | --- | --- |
| `frontend` (Caddy) | frozen frontend image ID | `edge` (fixed `172.30.59.2`), publishes TCP 80/443 | `schatten_caddy_data` at `/data` | `unless-stopped` |
| `backend` | frozen backend image ID | `edge` (ingress, Entra egress) + `data` | none | `unless-stopped` |
| `prediction-worker` | same backend image ID | `data` only | none | `unless-stopped` |
| `migration` (one-shot) | same backend image ID | `data` only | none | `no` |
| `database` | `postgres:18.6@sha256:…` | `data` only | `schatten_postgres_data` | `unless-stopped` |
| `ofelia` (profile `scheduler`) | `mcuadros/ofelia:0.3.22@sha256:…` | `network_mode: none` | none | `unless-stopped` |
| `backup-runner` (profile `ops`) | same pinned PostgreSQL image | `data` only | writes `/opt/postgres-backups` | `no` |
| `cleanup-runner` (profile `ops`) | `docker:28.5.2-cli@sha256:…` | `network_mode: none` | none | `no` |

`data` is an internal Docker network without external routing. Every service
and runner runs as a numeric non-root user with a read-only root filesystem,
`cap_drop: [ALL]`, `no-new-privileges`, no privileged mode or host namespaces,
and only declared `tmpfs` scratch space. Caddy binds 80/443 as user `10001`
through the namespaced `net.ipv4.ip_unprivileged_port_start=80` sysctl; the
image strips the upstream binary's file capability, which `no-new-privileges`
would otherwise refuse to execute. Caddy advertises HTTP/1.1 and HTTP/2 only,
because UDP 443 is not published.

Host storage mappings and required ownership:

| Host path | Use | Ownership / mode |
| --- | --- | --- |
| `/opt/apps` | Operator directory; `check-host` requires it writable by `deploy`; no container writes here | `deploy` (changed non-recursively if cloud-init left it root-owned) |
| `/opt/apps/schatten-upload/` | Upload area written only through `upload-gate`: `<commit>/` folders and the SCP action's transient `<10 letters/digits>.tar.gz` | `schatten-upload:schatten-upload`, `0750`; `deploy` reads through the group |
| `/opt/apps/schatten-upload/<commit>/` | Delivered upload (source plus `SOURCE_MANIFEST`), files `0640`/folders `0750`; read by `schatten-receive` only as data, never executed; stale files are ignored | `schatten-upload` |
| `/opt/apps/schatten-sources/` | Accepted sources; must exist, owned by `deploy` and not group/other writable, before the first receive | `deploy`, `0755` |
| `/opt/apps/schatten-sources/<commit>/` | Verified read-only source accepted by `schatten-receive` (only the manifest-listed files, manifest modes, `SOURCE_MANIFEST`); the only `build-release` input and where `make` and the tooling run from; `<commit>.incomplete` is transient staging | `deploy`; read-only tree |
| `/usr/local/bin/schatten-receive` | Installed receiver, run directly | `root`, not group/other writable |
| `/usr/local/bin/upload-gate` | Forced command of the upload key | `root`, `0755` |
| `/home/schatten-upload/.ssh/authorized_keys` | The one upload key with `restrict,command="/usr/local/bin/upload-gate"` | `root`, `0644`; home and `.ssh` `root` `0755` |
| `/opt/apps/schatten-config/production.env` | Protected configuration | `deploy`, `0600` |
| `/opt/apps/schatten-config/backup-public-key.asc` | Backup encryption public key (read-only mount) | `deploy`, `0644` |
| `/opt/apps/schatten-releases/<release-id>/` | Frozen, re-verified copy of the verified source, `release.env`, `build.log`; `current`/`previous` pointers; `retired/` | `deploy`; source read-only |
| `/opt/apps/schatten-state/` | `locks/*.lock` (read-only runner mounts), `deployments/*.env`, `restore-evidence/` (`0700`), transient `stopped-services` written by `service stop` and removed by `service start` | `deploy` |
| `/opt/postgres-backups` | Encrypted backups and manifests; existing contents preserved | `10002:10002`, `0700` (or `0750`) |
| `/opt/caddy` | Not mounted and not modified; Caddy state lives in `schatten_caddy_data` | unchanged |

Containers never write under `/opt/apps`. PostgreSQL data and Caddy
certificates live in named volumes created with the image directory ownership
(`999` and `10001`). Volumes survive container replacement and host reboot but
**are not backups**. Existing `/opt/postgres-backups` contents are never
overwritten or pruned unless they match the job-owned naming pattern below.
F sets its ownership explicitly; `check-host` only reports mismatches.

### Commands

Run the installed `/usr/local/bin/schatten-receive` directly, never from an
upload or a delivered Makefile. Run every other command from the verified
source copy of the target release (`/opt/apps/schatten-sources/<commit>/deploy`,
through `make` or `bin/...`), so the tooling matches the release's Compose file
and job scripts. The frozen release directory
(`/opt/apps/schatten-releases/<id>/source/deploy/bin/...`) holds an identical,
re-verified copy; a rollback runs the target release's copy from there.
Nothing is ever run from `/opt/apps/schatten-upload`.

| Command | Purpose |
| --- | --- |
| `audit-host` | Read-only, sanitized audit of the existing cloud-init baseline for F: cloud-init status counts, accounts, effective SSH including `AllowUsers` (`deploy`, `root` and `schatten-upload`, nothing else; `@<cidr>` patterns are a stricter fact), key-only root login (`prohibit-password`; a main-file override is a fact) and root key counts with the cloud-init `disable_root` prefix, UFW (SSH from `Anywhere` is attention only while password or keyboard-interactive login is enabled or root login is not key-only), listeners, Docker, swap/sysctl, timezone, fail2ban, updates, `/opt` storage, the upload account (locked, own group only, no sudo rules, root-owned key file, key **counts** with `restrict` and the gate as forced command, `deploy` in its group), the upload folder, `upload-gate` and `schatten-receive` ownership and hash, and the newest received sources with their manifest digest (or attention if a manifest is missing or staging was left behind); Git presence is only a fact. Before the first receive it runs from a workstation (`git show <commit>:deploy/bin/audit-host \| ssh deploy@<host> bash -s`), afterwards as `make audit` |
| `check-host [--allow-os-mismatch]` | Read-only check of Ubuntu 26.04, Docker Engine ≥ 25, Compose ≥ 2.24, Buildx, `python3`/`flock`/`sha256sum`/`tar`/`make` (not Git), env file privacy/keys, socket group/mode `660`, no Docker TCP listener, state/release/source directories and lock files, backup directory owner/mode and key placement; reports whether `/usr/local/bin/schatten-receive` is installed root-owned and not group/other writable (missing is a warning until F installs it); reports disk, memory and swap |
| `init-state` | Creates missing state, release and `/opt/apps/schatten-sources` directories and lock files only |
| `schatten-receive <manifest-sha256> [--upload <folder>]` | Installed root-owned receiver, run as `deploy`. Stages and checks only `SOURCE_MANIFEST` first (digest from the run summary, format, count, relative unique sorted paths, `SOURCE_REF=refs/heads/main`, `SOURCE_COMMIT` equal to the upload folder name), then copies only listed regular files without following symlinks, verifies the staged copy, applies manifest modes read-only and renames it to `/opt/apps/schatten-sources/<commit>`; never replaces an existing commit folder and removes staging on failure. Without `--upload` it uses the upload whose manifest has that digest. Prints `SOURCE_DIR=`, `SOURCE_COMMIT=`, `SOURCE_MANIFEST_SHA256=`. `--verify <folder>` re-verifies an accepted folder in place |
| `build-release --source <verified folder>` | Refuses any folder that is not directly under `SCHATTEN_SOURCES_DIR` (`/opt/apps/schatten-sources`), because `--verify` checks a folder only against its own manifest. Copies the verified folder into the release, re-verifies that copy against its manifest, then builds both images with pinned base images, locked dependencies and the manifest's `SOURCE_DATE_EPOCH`; no Git. `release.env` records `SOURCE_COMMIT`, `SOURCE_DATE_EPOCH`, `SOURCE_REF`, `SOURCE_RUN_ID`, `SOURCE_MANIFEST_SHA256`, image tags and IDs, Docker Engine/Compose/Buildx and kernel versions, duration and available memory |
| `deploy-release <id> --approval <ref> …` | Deploys frozen image IDs without building or pulling application images (see gates below) |
| `initialize status` | Read-only counts (schema version, active default metamodels, metamodel types, Users including deleted, active admins, identities, sessions, organisations); never names, emails or rows |
| `initialize reference-seed` / `initialize bootstrap-admin` | Explicit C/D first-initialization interfaces from the release backend image; bootstrap requires an interactive terminal |
| `backup-now [--reason pre-release\|manual]` | On-demand encrypted backup through the hardened backup-runner; prints `BACKUP_ID=` only after completion |
| `restore-rehearsal <backup-id> --private-key <file> [--passphrase-file <file>]` | Isolated restore and schema/data checks; writes evidence |
| `docker-cleanup [--dry-run\|--apply]` | Inspect or apply the weekly cleanup through the same hardened runner |
| `verify-runtime-hardening` | Checks effective container settings; failure blocks scheduler activation |
| `retire-release <id>` | Makes a non-current, non-previous release's images eligible for cleanup |
| `ops-status` | Release pointers, services stopped by `service stop`, recent backups, latest restore evidence and scheduler results |
| `service ps\|logs [service]\|stop\|start` | For the `current` release through its frozen Compose file: container state, the last 200 log lines (all or one service), stop of the running services (scheduler included; refused during a build, release or backup) and start of exactly those services in dependency order with health waits. Keeps containers, volumes and networks, never starts the migration job or the runners and never prints `docker compose config`, environments or `docker inspect` output. While the `stopped-services` record exists, `deploy-release` (including rollback) refuses, `ops-status` lists it and the services stay stopped across reboots |

### Server Makefile (TASK-059H3)

`deploy/Makefile` gives operators short commands over these tools. It runs from
the verified copy, `make -C /opt/apps/schatten-sources/<commit>/deploy
<target>`; receiving is not a target because the copy exists only after it.
Every target is a thin wrapper, so all gates stay in the commands:

| Target | Command |
| --- | --- |
| `help` | Lists the targets |
| `check`, `audit` | `check-host`, `audit-host` |
| `build` | `build-release --source <this copy>` |
| `deploy RELEASE= APPROVAL=` | `deploy-release <id> --approval <ref>` |
| `first-install RELEASE= APPROVAL=` | `deploy-release <id> --approval <ref> --first-install` |
| `status` | `ops-status` |
| `ps`, `logs [SERVICE=]`, `stop`, `start` | `service ...` |
| `backup` | `backup-now --reason manual` |
| `restore BACKUP= KEY= [PASSPHRASE=]` | `restore-rehearsal <id> --private-key <file> [--passphrase-file <file>]`; `KEY` and `PASSPHRASE` must be absolute paths |
| `cleanup-dry-run` | `docker-cleanup --dry-run` |

A missing required variable stops with a usage message and exit 2. Values
reach the commands through the environment, never through the recipe text, so
they cannot inject shell syntax. `deploy` and `first-install` refuse a release
whose ID does not end with the first 12 characters of the copy's commit, so a
release is always deployed with the tooling it was built from. No target runs
`docker compose down -v`, prunes, deletes volumes, runs down migrations,
restores production, seeds or bootstraps; `init-state`, `initialize`,
`verify-runtime-hardening`, scheduler activation, rollback, `retire-release`
and `docker-cleanup --apply` stay direct commands. The repository-root
`Makefile` has no production commands.

Commands run Compose with the project name `schatten`, the release's frozen
Compose file and a minimal environment, so stray shell variables cannot
override the protected configuration. `SCHATTEN_COMPOSE_OVERRIDE_FILE` exists
only for disposable QA (for example internal TLS) and is written into the
deployment record when used.

### Release, First Install And Rollback Gates

`deploy-release` takes an exclusive release lock and the shared maintenance
lock, then stops with nonzero status and unchanged `current`/`previous`
pointers at the first failed gate:

1. The frozen tags resolve to the recorded image IDs; pinned operational images
   are preloaded by digest (application images are never pulled or built).
2. The latest (or `--restore-evidence`) restore rehearsal is `STATUS=success`.
   A first install skips this gate and rehearses after initialization.
3. PostgreSQL is healthy; `--first-install` is refused if migration history
   exists, and a normal release is refused if it does not.
4. A pre-change `pre-release` backup completes; its ID is recorded. On first
   install this is the pre-migration baseline.
5. The one-shot migration job runs from the new backend image. A nonzero exit
   stops the release before the new API, worker or frontend is created; the
   previously running containers keep serving. Retry forward after fixing the
   cause.
6. API, worker and frontend become healthy, with exactly one worker.
7. Runner containers are recreated; Ofelia is updated if already running or
   started with `--enable-scheduler`; `verify-runtime-hardening` must pass or
   the scheduler is stopped.

Unchanged pointers do not mean the previous release is still serving. A failure
at gate 6 or 7, or during a rollback's API/worker start, happens after the new
release's containers started against the current schema. They may stay partly
running, and the failure message and `SERVICES_REPLACED=true` in the record say
so. Recover by fixing the cause and running the same release forward again, or
by rolling back to a schema-compatible release with `deploy-release <id>
--rollback --confirm-schema-compatible`. Never run down migrations or restore
the database.

Each run writes `deployments/<time>-<id>.env` with commit, image IDs, mode,
approval reference, previous release, backup ID, restore evidence, migration
exit code, whether services were replaced, scheduler state and result. It
contains no secrets or identities.

First installation: `deploy-release <id> --approval <ref> --first-install`,
then `initialize status`, `initialize reference-seed`, `initialize
bootstrap-admin` in a private terminal, `backup-now`, `restore-rehearsal` of
that backup, and only then `deploy-release … --enable-scheduler` to activate
schedules. The runbook's
[first-installation table](PRODUCTION-RUNBOOK.md#4-first-installation-fresh-database-only)
lists the expected status counts after each step. Subsequent releases never
bootstrap.

Rollback: `deploy-release <older-id> --approval <ref> --rollback
--confirm-schema-compatible`. The confirmation records a human
expand/contract review. The command also verifies inside the older image that
its migrations are an exact prefix (version, filename, checksum) of the applied
history, then replaces API and worker together (and then the frontend) without
running the migration job. It never runs down migrations, deletes volumes,
resets or restores the database. The first release has no rollback target.

### Encrypted Backups And Restore Rehearsal

- **Format:** `pg_dump --format=custom --compress=zstd:3` (one consistent
  snapshot of the application database, restorable with PostgreSQL 18
  `pg_restore`), streamed directly into `gpg --encrypt` for the configured
  public key (AES-256, integrity-protected). Plaintext never touches disk.
- **Keys:** the runner mounts only the public key and refuses a key file that
  contains secret key material. Generate the key pair outside the backup
  directory, keep the private key and any passphrase offline or in separately
  protected operator storage, and record who can reach them for recovery.
  Losing the private key makes every backup unrecoverable.
- **Cluster objects:** the dump covers the application database's schema,
  data and sequences. The only cluster role is recreated from the protected
  `POSTGRES_USER`/`POSTGRES_PASSWORD` configuration; restores use
  `--no-owner --no-acl` into that role.
- **Files:** `schatten-<UTC YYYYmmddTHHMMSSZ>-<reason>-<6 hex>.dump.gpg` plus a
  `.manifest` (`BACKUP_ID`, reason, completion time, size, SHA-256, key
  fingerprint, server/pg_dump versions, schema migration version, table count),
  mode `0600`. The dump is written to `.incomplete/`, checked for size and a
  public-key encryption packet, checksummed and fsynced, then published by
  rename; the manifest is published last and is the completion marker.
- **Reporting:** one `status=completed … backup_id=… sha256=… retention=…
  free_bytes=…` or `status=failed … error="…"` line, never data, URLs or
  passwords. Missing key, missing/wrong credentials, unwritable directory, full
  disk and encryption errors exit nonzero and publish nothing. `DATABASE_URL`
  is split into libpq variables so the password never appears in process
  arguments. Temporary files are removed on failure; interrupted leftovers in
  `.incomplete/` are removed after one day.
- **Retention:** after a successful backup, completed job-owned pairs whose
  filename timestamp is older than **7 days** are removed, the newest backup is
  always kept, and orphaned job-owned dumps without a manifest are removed after
  one day. Any other file is never touched. A retention failure exits `2` after
  reporting the completed backup.
- **Non-overlap:** backups hold the shared maintenance lock and an exclusive
  backup lock (default wait 30 minutes); the scheduled and on-demand runs
  cannot overlap each other or the weekly cleanup.
- **Restore rehearsal:** verifies the manifest checksum, starts a disposable
  PostgreSQL 18 on a new internal network with no ports, decrypts inside a
  hardened runner (backup user, backup directory mounted read-only) with the
  separately supplied private key and optional passphrase, which are streamed
  on stdin into the runner's tmpfs and never bind-mounted, runs
  `pg_restore --exit-on-error --single-transaction`, and checks schema migration
  version/contiguity, table count, validated constraints and per-table row
  counts. The target and its volume are always removed. Evidence
  (`restore-evidence/<time>-<backup-id>.txt`) holds identifiers, check results
  and counts only. Production is never overwritten.

Backup size, the encrypted copy and the rehearsal target all use the same small
host's disk; `check-host` and every backup line report free space. These
same-host backups do not protect against host or disk loss.

### Operational Scheduler (Ofelia) And Docker Control Boundary

`deploy/ofelia/config.ini` is the reviewed job file, mounted read-only from the
frozen release. Ofelia starts without `--docker`, so container labels are
never read as jobs, and each `job-run` names a pre-created Compose container
(`container =`) instead of an image or command. Ofelia therefore creates,
pulls and deletes nothing; the runners' effective settings are the Compose
settings verified by `verify-runtime-hardening`. Schedules use the explicit
`TZ=Europe/Helsinki`:

| Job | Schedule | Runner |
| --- | --- | --- |
| `postgres-backup` | daily 02:30 | `schatten-backup-runner` |
| `docker-cleanup` | Sundays 04:30 | `schatten-docker-cleanup` |

`no-overlap` prevents a job overlapping itself; the file locks exclude the
other operations. Ofelia logs each run with `failed: true|false` and the
runner's output; there is no automatic retry. A failed daily backup is
visible through `ops-status`/`docker logs` and is handled by running
`backup-now` after fixing the cause.

The Docker socket is mounted only into Ofelia and the cleanup runner, both with
`network_mode: none`, user `65534` and the socket group as primary group; the
backup runner, application and database never get it. There is no Docker TCP
listener and socket permissions stay `660`. **Docker API access is
host-administrator-equivalent**: a `:ro` socket mount would not make API calls
read-only, and a compromised Ofelia or cleanup runner could reach every
container and its secrets despite the separated mounts. Only authorized host
operators may change the job file, and the Ofelia or job-image digests change
only through a reviewed update. Without socket group access, Ofelia fails
visibly (`permission denied`) instead of widening permissions.

### Weekly Docker Cleanup

`deploy/ops/docker-cleanup.sh` needs the maintenance lock exclusively and
exits `75` (skipped) while a build, release, rollback, backup or restore holds
it. With the default 7-day window it removes only exited/dead containers
without the `eu.lupaus.schatten.retain=true` label (set on every Schatten
Compose container, including the migration job and runners); dangling images and `schatten-backend`/`schatten-frontend` images
not referenced by any non-retired release record or any container; and BuildKit
build cache older than 7 days. It never runs `docker system prune`, never
touches volumes, networks, running containers or other repositories' tagged
images, and cannot reach `/opt/postgres-backups` or Caddy/PostgreSQL volumes.
`docker-cleanup --dry-run` lists candidates. Any failed container or image
listing, removal or build-cache prune exits `1` with `status=failed`. A failed
listing aborts before its phase removes anything. Release records protect the current, previous and any frozen
but not yet deployed release; `retire-release` makes older ones eligible.
Docker cleanup is separate from the 7-day backup retention.

### Health, Restart, Reboot And Certificates

The database is healthy on `pg_isready`, the API on its `/health` check, the
worker on its lock-owning health command, and Caddy on a loopback-only
`127.0.0.1:8081/health` listener that does not depend on certificates. Startup
order is database → migration → API/worker → frontend. Certificate issuance
starts after Caddy starts and nothing waits on it, so a slow or failed ACME
order cannot block readiness. On reboot, Docker restarts the `unless-stopped`
services from their existing containers without Compose ordering: the API
health check does not query the database, so database-backed requests fail
until PostgreSQL is healthy, and a worker that cannot connect exits and is
restarted. The completed migration job and the runners are not rerun. The API fetches
Entra discovery during startup and exits if it is unreachable; the restart
policy retries, and the frontend stays gated until the API is healthy. Caddy obtains
and renews certificates over HTTP-01 on port 80 or TLS-ALPN-01 on port 443
and keeps them in `schatten_caddy_data`.

### Build Relocation And Managed PostgreSQL

`release.env` records build duration and available memory. Reassess
off-server builds after OOM kills or failed builds, sustained swap/CPU/memory
contention with the running services during builds, or build time the
operator finds unacceptable. A later GitHub Actions/GHCR pipeline must produce
the same two images from the approved commit and hand over digests in the same
release-record contract; nothing here implements it or any automatic
deployment.

`DATABASE_URL` stays portable to a managed PostgreSQL service
(`?sslmode=`/`sslrootcert=` are honoured by the backup runner). The worker needs
session-level advisory locks, so a managed endpoint must provide direct or
session-mode pooling, not transaction pooling. Data transfer, cutover and
backup placement need the separate plan described above.

### Known Limitations

- Docker publishes IPv6 through its userland proxy, so IPv6 clients may reach
  FastAPI with the Docker gateway as client address, which weakens per-client
  rate limiting and audit addresses for those clients. IPv4 preserves the
  client address. The runbook recommends no `AAAA` record initially; F records
  the effective behavior and the DNS decision.
- Backups share the host and disk with the database (accepted until an
  off-server solution is planned).
- `docker compose config` output and the env file contain secrets.

## First Initialization (Reference Seed And Bootstrap Implemented)

For a fresh database, the explicit order is:

1. Apply reviewed forward migrations through the release backend image.
2. Run the implemented `python -m app.seed_reference_data` command from that
   artifact with only `DATABASE_URL`. It shares the development seed's non-user
   metamodel SQL/JSON, inserts atomically only when no active default exists,
   and otherwise preserves it unchanged.
3. Run interactive `python -m app.bootstrap_admin` from that artifact in a private
   operator terminal with screen sharing and session recording disabled. Supply
   `DATABASE_URL` through protected environment configuration and enter the
   designated Entra name/email only at the prompts, never in arguments or
   repository records. The command validates and trims both fields and creates
   one fixed-role admin only when the entire users table is empty, including
   soft-deleted rows.
4. First direct-Entra login links the pre-provisioned admin normally. Provision
   subsequent Users through existing admin functionality, then run limited smoke.

C's reference seed is database-only, creates no Users, identities or sessions,
and does not initialize OIDC. D's bootstrap has the same configuration boundary
but accepts private interactive administrator input. It serializes the complete
table-emptiness check and insert against all User writers. Existing active or
soft-deleted rows cause a nonzero refusal without updates, revival, promotion or
new rows; do not bypass that refusal with manual SQL. The bootstrap leaves audit
actors null as approved and creates no identity or session. Neither command runs
automatically on application startup. Subsequent releases run migrations, not
first-admin bootstrap. Never run the full `002_seed_development_data.sql` in
production.

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

E integrated B/C/D/G and verified the commands against disposable
infrastructure; the executable sequence, smoke and release record are in
[PRODUCTION-RUNBOOK.md](PRODUCTION-RUNBOOK.md). F requires E and explicit
operational approval. Before deployment:

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
verification. [E](../tasks/TASK-059E-upcloud-docker-runbook-qa.md) integrates them
in the runbook and disposable QA.
[H](../tasks/TASK-059H-github-source-delivery-architecture.md) amends ADR-013
for Git-free source delivery after E;
[H1](../tasks/TASK-059H1-source-manifest-git-free-build.md) (manifest, receiver,
Git-free build) precedes
[H2](../tasks/TASK-059H2-upload-account-deploy-action.md) (upload gate and
workflow), and [H3](../tasks/TASK-059H3-server-makefile-runbook.md) (server
Makefile and runbook) follows both.
[F](../tasks/TASK-059F-first-production-rollout.md) follows H3 and explicit
operational approval. Production Authentik remains excluded.
