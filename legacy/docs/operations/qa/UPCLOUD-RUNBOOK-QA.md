# UpCloud Runbook And Integrated QA (TASK-059E)

> Historical record (2026-11-06): the identity setup (Microsoft Entra) recorded here was replaced by Authentik (ADR-017). Kept as evidence of the runs it records.

This record holds TASK-059E evidence for the integrated
[production runbook](../../runbooks/production.md): B/C/D/G combined in the
documented operator sequence and executed against **disposable** local
infrastructure with synthetic secrets, a throwaway passphrase-protected GPG key
and a simulated Entra discovery endpoint. **No production host, DNS, UpCloud
firewall, GitHub, Entra tenant, certificate, backup directory or database was
touched, and no provider or production action occurred.** G's original runtime
results stay in [PRODUCTION-RUNTIME-QA.md](PRODUCTION-RUNTIME-QA.md); historical
Authentik/Coolify results are not counted here.

## Environment

| Item | Value |
| --- | --- |
| Date | 2026-09-28 |
| Base | `main` at `a3b18aa1b25e` plus the TASK-059E working tree, committed only in scratch clones as `8aed4bb77add` (run A) and `fe9ca98c68b9` (run B); these are not repository commits |
| Run A | Workstation Ubuntu 24.04 userland (GNU coreutils 9.4), Docker CLI/Compose 5.1.0, isolated daemon `docker:28.5.2-dind@sha256:2a232a42…` |
| Run B | `ubuntu:26.04` (26.04.1) operator container as non-root `deploy` in the socket group: uutils coreutils 0.8.0, GNU tar 1.35, util-linux flock 2.41.3, mawk 1.3.4, Git 2.53.0, Docker CLI 29.8.1, Compose 5.5.1 and Buildx 0.37.1 from Docker's `resolute` APT repository; isolated daemon `docker:29.8.1-dind@sha256:3f3c01aa…` (containerd snapshotter enabled by default) |
| Pinned runtime images | Unchanged from G: `postgres:18.6@sha256:4ef4dbc9…`, `mcuadros/ofelia:0.3.22@sha256:efcbe2c5…`, `docker:28.5.2-cli@sha256:625d9431…`, `caddy:2.11.4-alpine@sha256:5f5c8640…` |

Run B is the closest available approximation of the target host: the Ubuntu
26.04 userland and the Docker packages the reported cloud-init installs, with
the Engine major version that repository currently ships. It is still a
container driving a Docker-in-Docker daemon, not the UpCloud host.

## Disposable End-To-End Runbook Sequence

Commands:

```bash
# Run A, from a scratch clone with a WIP commit:
QA_LOG_FILE=<file> .github/scripts/verify-production-runtime.sh
# Run B, same clone mounted at the same path with /tmp shared:
docker run --rm --user deploy -v /var/run/docker.sock:/var/run/docker.sock -v /tmp:/tmp \
  -w <clone> -e QA_LOG_FILE=<file> \
  -e QA_DIND_IMAGE=docker.io/library/docker:29.8.1-dind@sha256:3f3c01aaaebf7cce837356b688b7c059a4749f10bd7660dec7c58fc454a283f0 \
  <ubuntu:26.04 image with git/curl/openssl/python3/iproute2/procps and Docker's CLI plugins> \
  bash .github/scripts/verify-production-runtime.sh
```

Result: **pass in both runs** (`EXIT=0`, 45 `PASS` assertion groups each;
G's run recorded 38). Build from a cold cache took 603 s (run A, concurrent
with other QA) and 354 s (run B) inside the isolated daemons. Both runs used
the scratch clones' harness, whose closing banner still read "TASK-059G"; the
banner text was updated afterwards.

New TASK-059E checks, in runbook order (section 4):

| Runbook step | Evidence (both runs) |
| --- | --- |
| 2 First install | Approval required; pre-migration baseline backup; all 15 migrations; one worker; hardening passed; second `--first-install` refused |
| 4 No implicit seed | `initialize status` after deployment: `schema_version=15`, `active_default_metamodels=0`, `users_including_deleted=0`, `user_identities=0`, `auth_sessions=0`, `organisations=0` |
| 5 Reference seed | `Reference data seed completed.`; `active_default_metamodels=1`, `node_types=11`, non-zero `allowed_connections`, still no Users or organisations; the repeat printed `Reference data seed skipped: an active default already exists.` and the status was byte-identical |
| 6 Bootstrap | Non-interactive session refused; driven through a pseudo-terminal with synthetic input: prompts for display name and Entra email, `Administrator bootstrap completed.`, the synthetic name and email each appeared exactly once (the terminal echo) and never in command output |
| 7 Status | `users_including_deleted=1`, `active_admins=1`, `user_identities=0`, `auth_sessions=0`, `organisations=0`: no development Users or business data |
| 6 Repeat | Second bootstrap: `Administrator bootstrap refused: the users table is not empty.`; status unchanged |
| 8-9 Initialized backup and restore | `backup-now` of the initialized database; restore with a **wrong passphrase** failed (`decryption or pg_restore failed`, `STATUS=failed` evidence) and that failed latest evidence blocked `deploy-release` ("not successful"); restore with the right passphrase passed checksum, decrypt/restore, schema version 15, 27 tables and constraints, with `users=1`, `metamodels=1`, `node_types=11`, `allowed_connections=14`, `user_identities=0`, `auth_sessions=0`, `organisations=0` |
| 11 Scheduler activation | Same-release `deploy-release --enable-scheduler` passed the restore gate and hardening including Ofelia; both jobs ran with `failed: false` |
| Secret scan | Synthetic database password, client secret, **key passphrase** and bootstrap email absent from the QA log, all container logs and image history |

All G checks were rerun unchanged in both runs and passed: host prerequisites,
frozen build, edge (only Caddy 80/443, TLS, HSTS/CSP, `308` redirect, SPA,
spoofed forwarding `401`, direct non-Caddy peer `400`), backup file mode/
encryption, backup failure cases (missing/secret key, missing/wrong credential,
permission denied, disk full, overlap), 7-day retention with fixture
timestamps, certificate/database persistence across replacement, daemon-restart
recovery without rerunning migration or runners, Ofelia label isolation and
socket-group failure, `verify-runtime-hardening`, release-aware cleanup
(dry-run, lock skip, failure reporting, protected volumes/backups/current/
previous images), the missing-evidence gate, failed-migration isolation,
post-migration failure reporting with fix-forward, and schema-compatible
rollback with refusal on divergent history.

Engine 29 compatibility: with the containerd image store enabled by default,
`build-release` recorded `sha256:` image IDs that matched their tags, frozen
deployments resolved them, `docker-cleanup` removed and protected the fixture
images correctly, and Ofelia 0.3.22 talked to the Engine 29 API without errors.
No tooling change was needed for Engine 29.

## Ubuntu 26.04 Operator-Tool Findings

- **Defect found and fixed:** in run B, `check-host` aborted after its last
  check because its informational `df` disk report failed on a missing
  `/var/lib/docker` under `set -e`/`pipefail`. The same abort would hit a host
  with a non-default Docker data root. The report is now non-fatal
  (`deploy/bin/check-host`); uutils `df -P -B1` itself behaves like GNU. Run B
  used the fixed script; run A predates the one-line fix, which does not affect
  its results.
- All other `deploy/bin` commands ran unchanged under uutils coreutils 0.8.0
  (`stat -c`, `date -u`, `sort -V`, `readlink -f`, `od`, `install`, `mktemp`),
  GNU tar `--transform`, mawk and util-linux `flock`.
- Ubuntu 26.04's `sudo` is sudo-rs 0.2.13; `sudo -n` read-only probes behaved
  as expected.

## Host Audit (`deploy/bin/audit-host`)

Disposable `ubuntu:26.04` container set up like the reported baseline: locked
`deploy` and default `ubuntu` users with one authorized key each, root key,
NOPASSWD sudo for `deploy`, `sshd` with the cloud-init
`PasswordAuthentication no` drop-in, UFW enabled with OpenSSH/80/443 from
`Anywhere`, a fail2ban `sshd` jail (5/600/3600), `Europe/Helsinki`, and root-owned
`/opt/apps`, `/opt/caddy`, `/opt/postgres-backups` (with one pre-existing file).

| Check | Result |
| --- | --- |
| Run as `deploy`, directly and as `ssh … bash -s` from stdin | All 12 sections, `EXIT=0`; identical findings |
| Expected baseline attention items | `permitrootlogin=prohibit-password` (root SSH not disabled), SSH allowed from `Anywhere`, `/opt/postgres-backups` owner `0:0` mode `755` |
| Matching items | Ubuntu 26.04, tools, password/keyboard-interactive disabled, all accounts `L`, key counts only, UFW active, only 22 listening, fail2ban `5/600/3600`, timezone, unattended-upgrades enabled, no pending reboot |
| Container artefacts (not host findings) | cloud-init `not-started`, host sysctl values, no systemd unit states, no Docker daemon |
| cloud-init parser with stub output | `done` -> `ok`; `degraded done` with two recoverable errors and exit 2 -> `attention` with counts only |
| Workstation (Ubuntu 24.04, no passwordless sudo) | Privileged probes reported `missing` instead of failing; desktop listeners and a published database port flagged as attention |
| Sanitization | No key material, banned addresses, user-data or environment values in output |

Review follow-up (2026-09-29, Step 13 round 1, finding F-001): `audit-host`
now flags a `/opt/apps` or existing Shadow path not owned by `deploy`,
because `check-host` and the setup steps write there as `deploy`. In a fresh
`ubuntu:26.04` container with a root-owned `/opt/apps` holding one unrelated
file, the audit reported attention for `/opt/apps`; after the runbook 2.2
non-recursive `chown`/`chmod`, the unrelated file stayed `root:root 0644`,
`deploy` created `shadow-config`, `shadow-state` and `shadow-releases`,
and the audit reported them `ok` while flagging a pre-created root-owned
`/opt/apps/shadow` for review. It ran directly and through `bash -s` with
exit 0, and shellcheck `--severity=warning` passed. The runbook 10.2 reboot
form (`sudo flock --exclusive --nonblock ... systemctl reboot`, with `echo` in
place of the reboot) ran when idle and printed `busy` while a shared holder
existed.

Three defects found while writing it were fixed before these runs: multi-word
cloud-init status parsing, `set -e` exits on a missing `docker` group and on
empty `grep` counts, and verbose UFW rules (`22/tcp (OpenSSH)`) not matching the
SSH-from-Anywhere check.

## Other Runbook Commands

| Command group | Result |
| --- | --- |
| SSH drop-in `PermitRootLogin no`, `sshd -t`, `sshd -T` (26.04 container) | Valid; `audit-host` then reported root login disabled |
| UFW restrict-then-delete (26.04 container) | Restricted 22/tcp rule added; `ufw delete allow OpenSSH` removed the IPv4 **and** IPv6 OpenSSH rules (runbook warns); 80/443 unchanged; audit no longer flagged `Anywhere` |
| Offline key generation/export with gpg 2.4.8 (26.04 container) | 40-character fingerprint; public file has no private block; files were `0600` under `umask 077`, so the runbook adds `chmod 0644` for the public key |
| Maintenance-lock idle check (`flock --exclusive --nonblock`) | `busy` while a shared holder existed, `idle` afterwards |
| `systemctl reload ssh`, fresh SSH sessions, provider firewall, DNS, GitHub deploy key, Entra | Not testable without the real host/provider: pending F |

## Standard Checks Run Locally

| Check | Result |
| --- | --- |
| `.github/scripts/verify-production-compose.sh` | Pass |
| `.github/scripts/verify-release-compose-failure.sh` (disposable project) | Pass: migration exit 1, no backend/worker/frontend started |
| `.github/scripts/verify-production-frontend.sh` (locally built production image) | Pass |
| `.github/scripts/verify-production-worker.sh` (migrated disposable PostgreSQL 18) | Pass |
| shellcheck `--severity=warning` on `audit-host`, `initialize`, `check-host` and the harness | Pass |
| Backend full suite with `MIGRATION_TEST_DATABASE_URL` on disposable PostgreSQL 18 (auth, seed parity, bootstrap, predictions, migrations integration included) | 459 passed |
| `ruff check`, `pyright` | Pass, 0 errors |
| Frontend `eslint`, `vitest run` (includes `localCsp`), `tsc -b && vite build` | Pass, 262 tests (run with `--config.verify-deps-before-run=false`: pnpm's pre-run dependency check fails without a TTY; nothing was installed) |
| `scripts/verify-local-direct-entra-config.sh` with synthetic files, and `make local-verify` with the private local files | Pass |
| `python3 scripts/ai_review_records.py validate` | Pass |
| `docs/architecture/diagrams/component-authentication-topology.puml` re-rendered | SVG updated |

## Local HTTPS And Direct-Entra Boundary

Read-only probes against the already-running local stack (working tree of this
branch, local CA trusted with `--cacert`, no login performed):
`https://app.localhost/health` returned `OK`; HSTS, CSP with the Vite refresh
hash and `wss://app.localhost`, `no-referrer`, `nosniff` and `DENY` were
present; `/api/v1/auth/session` without a cookie returned `401`; the Vite HMR
WebSocket upgrade through Caddy returned `101` with the per-server token
(`400` without it, which is Vite's token check, not a Caddy fault). Simulated
OIDC behavior is covered by the backend suite above.

**Live local Entra browser evidence** is the authorized TASK-059B run recorded
on 2026-09-24 in the
[authentication checklist](AUTHENTICATION-QA-CHECKLIST.md#task-059b-direct-entra-local-evidence);
E did not repeat it. F confirms it still covers each release's authentication
scope or records a new authorized run. It does not establish production DNS,
TLS or client-secret correctness.

## Acceptance Mapping

| Criterion | Status |
| --- | --- |
| Ofelia/runner hardening passes disposable QA; activation checks cover effective settings and privileged API access | Tested (E), runs A and B; runbook section 9. Production activation pending F |
| Runbook starts from the reported baseline, separates reported/verified, avoids bootstrap repetition; SSH/firewall/storage checks explicit | Runbook sections 0-2 and `audit-host`; live results pending F |
| Commands match B/C/D/G and Ubuntu 26.04; links resolve | Run B plus 26.04 container checks; link check below |
| Integrated migrations -> seed -> bootstrap without development Users; repeat/refusal documented | Tested (E), runbook section 4 |
| Simulated OIDC, HTTPS, production Compose, ingress/worker checks pass; historical results not claimed | Tested (E), this record |
| Live local Entra separately recorded; production smoke pending F | TASK-059B record; smoke pending F |
| Approval/frozen artifacts, narrow smoke, schema-compatible rollback; missing evidence blocks release | Runbook sections 3, 5-7; missing **and failed** evidence gates tested |
| Daily encrypted backups and 7-day retention tested with disposable data; isolated restore evidence separate from F activation | Tested (E); production activation pending F |
| Managed-PostgreSQL planning preserves backup policy; no provider/production action | Runbook section 12; none occurred |

Relative Markdown links in the changed documents were checked to resolve,
including heading anchors.

## Not Verified Here (F)

- Real host audit results, fresh SSH sessions and password refusal, root SSH
  and SSH-source decisions, UpCloud firewall IPv4/IPv6 rules.
- `/opt/apps` ownership change and `deploy` ownership of the Shadow paths on
  the real host; Git installation, GitHub read-only deploy key and clone.
- `production.env`, the production backup key pair, its vault storage and
  recovery custodians, `/opt/postgres-backups` ownership change.
- DNS, public Let's Encrypt issuance, effective IPv6 client addresses.
- Entra production callback/logout, production secret, assignments and
  consumer-checked Authentik/Graph cleanup.
- The actual build on the UpCloud host (duration/memory), first install,
  initialization, backups, restore rehearsal, schedule activation, the first
  scheduled backup and weekly cleanup, and the narrow production smoke.

## Limitations

- Docker-in-Docker daemons stand in for the host; host reboot is simulated by a
  clean daemon restart, and systemd behavior was not exercised.
- Both QA releases in each run were built from the same commit, so rollback
  proves the gates and coordinated path, not an actual image change (as in G).
- Engine 29 was tested at 29.8.1; F records the host's actual version, and
  `check-host` accepts Engine 25 or newer.
