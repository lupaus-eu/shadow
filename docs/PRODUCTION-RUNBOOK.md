# Production Runbook: UpCloud Docker Host

This is the integrated operator runbook for Schatten on the existing UpCloud
**Ubuntu 26.04 LTS** host: Docker Engine/Compose, direct Caddy TLS for
`https://schatten.lupaus.eu`, private PostgreSQL 18 in Docker, direct Entra
OIDC, daily encrypted on-server backups with 7-day retention and the hardened
Ofelia scheduler. It integrates TASK-059B/C/D/G under
[ADR-013](decisions/ADR-013-shared-entra-local-https-deployment.md). The
architecture, configuration contract and tooling reference live in
[DEPLOYMENT.md](DEPLOYMENT.md). The disposable verification behind every
command below is recorded in
[UPCLOUD-RUNBOOK-QA.md](qa/UPCLOUD-RUNBOOK-QA.md).

**This runbook authorizes nothing.** Every host, DNS, firewall, GitHub, Entra,
backup-activation and production step is TASK-059F work and needs explicit
operational approval first. Until F records it, every live fact below is
*reported* or *pending*, never *verified*.

## 0. Ground Rules

Evidence labels used in this runbook and the F record:

| Label | Meaning |
| --- | --- |
| Reported | Operator-supplied configuration (the cloud-init baseline); not evidence |
| Tested (E) | Exercised against disposable local infrastructure; see the QA record |
| Verified (F) | Observed on the real host/provider under approval and recorded by F |
| Pending | Not yet performed; never mark it complete without doing it |

Always:

- Run tooling from the frozen release you act on:
  `B=/opt/apps/schatten-releases/<release-id>/source/deploy/bin`. Only
  `build-release` runs from the reviewed checkout.
- Record sanitized outcomes only: identifiers, counts, statuses, versions and
  times. Keep a working SSH session open while changing SSH or firewall rules.
- Stop at the first failed gate. Commands leave release pointers unchanged on
  failure and print the next safe action.

Never:

- Rerun cloud-init, recreate or format swap, reinstall Docker or overwrite
  existing `/opt` contents as a routine step.
- Paste `production.env`, `docker compose config` output, full
  `docker inspect` output of `backend`, `migration`, `prediction-worker`,
  `database` or `backup-runner` (their environment holds secrets), private
  keys, passphrases, SSH keys, cloud-init user-data, raw auth/callback logs,
  cookies, tokens, names or personal emails into any record.
- Run `docker compose down -v`, `docker volume rm`/`prune`, `docker system
  prune`, down migrations, manual production SQL writes, the full development
  seed (`002_seed_development_data.sql`) or any restore onto production.
- Deploy without a recorded human approval, or treat a merge to `main` as
  approval.

`deploy` is a **privileged operator**: passwordless sudo plus membership of the
`docker` group, which is itself host-administrator-equivalent. It is not an
application identity; no application container runs as it.

## 1. Verify The Existing Host Baseline (Read-Only)

The host was set up by cloud-init (see the
[reported baseline](DEPLOYMENT.md#existing-cloud-init-baseline-operator-reported)).
This section inspects it without changing anything.

### 1.1 Access from an operator workstation

Keep one session open throughout. In a second terminal:

```bash
# Fresh key-only session as deploy (must succeed).
ssh -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no deploy@<host> true
# Password and keyboard-interactive must be refused ("Permission denied (publickey)").
ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password,keyboard-interactive deploy@<host> true
# Record the host key fingerprint you accepted, compared with the UpCloud console.
ssh-keygen -F <host> -l
```

Repeat the refusal check for `root` and the image's default user. Record only
"accepted/refused" per account, not key material.

### 1.2 Sanitized host audit

`deploy/bin/audit-host` inspects the effective state with `sudo -n` read-only
commands and prints counts and settings only. It does not need the checkout,
so run the reviewed version straight from the workstation:

```bash
git show <reviewed-commit>:deploy/bin/audit-host | ssh deploy@<host> bash -s > audit-host.txt
```

It reports `ok`, `attention`, `manual` and `missing` lines and a final
`SUMMARY attention=N missing=M`. It exits 0: attention items are decisions for
F, not script failures. It covers:

| Area | Checked |
| --- | --- |
| OS/tools | Ubuntu 26.04, kernel, uutils coreutils and sudo-rs versions, `git`, `python3`, `curl`, `gpg`, `openssl`, `flock`, `ss` |
| cloud-init | `cloud-init status --format json`: status, error and recoverable-error **counts** only |
| Accounts | Human accounts and root: password status (`L` locked), authorized-key **counts**, `sudo`/`docker`/`adm` membership; `docker` group members; passwordless sudo for `deploy` |
| SSH | `sshd -T` effective `permitrootlogin`, password/keyboard-interactive/pubkey settings, `authenticationmethods`, `allowusers`/`allowgroups`, ports; `Match` blocks; `ssh.socket`/`ssh.service` state |
| Firewall | `ufw status verbose` rules; SSH allowed from `Anywhere` |
| Listeners | Non-loopback TCP listeners other than 22/80/443; any 2375/2376 Docker API listener |
| Docker | Engine/containerd/Compose/Buildx versions, storage/cgroup/security options, socket mode/group, `daemon.json` keys, containers publishing ports other than 80/443 |
| Resources | Swap devices, fstab swap entries, `vm.swappiness`/`vm.vfs_cache_pressure`, CPUs, memory, disk for `/`, `/var/lib/docker`, `/opt` |
| Time | Timezone `Europe/Helsinki`, NTP synchronization |
| fail2ban | `sshd` jail, current/total ban **counts** (no addresses), `maxretry`/`findtime`/`bantime` |
| Updates | unattended-upgrades units, APT periodic and automatic-reboot settings, pending reboot, held packages |
| Storage | Owner/mode/entry count/filesystem of `/opt/apps`, `/opt/caddy`, `/opt/postgres-backups` and the Schatten paths; `deploy` ownership of `/opt/apps` and existing Schatten paths; completed-manifest count; checkout remote without embedded credentials |

Expected attention items on the reported baseline, and the F decision each
needs:

| Audit finding | Why | F action (approval required) |
| --- | --- | --- |
| `permitrootlogin` is not `no` | cloud-init `disable_root: false` keeps root key login | Disable root SSH (2.1) or record an accepted exception |
| SSH allowed from `Anywhere` | The supplied OpenSSH UFW rule has no source | Restrict to operator networks in UFW and/or the UpCloud firewall (2.1) |
| `/opt/apps` not owned by `deploy` | cloud-init creates directories as root by default; `check-host` and the setup steps need `deploy` to write there | Set ownership non-recursively (2.2) |
| `/opt/postgres-backups` not `10002:10002` `0700` | cloud-init creates directories as root by default | Set ownership/mode non-recursively (2.5) |
| `tool git is not installed` | Not in the supplied package list | Install Git (2.2) |
| cloud-init errors/recoverable errors | Provisioning did not finish cleanly | Inspect privately with `sudo cloud-init status --long`; decide before rollout |
| Pending reboot | Kernel/library updates waiting | Reboot in a quiet window before the first release (10.2) |
| sysctl/fail2ban values differ from 10/50 and 5/600/3600 | Reported settings not effective | Record; correct only if approved |

`manual` lines must be checked elsewhere: the fresh-session and refusal checks
above, and the UpCloud provider firewall for IPv4 and IPv6. UFW rules do not
make Docker-published ports private: Docker programs its own iptables chains.
Only the frontend may publish ports, and only TCP 80/443.

### 1.3 Record

Attach the sanitized `audit-host.txt` (or its relevant lines) to the F record
under *Verified (F)* with date, operator role and host identifier. Keep
reported settings and verified results in separate columns.

## 2. Remaining Setup On The Existing Host (F, Approved)

Each step is an authorized change. Record who approved it and the sanitized
result. Nothing here reprovisions the host.

### 2.1 SSH and firewall restrictions

If approved, disable root SSH and restrict SSH sources without losing access:

```bash
# Keep the existing session open. Drop-in files are read in lexical order;
# the first value of each option wins, so use a low number.
printf 'PermitRootLogin no\n' | sudo tee /etc/ssh/sshd_config.d/10-schatten-hardening.conf >/dev/null
sudo sshd -t && sudo sshd -T | grep -Ei '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication) '
sudo systemctl reload ssh.service   # Ubuntu 26.04 starts ssh.service from ssh.socket
# Verify from the workstation in a NEW session (1.1) before closing the old one.

# Restrict SSH in UFW: add the restricted rule first, then remove the open one.
sudo ufw allow from <operator-cidr> to any port 22 proto tcp comment 'schatten operators'
sudo ufw status numbered
sudo ufw delete allow OpenSSH             # removes the IPv4 and the IPv6 OpenSSH rule
```

If operators connect over IPv6, add their IPv6 rule before the delete, or
restrict SSH in the UpCloud firewall instead. Keep TCP 80 and 443 public:
port 80 serves ACME HTTP-01 and the HTTPS redirect. Rerun `audit-host` and
record the new effective state. The drop-in, `sshd -t`/`sshd -T` and UFW
sequence were tested in a disposable Ubuntu 26.04 container (root login then
reported disabled, SSH no longer open to `Anywhere`); the `systemctl reload`
and the real-host result were not, so validate each before continuing.

### 2.2 Operator directory, Git and read-only GitHub source access

`deploy` creates the Schatten paths under `/opt/apps` and `check-host` requires
`/opt/apps` to be writable by it; no container writes there. If `audit-host`
reported another owner, inspect it and change only the directory itself, never
its existing contents; `/opt/caddy` stays unchanged:

```bash
sudo ls -la /opt/apps                          # look; do not record names of unrelated files
sudo chown deploy:deploy /opt/apps             # not recursive
sudo chmod 0755 /opt/apps
```

If a Schatten path (`schatten`, `schatten-config`, `schatten-state`,
`schatten-releases`) already exists with another owner, stop and review it
instead of changing it.

```bash
command -v git || sudo apt-get install --yes git        # only if audit-host reported it missing
ssh-keygen -t ed25519 -N '' -C 'schatten-upcloud-readonly' -f ~/.ssh/schatten_github_ro
cat >> ~/.ssh/config <<'EOF'
Host github-schatten
  HostName github.com
  User git
  IdentityFile ~/.ssh/schatten_github_ro
  IdentitiesOnly yes
EOF
ssh-keyscan -t ed25519 github.com | ssh-keygen -lf -   # compare with GitHub's published fingerprint
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts
```

A GitHub repository admin adds `~/.ssh/schatten_github_ro.pub` as a **read-only
deploy key** (write access unchecked). Then:

```bash
git clone git@github-schatten:reflector-oy/schatten.git /opt/apps/schatten
```

Never use a personal token or an HTTPS remote with embedded credentials;
`audit-host` flags one.

### 2.3 Protected configuration

```bash
install -d -m 0700 /opt/apps/schatten-config
( umask 077 && touch /opt/apps/schatten-config/production.env )
stat -c %g /var/run/docker.sock          # value for DOCKER_SOCKET_GID
openssl rand -hex 32                     # a URL-safe POSTGRES_PASSWORD; type it into the editor, never echo it into a file
${EDITOR:-nano} /opt/apps/schatten-config/production.env
```

The file contains exactly the keys of the
[configuration contract](DEPLOYMENT.md#required-configuration-contract),
without `BACKEND_IMAGE`/`FRONTEND_IMAGE`:

```text
POSTGRES_DB=schatten
POSTGRES_USER=schatten
POSTGRES_PASSWORD=<generated>
DATABASE_URL=postgresql://schatten:<same password>@database:5432/schatten
OIDC_DISCOVERY_URL=https://login.microsoftonline.com/<tenant-id>/v2.0/.well-known/openid-configuration
OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
OIDC_CLIENT_ID=<shared client ID>
OIDC_CLIENT_SECRET=<production-only secret>
PUBLIC_ORIGIN=https://schatten.lupaus.eu
DOCKER_SOCKET_GID=<stat output>
SCHATTEN_BACKUP_PUBLIC_KEY=/opt/apps/schatten-config/backup-public-key.asc
```

Leave `SCHATTEN_OFELIA_CONFIG`, `SCHATTEN_DOCKER_SOCKET` and
`SCHATTEN_COMPOSE_OVERRIDE_FILE` unset: they exist for disposable QA only.

### 2.4 Backup encryption key pair (offline)

Generate the pair on a trusted operator workstation, not on the host, in a
throwaway keyring:

```bash
export GNUPGHOME="$(mktemp -d)"; umask 077
gpg --quick-generate-key 'Schatten production backup' default default never   # prompts for a strong passphrase
fpr="$(gpg --batch --with-colons --list-secret-keys | awk -F: '/^fpr:/ { print $10; exit }')"
gpg --batch --armor --export "${fpr}" > backup-public-key.asc
gpg --armor --export-secret-keys "${fpr}" > backup-private-key.asc              # prompts for the passphrase
printf 'fingerprint %s\n' "${fpr}"                                              # record this; it is not secret
```

Store `backup-private-key.asc` and its passphrase **separately** from each
other and from the host (for example two protected operator vault entries),
and record which roles can reach them for recovery. Losing either makes every
backup unrecoverable. Remove the throwaway `GNUPGHOME` afterwards. Copy only
the public key to the host:

```bash
scp backup-public-key.asc deploy@<host>:/opt/apps/schatten-config/
ssh deploy@<host> chmod 0644 /opt/apps/schatten-config/backup-public-key.asc
```

The backup runner refuses a key file containing secret key material.

### 2.5 Backup directory

Reuse the cloud-init `/opt/postgres-backups`; inspect before changing it and
change only the directory itself, never its existing contents:

```bash
sudo ls -la /opt/postgres-backups              # look; do not record names of unrelated files
sudo chown 10002:10002 /opt/postgres-backups   # not recursive
sudo chmod 0700 /opt/postgres-backups
```

Backup retention only ever removes files matching the job's own
`schatten-<timestamp>-<reason>-<hex>.{dump.gpg,manifest}` names. `/opt/caddy`
is not mounted or modified; Caddy state lives in the `schatten_caddy_data`
volume.

### 2.6 DNS and TLS

Point `schatten.lupaus.eu` at the host with an `A` record and verify:

```bash
dig +short A schatten.lupaus.eu
dig +short AAAA schatten.lupaus.eu
```

Recommendation: publish **no `AAAA` record initially**. Docker reaches
published ports over IPv6 through its userland proxy, so IPv6 clients would
appear to FastAPI as the Docker gateway, weakening per-client rate limiting and
audit addresses (see the known limitations in DEPLOYMENT.md). Adding IPv6 later
is a recorded decision after checking the effective client address.

Caddy obtains the Let's Encrypt certificate on first start over HTTP-01
(port 80) or TLS-ALPN-01 (port 443). Nothing waits on issuance. Do not delete or
recreate `schatten_caddy_data`: it holds the certificate and ACME account, and
repeated issuance hits CA rate limits.

### 2.7 Entra (shared registration, tenant administrator)

| Setting | Production value |
| --- | --- |
| Web redirect URI | `https://schatten.lupaus.eu/api/v1/auth/callback` |
| Post-logout return | `https://schatten.lupaus.eu/login` |
| Development entries kept | `https://app.localhost/api/v1/auth/callback`, `https://app.localhost/login` |
| Issuer | `https://login.microsoftonline.com/<tenant-id>/v2.0` (exact) |
| Scopes | `openid profile email` only; no Graph calls; `email_verified` not required |
| Secret | New **production-only** client secret; record owner and expiry date, never the value |

Both environments authenticate the same app identity: consent, permissions,
enterprise-app assignments and callbacks are shared. Confirm the designated
production users are assigned. Remove the obsolete Authentik callbacks and the
Graph `User.Read` grant only after confirming no remaining consumer needs them.
No Authentik, Traefik, Coolify, forward-auth or `auth.lupaus.eu` is required.

To rotate the production secret: add the new secret in Entra, replace
`OIDC_CLIENT_SECRET` in `production.env`, redeploy the **current** release
(`$B/deploy-release <current-id> --approval <ref>`; Compose recreates only
containers whose configuration changed), verify login, then delete the old
secret in Entra.

### 2.8 Operator state and prerequisites

```bash
/opt/apps/schatten/deploy/bin/init-state     # creates missing state/lock files only
/opt/apps/schatten/deploy/bin/check-host     # must print PASSED host prerequisites
```

`check-host` rejects a non-Ubuntu-26.04 OS, old Docker/Compose, missing
Buildx/Git, a group-readable env file, image references in the env file, a
socket not mode `660` or with the wrong group, a Docker TCP listener, missing
lock files, wrong backup-directory ownership/mode and a public key inside the
backup directory.

## 3. Build And Freeze A Release

Before approval, for the exact commit to release:

1. Confirm CI passed for that commit on `main` and record the run URL. Local
   checks for the changed scope, simulated OIDC and the disposable runtime
   harness are part of that CI run.
2. Confirm real local direct-Entra browser evidence exists for the release
   scope (see the [authentication checklist](qa/AUTHENTICATION-QA-CHECKLIST.md));
   it does not prove production DNS, TLS or secrets.
3. Build on the host from the reviewed checkout:

   ```bash
   cd /opt/apps/schatten
   git fetch origin
   git merge-base --is-ancestor <sha> origin/main     # the commit must be on main
   git checkout --detach <sha>                        # tooling matches the commit
   deploy/bin/build-release <sha>                     # prints release.env
   ```

   `build-release` uses `git archive`, so untracked or modified files cannot
   enter the images. Record the printed `RELEASE_ID`, `SOURCE_COMMIT`, both
   image IDs, tool versions, `BUILD_DURATION_SECONDS` and
   `BUILD_MEMORY_AVAILABLE_BEFORE_BYTES`. `release.env` contains no secrets.
4. Watch the running application during the build (`free -m`,
   `docker stats --no-stream`). Reassess off-server builds after an OOM kill
   or failed build, sustained swap/CPU/memory contention with the running
   services, or a build duration the operator finds unacceptable. A later
   GitHub Actions/GHCR pipeline must deliver the same two images and release
   record; none is implemented.
5. Freeze: after approval nothing is rebuilt. `deploy-release` refuses tags
   that no longer resolve to the recorded image IDs and never pulls or builds
   application images.
6. Record the approval reference: a short non-personal identifier such as a
   PR number or change ID, passed as `--approval`.

## 4. First Installation (Fresh Database Only)

Use only when the database volume has never been initialized. `deploy-release
--first-install` refuses a database with migration history; do not work
around that. Existing-database adoption is out of scope.

```bash
R=<release-id>; B=/opt/apps/schatten-releases/$R/source/deploy/bin
```

| Step | Command | Expected result; stop otherwise |
| --- | --- | --- |
| 1 | `$B/check-host` | `PASSED host prerequisites` |
| 2 | `$B/deploy-release $R --approval <ref> --first-install` | Pre-migration baseline `BACKUP_ID` recorded as `PRE_CHANGE_BACKUP_ID`; all migrations exit 0; API, one worker and frontend healthy; `STATUS=succeeded`; `current` set; no `previous` |
| 3 | `$B/verify-runtime-hardening` | `PASSED runtime hardening`; `deploy-release` already required this, rerun it to capture the output for the record (Ofelia is checked on activation in step 11) |
| 4 | `$B/initialize status` | `users_including_deleted=0`, `active_default_metamodels=0`, `organisations=0`: nothing was seeded at startup |
| 5 | `$B/initialize reference-seed` then `$B/initialize status` | `active_default_metamodels=1`, non-zero `node_types`/`edge_types`/`type_attributes`/`allowed_connections`, still `users_including_deleted=0` |
| 6 | `$B/initialize bootstrap-admin` in a private terminal | Prompts for the designated display name and Entra email; prints `Administrator bootstrap completed.` |
| 7 | `$B/initialize status` | `users_including_deleted=1`, `active_admins=1`, `user_identities=0`, `auth_sessions=0` |
| 8 | `$B/backup-now --reason manual` | `BACKUP_ID=` of the initialized database |
| 9 | Restore rehearsal of that ID (section 8.3) | `STATUS=success`; evidence shows `rows table=users count=1` and `rows table=metamodels count=1` |
| 10 | `$B/ops-status` | Both backups listed; latest restore evidence `STATUS=success` |
| 11 | `$B/deploy-release $R --approval <ref> --enable-scheduler` | Scheduler activation (section 9): hardening passes including Ofelia; `SCHEDULER=active` in the record |
| 12 | First direct-Entra login by the designated admin | Guarded first link; then provision the designated consultant through the normal Users administration |
| 13 | Narrow production smoke (section 7) | All items pass |
| 14 | Next day: `$B/ops-status` | A `-scheduled-` backup is listed and Ofelia logged `failed: false` |

Step 6 details: run it in a private terminal with screen sharing and session
recording off. It accepts no arguments; the name and email are typed only at
the prompts and never appear in arguments, logs or records. The terminal echo
is the only place the input appears. It creates one fixed-role active `admin`
only when the whole `users` table, including soft-deleted rows, is empty, with
null audit actors and no identity or session. If it prints `refused: the users
table is not empty`, stop: do not delete rows, do not insert manually, and do
not rerun `--first-install`; escalate. `bootstrap-admin` also refuses a
non-interactive session. The reference seed is idempotent: a repeat reports
`Reference data seed skipped: an active default already exists.` and changes
nothing.

Step 11 reruns the same frozen release: it passes the restore-evidence gate
with step 9's evidence, takes a `pre-release` backup, runs the (no-op)
migration job, starts Ofelia and verifies runtime hardening including Ofelia.
If verification fails, it stops Ofelia and the release is not accepted.

The pre-migration baseline in step 2 is a backup of the still-empty database.
It proves the backup path before any change but is not a rehearsal of
initialized data; step 9 is. Release acceptance requires
both backup identifiers, step 9's successful evidence and step 11's active
scheduler.

## 5. Subsequent Releases

```bash
R2=<new-release-id>; B2=/opt/apps/schatten-releases/$R2/source/deploy/bin
```

1. Build and freeze `R2` (section 3). Review its migrations for
   expand/contract compatibility and record whether the current release could
   run against the new schema (this decides the rollback option).
2. Rehearse the newest completed backup (section 8.3) so the evidence is
   current. The gate needs the **latest** evidence file to be `STATUS=success`;
   a failed or missing rehearsal blocks the release until a successful one exists.
3. `$B2/check-host`, then `$B2/deploy-release $R2 --approval <ref>`. It takes
   the pre-change backup, runs migrations, replaces API/worker/frontend,
   recreates runners and updates Ofelia if it is running.
4. Run the narrow smoke (section 7) and complete the release record
   (section 11).

Repeated releases never run `bootstrap-admin` or `--first-install`. Running
`initialize reference-seed` again is safe but not part of a normal release.

## 6. Failure Handling And Application Rollback

- **Migration failure:** the migration job exits nonzero before any new
  API/worker/frontend container is created; the previous containers keep
  serving and the record shows `SERVICES_REPLACED=false`. Read the sanitized
  migration log (`docker logs` of the migration container), fix the reviewed
  cause, build a new release and retry forward.
- **Failure after migration** (health, worker count, hardening): the new
  release may be partly running (`SERVICES_REPLACED=true`, "may be partly
  running"). Fix forward with the same or a corrected release, or roll back.
- **Application or smoke failure:** stop new prediction submissions, inspect
  safe request summaries and keep one worker. Queued requests are durable;
  interrupted running requests become failed without automatic retry and need
  manual resubmission. Record request identifiers only.

Rollback to an older frozen release is allowed only when its images are
compatible with every applied migration:

```bash
B_old=/opt/apps/schatten-releases/<older-release-id>/source/deploy/bin   # the target release's own tooling
$B_old/deploy-release <older-release-id> --approval <ref> --rollback --confirm-schema-compatible
```

`--confirm-schema-compatible` records the human expand/contract review. The
command still verifies inside the older image that its migrations are an exact
prefix (version, filename, checksum) of the applied history, takes a
pre-change backup, replaces API and worker together, then the frontend, and
never runs the migration job. It never runs down migrations, deletes volumes,
resets or restores the database, and it cannot recover lost data.

**First release:** there is no previous stable release and no rollback target.
On failure stop, keep the database, and escalate for an approved forward fix.
If no compatible older release exists later, the same applies.

Database restoration to production is not part of this runbook. It needs its
own explicit authorization and impact review and is never triggered by a
failed deployment or smoke test.

## 7. Narrow Production Smoke

After every approved deployment, with designated pre-provisioned accounts and
isolated test records only:

1. `curl -sS https://schatten.lupaus.eu/health` returns `OK`; the certificate
   is publicly trusted
   (`echo | openssl s_client -connect schatten.lupaus.eu:443 -servername schatten.lupaus.eu 2>/dev/null | openssl x509 -noout -issuer -enddate`).
2. Designated admin: login, clean callback to a URL without provider query
   data, session restored on reload, Users administration visible, logout
   returns to `/login` and the session endpoint then returns `401`.
3. Designated consultant: login, no Users administration (database role
   enforcement, not Entra claims), logout.
4. First rollout or any authentication/provider change: a designated account
   with no matching Schatten User fails generically; no User, identity or
   session is created (confirm with `initialize status` counts).
5. One prediction flow on an isolated test record: submit, observe queued ->
   calculating -> completed with exactly one worker.

Prohibited in production: broad automated suites, destructive tests, load or
rate-limit tests, Host/proxy spoofing, secret injection, migration-failure or
rollback experiments and waiting out session lifetimes. Record tester role,
time, commit, image IDs and pass/fail, without identities or credentials.

## 8. Backups, Keys And Restore Rehearsal

### 8.1 What runs

| Item | Behavior |
| --- | --- |
| Daily backup | Ofelia job `postgres-backup`, 02:30 `Europe/Helsinki`, runner `schatten-backup-runner` |
| On demand | `$B/backup-now [--reason pre-release\|manual]`; every release takes a `pre-release` backup automatically |
| Format | `pg_dump --format=custom` streamed into `gpg --encrypt` for the public key; plaintext never touches disk |
| Files | `/opt/postgres-backups/schatten-<UTC>-<reason>-<hex>.dump.gpg` + `.manifest`, mode `0600`, owner `10002` |
| Completion | The manifest is published last; only manifested backups count |
| Retention | After a successful backup, job-owned pairs older than 7 days are removed; the newest is always kept; unrelated files are never touched |
| Non-overlap | Backup and maintenance locks exclude overlapping backups and the weekly cleanup |

A completed run prints one `status=completed ... backup_id=... sha256=...
retention=... free_bytes=...` line and `backup-now` then prints
`BACKUP_ID=<id>`. Missing key, missing/wrong credentials, an unwritable
directory, a full disk or an encryption error exit nonzero with
`status=failed` and publish nothing. Exit code `2` means the backup completed
but retention pruning failed. There is no automatic retry: after a failed
scheduled run, fix the cause and run `backup-now`.

These backups share the host and disk with the database. Host or disk loss can
destroy both; this is accepted until off-server protection is planned
separately. Backup size, the encrypted copy and rehearsal targets all use the
same disk, so watch the `free_bytes` value and `check-host` disk report.

### 8.2 Status

```bash
$B/ops-status     # pointers, newest completed backups, latest restore evidence, scheduler results
```

### 8.3 Restore rehearsal

Bring the private key and passphrase to the host only for the rehearsal, into
the operator's private runtime directory (tmpfs), and remove them afterwards:

```bash
install -d -m 0700 "/run/user/$(id -u)/schatten-restore"
# From the workstation, from the two separate vault entries; the passphrase
# file contains only the passphrase on its first line:
scp backup-private-key.asc backup-key-passphrase deploy@<host>:/run/user/<uid>/schatten-restore/
# On the host:
$B/restore-rehearsal <backup-id> \
  --private-key "/run/user/$(id -u)/schatten-restore/backup-private-key.asc" \
  --passphrase-file "/run/user/$(id -u)/schatten-restore/backup-key-passphrase"
rm -rf "/run/user/$(id -u)/schatten-restore"
```

The rehearsal verifies the manifest checksum, starts a disposable PostgreSQL 18
on a new internal network with no ports, streams the key material on stdin
into a hardened runner, restores with `pg_restore --exit-on-error
--single-transaction` and checks migration version/contiguity, table count,
validated constraints and per-table row counts. The target and its volume are
always removed. It prints `RESTORE_EVIDENCE=<file>`; the file under
`/opt/apps/schatten-state/restore-evidence/` holds identifiers, check results
and counts only. A wrong passphrase or key yields `STATUS=failed` evidence,
which blocks the next release until a successful rehearsal follows.

`deploy` can read the key while it is on the host; its privileges already
equal host administration, so the exposure is limited by removing the files
promptly and never storing them there.

### 8.4 Key rotation and recovery access

To rotate, generate a new pair (2.4), replace the public key file, and keep the
old private key and passphrase until no backup encrypted with it remains in
`/opt/postgres-backups` (normally 7 days after rotation; retention always keeps
the newest backup) **and** a rehearsal of a backup made with the new key has
succeeded.
Each manifest records the key fingerprint it was encrypted for. Record the
recovery custodians (roles) for the private key and passphrase in the F
record.

## 9. Scheduler Activation And The Docker Control Boundary

**Docker API access is host-administrator-equivalent.** Ofelia and the
cleanup runner hold the local Docker socket; a `:ro` bind mount would not make
API calls read-only, and container hardening cannot contain a compromised API
client, which could reach every container and its secrets despite the
separated mounts. Only authorized host operators may change the job file or
the pinned images, and only through a reviewed release.

Activate with `deploy-release ... --enable-scheduler` (4 step 11). Before
recording activation, confirm from `verify-runtime-hardening` output and the
record:

- Ofelia, backup-runner and cleanup-runner images are digest-pinned; API,
  migration, worker and frontend run the frozen image IDs.
- No container except the frontend publishes ports; the frontend publishes only
  80/tcp and 443/tcp. Ofelia and the cleanup runner have `network_mode: none`;
  the backup runner, migration, worker and database join only the internal
  `schatten_data` network.
- Every container: non-root user, read-only root filesystem, all capabilities
  dropped, `no-new-privileges`, not privileged, no host PID/IPC/UTS/network/user
  namespace, no devices, no supplementary groups.
- The socket is mounted only into Ofelia and the cleanup runner; socket mode
  stays `660` and there is no TCP listener (`check-host`, `audit-host`).
- Ofelia runs without `--docker` (no label discovery) and its job file is
  mounted read-only, with each job only starting a pre-created runner
  (`container =`), no image/command/volume/network/user keys.
- Only the backup runner has writable bind mounts (`/backups`) and receives
  the database credential; Ofelia and the cleanup runner receive no secrets; no
  operational container mounts host root, PostgreSQL data or Caddy storage.

To spot-check Ofelia's effective settings without printing environments:

```bash
docker inspect --format 'image={{.Config.Image}} user={{.Config.User}} network={{.HostConfig.NetworkMode}} ro={{.HostConfig.ReadonlyRootfs}} capdrop={{.HostConfig.CapDrop}} secopt={{.HostConfig.SecurityOpt}} cmd={{.Config.Cmd}}' \
  "$(docker ps --quiet --filter label=com.docker.compose.project=schatten --filter label=com.docker.compose.service=ofelia)"
```

Any failed control blocks activation: leave the scheduler stopped and escalate
for a reviewed amendment; never widen socket permissions or add privileges.

Diagnosis:

- `docker logs --since 48h <ofelia container>` shows each run with
  `failed: true|false` and the runner's output (`ops-status` summarizes it).
- `permission denied` on the socket means `DOCKER_SOCKET_GID` no longer
  matches the socket group; correct the env value and redeploy the current
  release; do not change socket permissions.
- A backup exiting `1` means a job failure (see 8.1); exit `2` means retention
  failed after a completed backup.

### 9.1 Weekly Docker cleanup

Ofelia runs `docker-cleanup` on Sundays at 04:30 `Europe/Helsinki`. It needs
the maintenance lock exclusively and exits `75` (`status=skipped`) while a
build, release, rollback, backup or restore holds it. With a 7-day window it
removes only exited/dead containers without the
`eu.lupaus.schatten.retain=true` label, dangling images, `schatten-backend`/
`schatten-frontend` images not referenced by any non-retired release record or
container, and BuildKit cache older than 7 days. It never touches volumes,
networks, running containers, backups or other repositories' tagged images and
never runs `docker system prune`.

```bash
$B/docker-cleanup --dry-run      # lists candidates, removes nothing
$B/retire-release <old-id>       # makes an old, non-current, non-previous release eligible
```

Any failed listing, removal or cache prune exits `1` with `status=failed`.
Docker cleanup is not a backup mechanism and is separate from the 7-day
backup retention.

## 10. Operations: Health, Restart, Reboot, Certificates

### 10.1 Health and diagnosis

```bash
docker ps --all --filter label=com.docker.compose.project=schatten --format 'table {{.Names}}\t{{.Status}}'
curl -sS https://schatten.lupaus.eu/health
docker logs --since 30m <container> 2>&1 | tail -n 50
```

Health checks: database `pg_isready`; API `/health`; worker its lock-owning
health command; Caddy a loopback `127.0.0.1:8081/health` that does not depend
on certificates. Logs redact callback query values and credential headers, but
summarize rather than paste auth logs. Use `docker inspect --format` for
specific fields; plain `docker inspect` of application, database or backup
containers prints their secret environment.

### 10.2 Restart and reboot

Services use `restart: unless-stopped`. On reboot Docker restarts database, API,
worker and frontend from their existing containers; the completed migration
job and the runners are not rerun. Until PostgreSQL is healthy, database-backed
API requests fail and the worker restarts. The API exits if Entra discovery is
unreachable at startup and is retried; the frontend waits for a healthy API.

For a planned reboot (including a pending unattended-upgrades reboot), choose a
window outside 02:30 and Sunday 04:30 and reboot while holding the shared
maintenance lock, so no build, release, backup or restore can start between the
check and the reboot:

```bash
sudo flock --exclusive --nonblock /opt/apps/schatten-state/locks/maintenance.lock systemctl reboot \
  || echo 'busy: a build, release, backup or restore holds the maintenance lock; retry later'
```

The lock is held until the reboot has been started; if it is busy, nothing
happens. Afterwards confirm healthy containers, `/health` and `ops-status`.
Record the effective unattended-upgrades automatic-reboot setting from
`audit-host`; an automatic reboot at an unplanned time follows the same
recovery path.

### 10.3 Persistence

`schatten_postgres_data` and `schatten_caddy_data` survive container
replacement and reboots; they are **not backups**. Never delete, prune or
recreate them. Certificates renew automatically; check the expiry with the
`openssl` command in section 7.

## 11. Release Record

Record per deployment (first install, release or rollback), without secrets,
identities or restored data:

| Field | Source |
| --- | --- |
| Release ID, approved commit, CI run URL | `release.env`, CI |
| Backend and frontend image IDs | `release.env` |
| Tool versions, build duration and available memory | `release.env` |
| Local/CI evidence and real local Entra evidence reference | CI, authentication checklist |
| Approval reference | `--approval` value |
| Mode, previous release or explicit first-release absence | Deployment record `MODE`, `PREVIOUS_RELEASE` |
| Pre-change backup ID | Deployment record `PRE_CHANGE_BACKUP_ID` |
| Latest successful restore evidence: file, time, backup ID, result | Deployment record `RESTORE_EVIDENCE`; evidence file |
| Migration exit code, services replaced, scheduler state, result | Deployment record |
| First install: initialization status counts, initialized backup ID and its restore evidence | Section 4 |
| Tester role, time, smoke results | Section 7 |
| Prior stable annotated SemVer tag and its image IDs, or "none (first release)" | Release history |

Deployment records live in `/opt/apps/schatten-state/deployments/`. Stable tags
are created only after acceptance by a human.

## 12. Future Managed PostgreSQL (Planning Entry)

Moving to UpCloud Managed PostgreSQL is deferred and needs its own reviewed
plan covering at least:

- data transfer from the Docker volume (dump/restore or logical replication),
  verification, write freeze and cutover window;
- connection and TLS (`sslmode=verify-full`, CA provisioning in
  `DATABASE_URL`), and **session-level advisory locks** for the single worker,
  which require direct or session-mode pooling, never transaction pooling;
- cutover and rollback, including keeping the Docker database untouched until
  acceptance;
- backup placement and continuity of encryption, 7-day retention, identifiers
  and restore rehearsal, with an evaluation of off-server protection;
- replacing or retiring the Ofelia backup job only after the replacement's
  scheduling and recovery evidence is verified.

Only the managed migration is deferred; the initial on-server backups and their
evidence gates are required now.

## 13. Command Verification Status

What TASK-059E exercised on disposable infrastructure
([QA record](qa/UPCLOUD-RUNBOOK-QA.md)); everything else is F verification.

| Section | Tested (E) | Not testable before F |
| --- | --- | --- |
| 1 Host audit | `audit-host` in a disposable Ubuntu 26.04 baseline container, directly and through `bash -s` | Real host results, fresh SSH sessions, provider firewall |
| 2.1 SSH/UFW | Drop-in, `sshd -t`/`sshd -T`, UFW restrict-then-delete in that container | `systemctl reload ssh`, lockout safety on the real host |
| 2.2 Directory, source access | `/opt/apps` ownership change and `deploy`-created Schatten paths in the 26.04 container, confirmed by `audit-host` | Deploy key, GitHub fingerprint, clone |
| 2.3 Configuration | Configuration contract and privacy checks (`check-host`) with synthetic values | Real secrets |
| 2.4 Backup keys | Key generation/export commands with gpg 2.4.8 on Ubuntu 26.04; passphrase-protected key used for all harness restores | Vault storage and custodians |
| 2.5-2.6 Storage, DNS | Backup directory ownership/mode checks | DNS, public certificate issuance |
| 2.7 Entra | Simulated discovery only | Callbacks, secret, assignments, cleanup |
| 2.8, 3-6 | `init-state`, `check-host`, `build-release`, first install, initialization, releases, gates, rollback on Engine 28.5.2 and 29.8.1 daemons | The real host and its resources |
| 7 Smoke | Local simulated-OIDC suites | Production smoke |
| 8-10 | Backups, failures, retention, passphrase restore, scheduler, cleanup, persistence, daemon restart; the reboot lock refusing while a holder exists (with `echo` in place of `systemctl reboot`) | Real schedule runs, real reboot, certificate renewal |

