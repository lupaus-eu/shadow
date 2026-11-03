# Production Runbook: UpCloud Docker Host

This is the integrated operator runbook for Schatten on the existing UpCloud
**Ubuntu 26.04 LTS** host: Docker Engine/Compose, direct Caddy TLS for
`https://schatten.lupaus.eu`, private PostgreSQL 18 in Docker, direct Entra
OIDC, daily encrypted on-server backups with 7-day retention and the hardened
Ofelia scheduler. It integrates TASK-059B/C/D/G and the Git-free source
delivery of TASK-059H1-H3 under
[ADR-013](decisions/ADR-013-shared-entra-local-https-deployment.md). The
architecture, configuration contract and tooling reference live in
[DEPLOYMENT.md](DEPLOYMENT.md). The disposable verification behind the
commands below is recorded in
[UPCLOUD-RUNBOOK-QA.md](qa/UPCLOUD-RUNBOOK-QA.md) (E) and
[SOURCE-DELIVERY-QA.md](qa/SOURCE-DELIVERY-QA.md) (H1-H3). Real host and
provider evidence goes into the F record,
[FIRST-PRODUCTION-ROLLOUT.md](qa/FIRST-PRODUCTION-ROLLOUT.md). Section 14 covers
AI via MCP ([ADR-015](decisions/ADR-015-ai-via-mcp.md)), which stays disabled
until its separately approved enablement.

**This runbook authorizes nothing.** Every host, DNS, firewall, GitHub, Entra,
backup-activation and production step is TASK-059F work and needs explicit
operational approval first. Until F records it, every live fact below is
*reported* or *pending*, never *verified*.

Source reaches the host only through the manually started "Deploy to
production" GitHub Action and a manifest-verified receive
([ADR-013 source-delivery amendment](decisions/ADR-013-shared-entra-local-https-deployment.md#source-delivery-without-git-on-the-server)).
There is **no Git, deploy key or checkout on the server**. UFW keeps TCP 22
open for GitHub-hosted runners and operators on changing networks; SSH is
limited by `AllowUsers deploy root schatten-upload`, key-only root login and
public-key-only settings
([ADR-013 TASK-059J](decisions/ADR-013-shared-entra-local-https-deployment.md#operator-ssh-access-from-any-address)). The order is: tool bootstrap (2.2) -> Action -> run check -> digest
-> receive -> build -> deploy (sections 3-5).

## 0. Ground Rules

Evidence labels used in this runbook and the F record:

| Label | Meaning |
| --- | --- |
| Reported | Operator-supplied information (the cloud-init baseline, a role's own statement); not evidence |
| Tested (E, H1-H3, J) | Exercised against disposable local infrastructure; see the QA records |
| Verified (F) | Observed on the real host/provider under approval and recorded by F |
| Recorded | A decision or acknowledgement by the named role; nothing to observe |
| Not performed | Not done: an optional check, or a required one whose gap is in the record's [failure log](qa/FIRST-PRODUCTION-ROLLOUT.md#10-failure-and-deviation-log) |
| Accepted deviation | Not performed or not as this runbook requires; the gap and who accepted it are in the record's [failure log](qa/FIRST-PRODUCTION-ROLLOUT.md#10-failure-and-deviation-log) |
| Pending | Not yet performed; never mark it complete without doing it |

Always:

- Run tooling from the **verified source copy** of the release you act on,
  which `schatten-receive` prints as `SOURCE_DIR=`:

  ```bash
  S=/opt/apps/schatten-sources/<commit>   # read-only, manifest-verified
  M="make -C $S/deploy"                   # $M help lists the targets below
  B=$S/deploy/bin                         # direct commands that make does not offer
  ```

  Each frozen release keeps an identical, re-verified copy in
  `/opt/apps/schatten-releases/<release-id>/source`; a rollback runs the
  target release's copy (section 6). The only command outside these copies is
  the installed `/usr/local/bin/schatten-receive`, always run directly.
- Record sanitized outcomes only: identifiers, counts, statuses, versions and
  times. Keep a working SSH session open while changing SSH or firewall rules.
- Stop at the first failed gate. Commands leave release pointers unchanged on
  failure and print the next safe action.

`deploy/Makefile` targets are thin wrappers; every gate stays in the command
they run. A missing required variable stops with a usage message (exit 2),
values are passed through the environment and never evaluated by a shell, and
`deploy`/`first-install` refuse a release that was not built from the copy
they run from (the release ID ends with the first 12 characters of its commit).

| Target | Runs |
| --- | --- |
| `$M check` | `check-host` |
| `$M audit` | `audit-host` |
| `$M build` | `build-release --source $S` |
| `$M deploy RELEASE=<id> APPROVAL=<ref> [MCP_APPROVAL=<ref>]` | `deploy-release <id> --approval <ref> [--mcp-approval <ref>]`; `MCP_APPROVAL` is required when the deploy turns MCP on (section 14) |
| `$M first-install RELEASE=<id> APPROVAL=<ref>` | `deploy-release <id> --approval <ref> --first-install` |
| `$M status` | `ops-status` |
| `$M ps`, `$M logs [SERVICE=<service>]`, `$M stop`, `$M start` | `service ps\|logs\|stop\|start` for the current release (section 10) |
| `$M backup` | `backup-now --reason manual` |
| `$M restore BACKUP=<id> KEY=<file> [PASSPHRASE=<file>]` | `restore-rehearsal`, into a disposable database only (8.3); `KEY` and `PASSPHRASE` must be absolute paths because `make -C` runs in the deploy folder |
| `$M cleanup-dry-run` | `docker-cleanup --dry-run` |

No target runs `docker compose down -v`, prunes, deletes volumes, runs down
migrations, restores production, seeds or bootstraps. These stay direct `$B`
commands with their own gates: `init-state`, `initialize`,
`verify-runtime-hardening`, `deploy-release ... --enable-scheduler`,
`deploy-release ... --rollback`, `retire-release` and `docker-cleanup --apply`.

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
  approval. Turning on `MCP_ENABLED` or `MCP_CHANGE_SET_REVIEW_ENABLED` needs its
  own recorded approval, which `deploy-release` requires as `--mcp-approval`
  (section 14).
- Execute, source or `make` anything inside `/opt/apps/schatten-upload`: the
  upload is data for `schatten-receive` only. Install Git, a deploy key or a
  checkout on the host.

`deploy` is a **privileged operator**: passwordless sudo plus membership of the
`docker` group, which is itself host-administrator-equivalent. It is not an
application identity; no application container runs as it. Every command in
this runbook runs as `deploy`. Key-only root SSH exists only for the product
owner's direct login; it is not used for runbook commands.

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

Repeat the refusal check for `root` and the image's default user. A root key
login is optional and only possible for the root key holder (the product
owner); it is not required evidence. Record only "accepted/refused" per
account, not key material.

### 1.2 Sanitized host audit

`deploy/bin/audit-host` inspects the effective state with `sudo -n` read-only
commands and prints counts and settings only. Before the first receive there
is no verified copy on the host, so run the version of the approved `main`
commit from an operator workstation (Git is allowed there, never on the host):

```bash
git fetch origin && git merge-base --is-ancestor <approved-commit> origin/main
git show <approved-commit>:deploy/bin/audit-host | ssh deploy@<host> bash -s > audit-host.txt
```

After the first receive, run `$M audit > audit-host.txt` on the host instead.

It reports `ok`, `attention`, `manual` and `missing` lines and a final
`SUMMARY attention=N missing=M`. It exits 0: attention items are decisions for
F, not script failures. It covers:

| Area | Checked |
| --- | --- |
| OS/tools | Ubuntu 26.04, kernel, uutils coreutils and sudo-rs versions, `python3`, `curl`, `gpg`, `openssl`, `flock`, `ss`, `make`; Git presence is only a fact |
| cloud-init | `cloud-init status --format json`: status, error and recoverable-error **counts** only |
| Accounts | Human accounts and root: password status (`L` locked), authorized-key **counts**, root keys with cloud-init's `disable_root` prefix (count), `sudo`/`docker`/`adm` membership; `docker` group members; passwordless sudo for `deploy` |
| SSH | `sshd -T` effective `permitrootlogin` (must be `prohibit-password`; `no` is stricter) and a different value in the main `sshd_config`, password/keyboard-interactive/pubkey settings, `authenticationmethods`, `allowusers`/`allowgroups`, ports; `AllowUsers` must admit `deploy`, `root` and `schatten-upload` and nothing else (`@<cidr>` patterns are a stricter fact); `Match` blocks; `ssh.socket`/`ssh.service` state |
| Firewall | `ufw status verbose` rules; SSH allowed from `Anywhere` is a fact when root, password and keyboard-interactive login are off, otherwise attention |
| Listeners | Non-loopback TCP listeners other than 22/80/443; any 2375/2376 Docker API listener |
| Docker | Engine/containerd/Compose/Buildx versions, storage/cgroup/security options, socket mode/group, `daemon.json` keys, containers publishing ports other than 80/443 |
| Resources | Swap devices, fstab swap entries, `vm.swappiness`/`vm.vfs_cache_pressure`, CPUs, memory, disk for `/`, `/var/lib/docker`, `/opt` |
| Time | Timezone `Europe/Helsinki`, NTP synchronization |
| fail2ban | `sshd` jail, current/total ban **counts** (no addresses), `maxretry`/`findtime`/`bantime` |
| Updates | unattended-upgrades units, APT periodic and automatic-reboot settings, pending reboot, held packages |
| Storage | Owner/mode/entry count/filesystem of `/opt/apps`, `/opt/caddy`, `/opt/postgres-backups` and the Schatten paths; `deploy` ownership of `/opt/apps` and existing Schatten paths; completed-manifest count |
| Upload | `schatten-upload`: locked password, only its own group, no sudo rules, `deploy` in its group, root-owned home/`.ssh`/`authorized_keys`, key **counts** and how many start with `restrict,command="/usr/local/bin/upload-gate"`, no `authorized_keys2`; `/opt/apps/schatten-upload` `schatten-upload:schatten-upload` `0750` |
| Source | `/usr/local/bin/upload-gate` and `schatten-receive`: root-owned, not group/other writable, SHA-256; newest received sources with their manifest digest; leftover staging |

Expected attention items on the reported baseline, and the F decision each
needs:

| Audit finding | Why | F action (approval required) |
| --- | --- | --- |
| `root SSH is not key-only` (`permitrootlogin=yes`) | The host's main `sshd_config` sets `PermitRootLogin yes`; cloud-init `disable_root: false` keeps root's key usable | Set `PermitRootLogin prohibit-password` (2.1); required before SSH may stay open to anywhere |
| `AllowUsers is not set` | The baseline has no `AllowUsers` | Set `AllowUsers deploy root schatten-upload` (2.1) |
| SSH allowed from `Anywhere` while password or keyboard-interactive login is enabled or root login is not key-only | The OpenSSH UFW rule has no source, which ADR-013 accepts only for public-key-only SSH | Harden SSH first (2.1). Afterwards SSH from Anywhere is reported as an accepted fact, not attention |
| `tool make is not installed` | Not in the supplied package list | Install `make` (2.2) |
| `/opt/apps` not owned by `deploy` | cloud-init creates directories as root by default; `check-host` and the setup steps need `deploy` to write there | Set ownership non-recursively (2.2) |
| `/opt/postgres-backups` not `10002:10002` `0700` | cloud-init creates directories as root by default | Set ownership/mode non-recursively (2.5) |
| Upload account, upload folder, `upload-gate`, `schatten-receive` absent (facts) | Not part of the baseline | Create and install them (2.2) |
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

### 2.1 Public-key-only SSH, `AllowUsers` and port 22

GitHub-hosted runners have no fixed addresses and operators connect from
changing networks, so TCP 22 stays reachable from anywhere and SSH itself is
restricted: only `deploy`, key-only root (the product owner's direct login)
and the upload-only `schatten-upload` may log in, with keys only. Keep the
existing session open throughout:

```bash
# Drop-in files are read in lexical order and the first value of each option
# wins, so use a low number. Ubuntu's sshd_config includes the drop-ins before
# its own settings, so this file also overrides a main-file PermitRootLogin yes.
sudo tee /etc/ssh/sshd_config.d/10-schatten-hardening.conf >/dev/null <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
AllowUsers deploy root schatten-upload
EOF
sudo sshd -t
sudo sshd -T | grep -Ei '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|allowusers) '
sudo sshd -T -C user=root,host=workstation,addr=203.0.113.9 | grep -Ei '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication) '
```

`sshd -t` must print nothing, and both `sshd -T` calls must show
`permitrootlogin prohibit-password` (older sshd prints its alias
`without-password`), `passwordauthentication no` and
`kbdinteractiveauthentication no`; the first must also show the three
`allowusers` lines `deploy`, `root` and `schatten-upload`. A
`deploy@<cidr>`/`root@<cidr>` pattern or `PermitRootLogin no` is an allowed,
stricter choice. Only then reload and verify in a **new** session from the
workstation before closing the old one:

```bash
sudo systemctl reload ssh.service   # Ubuntu 26.04 starts ssh.service from ssh.socket
# From the workstation: repeat 1.1. deploy must be accepted with its key from
# any network; password/keyboard-interactive logins as deploy and root and any
# login as the image's default user must be refused.
```

Root is verified without its key: the `sshd -T -C user=root,...` output above,
an unchanged root key count with no `disable_root` prefix in `audit-host`, and
a refused root password login. A root key login by the product owner is
optional and recorded only if it happens. If root SSH ever stops working, fix
it as `deploy` with `sudo`; no downtime is needed.

`AllowUsers` shuts out the image's default user and every other account over
SSH. If the new session fails, fix the drop-in from the old session.

Port 22: the reported baseline's UFW `OpenSSH` rule already allows 22 from
`Anywhere`; keep it and add no source restriction. Confirm it only after the
settings are shown by `sshd -T` and the new session worked, because a
missing setting blocks leaving 22 open:

```bash
sudo ufw status verbose            # 22/tcp (OpenSSH) ALLOW IN Anywhere (and v6); 80/443 public
sudo ufw allow OpenSSH             # only if a source-restricted rule replaced it earlier
```

In the UpCloud provider firewall, allow TCP 22 from anywhere for IPv4 (and
IPv6 only if SSH over IPv6 is intended) and TCP 80/443 publicly, nothing else.
The provider firewall is stateless: with only these rules it blocks the
replies to the host's own connections. Until this section is corrected, use
the rule set in the
[F record's 2.1 row](qa/FIRST-PRODUCTION-ROLLOUT.md#21-ssh-and-port-22-21) and
enable the firewall last.
Rerun `audit-host`: `root SSH is key-only`, password and keyboard-interactive
login `ok`, `AllowUsers admits deploy from any address`, `AllowUsers admits
root from any address`, `AllowUsers admits schatten-upload`, the main file's
`PermitRootLogin yes` reported as overridden, and SSH from `Anywhere` reported
as an accepted fact.

Operator keys: one key per person with a role comment, never a shared key, on
`deploy` and on root; keep private keys passphrase-protected and use them
through an agent. On a lost or suspected key, remove its line from the
affected `authorized_keys` (`/home/deploy/.ssh/` or `/root/.ssh/`) at once
from another working session. Record the key **counts** of both accounts and
the role holding each root key in the F record.

#### Recovery without SSH

All passwords stay locked, so the UpCloud web console has no login until a
password is set. Recovery access is held through the UpCloud account
(initially the product owner). In order of preference:

1. **Another working key** (`deploy` or root): fix the drop-in or
   `authorized_keys` from that session. No downtime.
2. **Locked out by `AllowUsers` or the drop-in:** during UpCloud's
   [disk-move procedure](https://upcloud.com/docs/guides/reset-root-password-cloud-server/)
   (below), while the disk is attached to the temporary server, correct the
   line in `etc/ssh/sshd_config.d/10-schatten-hardening.conf` on the mounted
   disk and validate it in a chroot on the temporary server:

   ```bash
   sudo mount --bind /dev <mount>/dev
   sudo chroot <mount> sh -c 'mkdir -p /run/sshd && sshd -t && sshd -T' \
     | grep -Ei '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|allowusers) '
   sudo umount <mount>/dev
   ```

   `sshd` needs `/dev/null` and the runtime directory `/run/sshd`, which are
   missing on a mounted disk (`/run/sshd` is recreated at boot anyway). A
   configuration error prints `Bad configuration option` and no settings. No
   password is needed.
   Alternative: set a password with the reset, log in on the UpCloud web
   console and correct the line there (it is short enough to type, since the
   console does not paste), validate with `sshd -t` and `sshd -T`, reload,
   and lock the password again.
3. **Lost the only working key:** during the disk-move procedure, while the
   disk is attached to the temporary server, add the new public key to
   `/home/deploy/.ssh/authorized_keys` or `/root/.ssh/authorized_keys` there,
   where pasting and `scp` work. No password is needed for this.

The disk-move reset: deploy a temporary server in the same zone, shut down the
production server, detach its system disk, attach it to the temporary server,
mount it and change it there (`chroot` for a password), reattach it and delete
the temporary resources. **It causes downtime**: the site and scheduled
backups stop. Take an UpCloud storage backup or snapshot of the disk first,
because the application backups live on the same disk. Afterwards lock any
password set during recovery (`sudo passwd -l <account>`), rerun `audit-host` and
record the recovery in the F record or release record.

**Never** follow the step of UpCloud's
[regaining-access guide](https://upcloud.com/docs/guides/regaining-access-to-a-server-that-was-deployed-using-ssh-keys/)
that comments out `Include /etc/ssh/sshd_config.d/*.conf` and sets
`PasswordAuthentication yes`: it disables the cloud-init and Schatten
drop-ins, re-enables the main file's `PermitRootLogin yes` and allows root
password login from anywhere while port 22 is public.

Optional, **a developer decision** (not the default): an idle limit for upload
sessions. `upload-gate` already ends each `scp`/`tar` after 10 minutes, which
is the actual limit on how long the gate stays busy; this block additionally
closes forgotten idle connections but does not stop a client that keeps
sending data. Append it at the end of the drop-in (a `Match` block applies to
everything after it), then validate as above:

```bash
printf '\nMatch User schatten-upload\n  ChannelTimeout session=15m\n' \
  | sudo tee -a /etc/ssh/sshd_config.d/10-schatten-hardening.conf >/dev/null
sudo sshd -t && sudo sshd -T -C user=schatten-upload,host=runner,addr=203.0.113.9 | grep -i '^channeltimeout'
```

With it, `audit-host` reports the `Match` block as attention to evaluate; that
is expected. The drop-in, `sshd -t`/`sshd -T`, `AllowUsers` matching and
the optional block were tested in a disposable Ubuntu 26.04 container
([H3 QA](qa/SOURCE-DELIVERY-QA.md#server-makefile-service-command-and-runbook-task-059h3),
[J QA](qa/SOURCE-DELIVERY-QA.md#deploy-and-root-ssh-from-any-address-task-059j));
`systemctl reload` and the real host were not, so validate each before
continuing.

### 2.2 Operator directory, upload account, source tools and GitHub environment

This is the tool bootstrap: the upload gate must exist before the first
upload, and the receiver before the first receive. Both come from the
**approved `main` commit** through an operator workstation.

**Step 1: `/opt/apps`, `make` and the sources folder.** `deploy` creates the
Schatten paths under `/opt/apps` and `check-host` requires `/opt/apps` to be
writable by it; no container writes there. If `audit-host` reported another
owner, inspect it and change only the directory itself, never its existing
contents; `/opt/caddy` stays unchanged:

```bash
sudo ls -la /opt/apps                          # look; do not record names of unrelated files
sudo chown deploy:deploy /opt/apps             # not recursive
sudo chmod 0755 /opt/apps
command -v make || sudo apt-get install --yes make   # only if audit-host reported it missing
install -d -m 0755 /opt/apps/schatten-sources  # as deploy; the receiver refuses a missing or foreign folder
```

If a Schatten path (`schatten`, `schatten-config`, `schatten-state`,
`schatten-releases`, `schatten-sources`, `schatten-upload`) already exists with
another owner, stop and review it instead of changing it. `/opt/apps/schatten`
is the superseded checkout path and is not created.

**Step 2: upload key pair (workstation).** Its private half goes only into the
GitHub secret `SSH_KEY` (step 6); it is never the `deploy` key:

```bash
ssh-keygen -t ed25519 -N '' -C 'schatten-upload' -f schatten-upload
```

**Step 3: copy the tools of the approved commit (workstation).**

```bash
git fetch origin && git merge-base --is-ancestor <approved-commit> origin/main
mkdir -m 0700 schatten-tools
for f in upload-gate schatten-receive; do git show "<approved-commit>:deploy/bin/$f" > "schatten-tools/$f"; done
sha256sum schatten-tools/upload-gate schatten-tools/schatten-receive   # note both values
ssh deploy@<host> 'install -d -m 0700 ~/schatten-tools'
scp schatten-tools/upload-gate schatten-tools/schatten-receive schatten-upload.pub deploy@<host>:schatten-tools/
```

**Step 4: install the tools and create the upload account (host, as
`deploy`).** The account's details are in
[DEPLOYMENT.md](DEPLOYMENT.md#source-delivery-workflow-and-upload-account-task-059h2):

```bash
sha256sum ~/schatten-tools/upload-gate ~/schatten-tools/schatten-receive   # equal to the workstation values
sudo install -o root -g root -m 0755 ~/schatten-tools/upload-gate /usr/local/bin/upload-gate
sudo install -o root -g root -m 0755 ~/schatten-tools/schatten-receive /usr/local/bin/schatten-receive
# Login shell must be a real shell: sshd runs the forced command through it.
sudo useradd --user-group --no-create-home --home-dir /home/schatten-upload --shell /bin/sh schatten-upload
sudo passwd --lock schatten-upload
sudo usermod --append --groups schatten-upload deploy
id schatten-upload        # only its own group: no sudo, docker, adm or deploy groups
# Root-owned home, .ssh and key file: the account cannot change its own restriction.
sudo install -d -o root -g root -m 0755 /home/schatten-upload /home/schatten-upload/.ssh
sudo install -d -o schatten-upload -g schatten-upload -m 0750 /opt/apps/schatten-upload
printf 'restrict,command="/usr/local/bin/upload-gate" %s\n' "$(cat ~/schatten-tools/schatten-upload.pub)" \
  | sudo tee /home/schatten-upload/.ssh/authorized_keys >/dev/null
sudo chown root:root /home/schatten-upload/.ssh/authorized_keys
sudo chmod 0644 /home/schatten-upload/.ssh/authorized_keys
rm -rf ~/schatten-tools
```

Log out and in again as `deploy` so the new group applies. Give the upload
account no sudo rule and no further group. Delete the workstation's
`schatten-upload` private key after step 6; a lost key is replaced with a new
pair, not recovered.

**Step 5: host key fingerprint (host).** `drone-scp` prefers the ECDSA host
key, so `SSH_FINGERPRINT` is its SHA-256 fingerprint:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ecdsa_key.pub    # 256 SHA256:... (ECDSA); the SHA256:... part is the secret value
```

Compare it with the fingerprint shown by the UpCloud console or a trusted
session.

**Step 6: GitHub `production` environment (repository admin).** Create the
environment with deployment branches limited to `main` and these environment
secrets (details in
[DEPLOYMENT.md](DEPLOYMENT.md#source-delivery-workflow-and-upload-account-task-059h2)):
`SSH_HOST`, `SSH_USER=schatten-upload`, `SSH_KEY` (the step 2 private key),
`SSH_PORT=22` and `SSH_FINGERPRINT` (step 5). Record that `main` is protected
against direct and force pushes and deletion, whether required approvals apply
and whether administrators can bypass the protection. Record names, dates and
the fingerprint, never secret values.

**After the first receive** (section 3 step 5), both installed tools must equal
the manifest entries of the same commit; `$M audit` then reports both
root-owned with their hash. When a later manifest changes either file, the
receive still runs with the installed receiver; after it has accepted the new
copy, reinstall the changed file from that copy (section 3 step 6).

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
Leave the optional AI via MCP keys `MCP_ENABLED`,
`MCP_CHANGE_SET_REVIEW_ENABLED` and `MCP_OAUTH_MAX_CLIENTS` out as well: MCP
is then off. Section 14 turns it on with its own approval.

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
from its verified copy (`$M deploy RELEASE=<current-id> APPROVAL=<ref>`;
Compose recreates only containers whose configuration changed), verify login,
then delete the old secret in Entra.

### 2.8 Operator state and prerequisites

These run from the verified copy, so they follow the **first receive**
(section 3 step 5):

```bash
$B/init-state     # creates missing state/lock files only
$M check          # must print PASSED host prerequisites
```

`check-host` rejects a non-Ubuntu-26.04 OS, old Docker/Compose, missing
Buildx, `python3`, `flock`, `sha256sum`, `tar` or `make`, a group-readable env
file, image references in the env file, a socket not mode `660` or with the
wrong group, a Docker TCP listener, missing state/release/source directories or
lock files, wrong backup-directory ownership/mode and a public key inside the
backup directory. It warns while `/usr/local/bin/schatten-receive` is missing
and fails if it is not root-owned or is group/other writable. Git is not
required.

## 3. Deliver, Receive, Build And Freeze A Release

Before approval, for the exact commit to release:

1. Confirm CI passed for that commit on `main` and record the run URL. Local
   checks for the changed scope, simulated OIDC and the disposable runtime
   harness are part of that CI run.
2. Confirm real local direct-Entra browser evidence exists for the release
   scope (see the [authentication checklist](qa/AUTHENTICATION-QA-CHECKLIST.md));
   it does not prove production DNS, TLS or secrets.
3. **Run the Action.** In GitHub: Actions -> "Deploy to production" -> Run
   workflow -> branch `main`. A manual run always uses the branch head, so the
   approved commit must be the head of `main` when you start it. The run
   uploads source only; it builds and deploys nothing.
4. **Check the run and copy the digest.** On the run page, over HTTPS, confirm
   before copying anything: workflow **Deploy to production**, event
   **`workflow_dispatch`**, branch **`main`**, commit equal to the approved
   commit, conclusion **success**, and the job summary's commit, run ID and
   upload folder. If the commit differs because `main` moved, stop: that commit
   needs its own approval. With the GitHub CLI on the workstation the same
   fields are
   `gh run view <run-id> --json workflowName,event,headBranch,headSha,conclusion`.
   Copy **`SOURCE_MANIFEST_SHA256`** from the job summary; never take it from
   the host. On the first real run (F), the upload step's log must also show
   `Downloading drone-scp-1.8.0-linux-amd64 from file://.../drone-scp-release/v1.8.0`
   ([why](DEPLOYMENT.md#source-delivery-workflow-and-upload-account-task-059h2)).
5. **Receive** with the installed receiver, directly (there is no make target:
   the verified copy does not exist yet):

   ```bash
   /usr/local/bin/schatten-receive <SOURCE_MANIFEST_SHA256>
   # SOURCE_DIR=/opt/apps/schatten-sources/<commit>  SOURCE_COMMIT=<commit>  SOURCE_MANIFEST_SHA256=<digest>
   S=/opt/apps/schatten-sources/<commit>; M="make -C $S/deploy"; B=$S/deploy/bin
   ```

   `SOURCE_COMMIT` must be the approved commit. The receiver copies only the
   manifest-listed files of that upload into a read-only copy and refuses
   everything else; see [troubleshooting](#31-delivery-troubleshooting). On the
   first receive, continue with section 2.8 (`$B/init-state`, `$M check`).
6. **Compare the installed tools** with the manifest of the received copy:

   ```bash
   for f in upload-gate schatten-receive; do
     listed="$(awk -v p="deploy/bin/$f" '$3 == p { print $2 }' "$S/SOURCE_MANIFEST")"
     installed="$(sha256sum < "/usr/local/bin/$f" | cut -d' ' -f1)"
     [ "$listed" = "$installed" ] && echo "$f matches" || echo "$f differs"
   done
   ```

   On the first receive both must match (they came from the same approved
   commit in 2.2); otherwise stop. On a later release, a difference means the
   new commit changed the tool: review that change, then reinstall it from the
   copy the existing receiver accepted and rerun the loop:

   ```bash
   sudo install -o root -g root -m 0755 "$S/deploy/bin/<changed tool>" "/usr/local/bin/<changed tool>"
   ```

7. **Build** on the host from the verified copy:

   ```bash
   $M check
   $M build          # build-release --source $S; prints release.env
   ```

   `build-release` builds only from a folder directly under
   `/opt/apps/schatten-sources`, re-verifies its release copy against the
   manifest and uses no Git. Record the printed `RELEASE_ID`, `SOURCE_COMMIT`,
   `SOURCE_MANIFEST_SHA256`, `SOURCE_RUN_ID`, both image IDs, tool versions,
   `BUILD_DURATION_SECONDS` and `BUILD_MEMORY_AVAILABLE_BEFORE_BYTES`.
   `release.env` contains no secrets.
8. Watch the running application during the build (`free -m`,
   `docker stats --no-stream`). Reassess off-server builds after an OOM kill
   or failed build, sustained swap/CPU/memory contention with the running
   services, or a build duration the operator finds unacceptable. A later
   GitHub Actions/GHCR pipeline must deliver the same two images and release
   record; none is implemented.
9. Freeze: after approval nothing is rebuilt. `deploy-release` refuses tags
   that no longer resolve to the recorded image IDs and never pulls or builds
   application images.
10. Record the approval reference: a short non-personal identifier such as a
    PR number or change ID, passed as `APPROVAL=` (`--approval`).

### 3.1 Delivery troubleshooting

| Symptom | Cause and action |
| --- | --- |
| The Action fails in its ref check | It was started from another branch; start it from `main` |
| The Action fails before uploading: secret check | `SSH_USER` is not `schatten-upload` or `SSH_FINGERPRINT` is not a `SHA256:` value (2.2 step 6) |
| `host key fingerprint mismatch` | `SSH_FINGERPRINT` is not the **ECDSA** host key's fingerprint (2.2 step 5) |
| `Permission denied (publickey)` in the upload step | `AllowUsers` lacks `schatten-upload` (2.1), or the authorized key or its `restrict,command=` prefix is wrong; `$M audit` or `audit-host` shows which |
| `upload-gate: refused: another upload-gate command is running` | Another upload session holds the gate's lock. Wait up to 10 minutes (the gate ends each `scp`/`tar` after 10 minutes) or end the upload account's session on the host (`sudo pkill -u schatten-upload`), then rerun the Action |
| `upload-gate: refused: ...` otherwise | The action issued a command the gate does not allow; do not widen the gate on the host. A changed action or input needs developer review ([DEPLOYMENT.md](DEPLOYMENT.md#source-delivery-workflow-and-upload-account-task-059h2)) |
| `schatten-receive`: `no upload under ...` | Wrong digest copied or the upload did not finish; recheck the run summary |
| `schatten-receive`: `does not equal the operator-supplied digest`, `does not match its manifest`, `is a symlink`, `is not refs/heads/main` | The upload is not the approved one; stop and investigate, never edit the upload folder |
| `schatten-receive`: `... already exists` | The commit was received before; use that `S` (it is read-only and cannot change) |
| `schatten-receive`: `... exists: another receive may be running` | Leftover staging after an interrupted receive; once no receive runs, remove it (`chmod -R u+w "$S.incomplete" && rm -rf "$S.incomplete"`) and retry |
| `Services are stopped by service stop` from `deploy`, `first-install` or a rollback | `$M stop` recorded stopped services; run `$M start` (10.2), then deploy again |
| `make: release ... was not built from this source copy` | Run `make` from `/opt/apps/schatten-sources/<that release's commit>/deploy` |

## 4. First Installation (Fresh Database Only)

Use only when the database volume has never been initialized. `deploy-release
--first-install` refuses a database with migration history; do not work
around that. Existing-database adoption is out of scope.

```bash
R=<release-id>; S=/opt/apps/schatten-sources/<commit>; M="make -C $S/deploy"; B=$S/deploy/bin
```

| Step | Command | Expected result; stop otherwise |
| --- | --- | --- |
| 1 | `$M check` | `PASSED host prerequisites` |
| 2 | `$M first-install RELEASE=$R APPROVAL=<ref>` | Pre-migration baseline `BACKUP_ID` recorded as `PRE_CHANGE_BACKUP_ID`; all migrations exit 0; API, one worker and frontend healthy; `STATUS=succeeded`; `current` set; no `previous` |
| 3 | `$B/verify-runtime-hardening` | `PASSED runtime hardening`; `deploy-release` already required this, rerun it to capture the output for the record (Ofelia is checked on activation in step 11) |
| 4 | `$B/initialize status` | `users_including_deleted=0`, `active_default_metamodels=0`, `organisations=0`: nothing was seeded at startup |
| 5 | `$B/initialize reference-seed` then `$B/initialize status` | `active_default_metamodels=1`, non-zero `node_types`/`edge_types`/`type_attributes`/`allowed_connections`, still `users_including_deleted=0` |
| 6 | `$B/initialize bootstrap-admin` in a private terminal | Prompts for the designated display name and Entra email; prints `Administrator bootstrap completed.` |
| 7 | `$B/initialize status` | `users_including_deleted=1`, `active_admins=1`, `user_identities=0`, `auth_sessions=0` |
| 8 | `$M backup` | `BACKUP_ID=` of the initialized database |
| 9 | Restore rehearsal of that ID (section 8.3) | `STATUS=success`; evidence shows `rows table=users count=1` and `rows table=metamodels count=1` |
| 10 | `$M status` | Both backups listed; latest restore evidence `STATUS=success` |
| 11 | `$B/deploy-release $R --approval <ref> --enable-scheduler` | Scheduler activation (section 9): hardening passes including Ofelia; `SCHEDULER=active` in the record |
| 12 | First direct-Entra login by the designated admin | Guarded first link; then provision the designated consultant through the normal Users administration |
| 13 | Narrow production smoke (section 7) | All items pass |
| 14 | Next day: `$M status` | A `-scheduled-` backup is listed and Ofelia logged `failed: false` |

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
R2=<new-release-id>; S2=/opt/apps/schatten-sources/<new-commit>; M2="make -C $S2/deploy"
```

1. Deliver, receive and build `R2` (section 3), including the tool comparison
   in step 6. Review its migrations for expand/contract compatibility and
   record whether the current release could run against the new schema (this
   decides the rollback option).
2. Rehearse the newest completed backup (section 8.3) so the evidence is
   current. The gate needs the **latest** evidence file to be `STATUS=success`;
   a failed or missing rehearsal blocks the release until a successful one exists.
3. `$M2 check`, then `$M2 deploy RELEASE=$R2 APPROVAL=<ref>`. It takes the
   pre-change backup, runs migrations, replaces API/worker/frontend, recreates
   runners and updates Ofelia if it is running.
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

Rollback has no make target on purpose: it needs the explicit schema review.
Like every release, it is refused while `$M stop` has services recorded as
stopped (10.2).

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
| On demand | `$M backup` (`$B/backup-now --reason manual`); every release takes a `pre-release` backup automatically |
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
$M status     # ops-status: pointers, newest completed backups, latest restore evidence, scheduler results
```

### 8.3 Restore rehearsal

Bring the private key and passphrase to the host only for the rehearsal, into
the operator's private runtime directory (tmpfs), and remove them afterwards:

```bash
install -d -m 0700 "/run/user/$(id -u)/schatten-restore"
# From the workstation, from the two separate vault entries; the passphrase
# file contains only the passphrase on its first line:
scp backup-private-key.asc backup-key-passphrase deploy@<host>:/run/user/<uid>/schatten-restore/
# On the host (restore-rehearsal into a disposable database, never production):
$M restore BACKUP=<backup-id> \
  KEY="/run/user/$(id -u)/schatten-restore/backup-private-key.asc" \
  PASSPHRASE="/run/user/$(id -u)/schatten-restore/backup-key-passphrase"
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
$M cleanup-dry-run               # docker-cleanup --dry-run: lists candidates, removes nothing
$B/retire-release <old-id>       # makes an old, non-current, non-previous release eligible
```

Any failed listing, removal or cache prune exits `1` with `status=failed`.
Docker cleanup is not a backup mechanism and is separate from the 7-day
backup retention.

## 10. Operations: Health, Restart, Reboot, Certificates

### 10.1 Health and diagnosis

```bash
$M ps                          # containers of the current release with state and health
$M logs SERVICE=backend        # last 200 lines; without SERVICE= every service
curl -sS https://schatten.lupaus.eu/health
docker logs --since 30m <container> 2>&1 | tail -n 50   # a longer or older window
```

`ps` and `logs` act on the `current` release through its frozen Compose file
and never print `docker compose config` or environments. `SERVICE=` is one of
`database`, `migration`, `backend`, `prediction-worker`, `frontend`, `ofelia`,
`backup-runner`, `cleanup-runner`.

Health checks: database `pg_isready`; API `/health`; worker its lock-owning
health command; Caddy a loopback `127.0.0.1:8081/health` that does not depend
on certificates. Logs redact callback query values and credential headers, but
summarize rather than paste auth logs. Use `docker inspect --format` for
specific fields; plain `docker inspect` of application, database or backup
containers prints their secret environment.

### 10.2 Stop and start the application

```bash
$M stop      # stops the running services, scheduler included; keeps containers, volumes and networks
$M start     # starts exactly the services that stop recorded, in order, and waits until healthy
```

`stop` refuses while a build, release, rollback or backup runs, records the
services it stopped in `/opt/apps/schatten-state/stopped-services` and stops
them in reverse order with their grace periods. While stopped, the site and
scheduled backups are down. `start` starts those same containers (database,
API, worker, frontend, then Ofelia if it was running), never the completed
migration job or the runners, and refuses when nothing was recorded or the
record names another release. A second `stop` before `start` is refused.
Neither command creates, recreates or removes containers or volumes; after a
configuration change, `$M start` and then redeploy the current release
(`$M deploy RELEASE=<current-id> APPROVAL=<ref>`). Never use
`docker compose down`.

While the record exists:

- `deploy-release` refuses every release, first install and rollback, so a
  deploy cannot leave the stopped scheduler off; run `$M start` first.
- The services stay stopped across reboots and Docker daemon restarts
  (`restart: unless-stopped`) until `$M start`.
- `$M status` lists the recorded release and services under
  `stopped by service stop`.

### 10.3 Restart and reboot

Services use `restart: unless-stopped`. On reboot Docker restarts database, API,
worker and frontend from their existing containers, except services stopped
with `$M stop`, which stay stopped until `$M start` (10.2); the completed migration
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
happens. Afterwards confirm healthy containers (`$M ps`), `/health` and
`$M status` (which lists services still stopped by `$M stop`).
Record the effective unattended-upgrades automatic-reboot setting from
`audit-host`; an automatic reboot at an unplanned time follows the same
recovery path.

### 10.4 Persistence

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
| "Deploy to production" run URL, `SOURCE_RUN_ID`, `SOURCE_MANIFEST_SHA256`, the run checks of section 3 step 4 | Run page, `release.env` |
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
| `MCP_ENABLED`, `MCP_CHANGE_SET_REVIEW_ENABLED`, `MCP_OAUTH_MAX_CLIENTS` and the MCP approval reference when MCP was turned on | Deployment record `MCP_*`, `MCP_APPROVAL`; section 14 |

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

What TASK-059E and TASK-059H1-H3 exercised on disposable infrastructure
([E QA record](qa/UPCLOUD-RUNBOOK-QA.md),
[H1-H3 QA record](qa/SOURCE-DELIVERY-QA.md)); everything else is F
verification.

| Section | Tested (E, H1-H3) | Not testable before F |
| --- | --- | --- |
| 1 Host audit | `audit-host` in a disposable Ubuntu 26.04 baseline container, directly, through `bash -s` and as `make audit` from a read-only verified copy, before and after the 2.1/2.2 setup and with negative variants (H3) | Real host results, fresh SSH sessions, provider firewall |
| 2.1 SSH | Hardening drop-in, `sshd -t`/`sshd -T`, the optional `Match` block (H3); `AllowUsers deploy root schatten-upload` with `PermitRootLogin prohibit-password` overriding a main-file `yes`, `deploy` and root accepted by key from an arbitrary address, password logins and other accounts refused (J) | `systemctl reload ssh`, lockout safety, the real UFW/provider rules, UpCloud recovery procedures |
| 2.2 Directory, upload account, tools | `/opt/apps` ownership (E); the upload account, root-owned key file with `restrict,command=`, upload folder, `install` of both tools and the gate refusing shells and commands (H2, H3) | The workstation copy of the real approved commit, GitHub environment and secrets, real fingerprint |
| 2.3 Configuration | Configuration contract and privacy checks (`check-host`) with synthetic values | Real secrets |
| 2.4 Backup keys | Key generation/export commands with gpg 2.4.8 on Ubuntu 26.04; passphrase-protected key used for all harness restores | Vault storage and custodians |
| 2.5-2.6 Storage, DNS | Backup directory ownership/mode checks | DNS, public certificate issuance |
| 2.7 Entra | Simulated discovery only | Callbacks, secret, assignments, cleanup |
| 3 Delivery | The pinned action's upload through `upload-gate` in an sshd container, the job summary digest, `schatten-receive` acceptance and rejections, Git-free `make build` (H1-H3) | The real Action run, its run page checks and the `file://` log line |
| 2.8, 4-6 | `init-state`, `check-host`, `make build`, `make first-install`, `make deploy` and its guards, initialization, `make backup`/`restore`/`status`, gates and direct-command rollback on Engine 28.5.2 and 29.8.1 daemons, with Git absent from `PATH` | The real host and its resources |
| 7 Smoke | Local simulated-OIDC suites | Production smoke |
| 8-10 | Backups, failures, retention, passphrase restore, scheduler, cleanup, persistence, daemon restart; `make ps`/`logs`/`stop`/`start` keeping containers and volumes, with and without Ofelia (H3); the reboot lock refusing while a holder exists (with `echo` in place of `systemctl reboot`) | Real schedule runs, real reboot, certificate renewal |
| 14 MCP | Enable, review-switch-only disable, full disable with the 404 surface, offboarding by soft delete and admin revocation, client cap, incident steps 1-4 and log redaction against the local stack; env-file switches, refused non-plain env-file lines and non-boolean rendered values, the `--mcp-approval` gate, the warning for a release that ignores the env file, the recorded values and `ops-status` in the disposable runtime (TASK-069P, [checklist](qa/AI-MCP-QA-CHECKLIST.md)) | The production redeploy, vendor-cloud connectors, real traffic |

## 14. AI Via MCP: Enable, Disable, Offboarding And Incidents

[ADR-015](decisions/ADR-015-ai-via-mcp.md) lets Users connect their own MCP
client (claude.ai, Claude Desktop, Claude Code or another client) to
`https://schatten.lupaus.eu/api/mcp/read` and `/api/mcp/write`. Schatten is the
OAuth 2.1 server over the existing Entra login; the Entra registration does not
change. Local evidence is in
[AI-MCP-QA-CHECKLIST.md](qa/AI-MCP-QA-CHECKLIST.md); the production items there
stay pending until the approved enablement records them.

**Enabling MCP in production needs its own recorded human approval
(TASK-069P).** A merge to `main` is not that approval.

### 14.1 Settings

Three MCP settings come from the protected env file
(`/opt/apps/schatten-config/production.env`, 2.3); every other MCP setting is a
literal value in `docker-compose.production.yml` and changes only through a
reviewed release
([configuration contract](DEPLOYMENT.md#ai-via-mcp-settings-task-069e-task-069f-task-069g-task-069p)).

| Setting | Where, default | Effect |
| --- | --- | --- |
| `MCP_ENABLED` | Env file, `false` when unset | `false`: the MCP endpoints, discovery, registration, authorize, consent, token and revoke and the skill zips answer 404, so no token works and no grant is issued. The connections API, the admin revocation and the change-set review API stay available |
| `MCP_CHANGE_SET_REVIEW_ENABLED` | Env file, `false` when unset | With `MCP_ENABLED=true`, `true` adds `apply_change_set` and `reject_change_set` to the write server. `false` keeps staging only |
| `MCP_OAUTH_MAX_CLIENTS` | Env file, `10000` when unset | Client cap (14.5) |
| `MCP_OAUTH_REDIRECT_URIS` | Compose: claude.ai and claude.com callbacks, `http://localhost:{port}/callback` | Redirect URI allowlist. The loopback entry is Claude Code's; TASK-069P removed the unused `127.0.0.1` and `[::1]` entries. Adding a client with another callback is a reviewed release |

Write each as a plain `KEY=value` line. The two switches accept exactly `true`
or `false`, and the cap a positive whole number; `$M check` reports any other
value, or an `export`-prefixed, indented or `KEY: value` line, as an error and
shows the values the next deploy applies. `deploy-release` also refuses a
release that would give the backend any other value. The backend reads them at
startup, so a change takes effect when the **current release is deployed
again**:

```bash
$M deploy RELEASE=<current-release-id> APPROVAL=<ref> [MCP_APPROVAL=<ref>]
```

**Only releases built from a commit that includes TASK-069P read these keys.**
Older releases, including the first production release `v0.1.0`, keep MCP off
and the cap at 10,000 in their frozen Compose file. Deploying such a release
keeps those values whatever the env file says: `deploy-release` then warns
that the release ignores the env file's MCP settings, and its record shows
what was deployed. So the first enablement, or a first cap change, deploys a
newly built release (section 3) instead of the current one.

This is a normal `deploy-release`: it needs the latest successful restore
evidence, takes a pre-change backup and replaces API, worker and frontend
(section 5). **Turning MCP on, or turning its change-set review on while MCP is
on, is refused without `MCP_APPROVAL`** (`--mcp-approval`); turning either off,
leaving them unchanged or changing only the cap needs no MCP approval. Each
deployment record holds `MCP_ENABLED`, `MCP_CHANGE_SET_REVIEW_ENABLED`,
`MCP_OAUTH_MAX_CLIENTS` and, when given, `MCP_APPROVAL`; `$M status` shows the
deployed values and the env file's values.

### 14.2 Enable (approved release)

1. Record the approval and complete the
   [enablement gate](qa/AI-MCP-QA-CHECKLIST.md#production-enablement-gate).
2. **Enable the review switch together with MCP.** Turning
   `MCP_CHANGE_SET_REVIEW_ENABLED` on later gives existing write grants the
   apply and reject tools although their consent said "proposals only"; if it
   is ever turned on later, tell the Users first.
3. Add to the env file, then check:

   ```text
   MCP_ENABLED=true
   MCP_CHANGE_SET_REVIEW_ENABLED=true
   ```

   ```bash
   $M check    # shows: env file AI via MCP (applied by the next deploy of a release built from TASK-069P or later): MCP_ENABLED=true ...
   ```

4. Deploy a release that reads the env file (14.1) with both references, from
   its verified source copy:
   `$M deploy RELEASE=<release-id> APPROVAL=<ref> MCP_APPROVAL=<ref>`. While
   the current release predates TASK-069P, deliver, build and approve a new
   release first (section 3); otherwise use the current release. If
   `deploy-release` warns that the release ignores the env file's MCP
   settings, MCP stayed off: deploy a newer release instead.
   Then run the narrow smoke (section 7) and the MCP smoke:
   - `curl -sS https://schatten.lupaus.eu/.well-known/oauth-authorization-server`
     returns issuer `https://schatten.lupaus.eu`;
   - `curl -sS -o /dev/null -D - -X POST https://schatten.lupaus.eu/api/mcp/read`
     returns `401` with `WWW-Authenticate: Bearer resource_metadata=...`;
   - a designated account connects one client to both servers, approves the
     consent pages and calls `whoami`, and stages and decides one change set in
     an isolated test organisation;
   - the remaining production items of the QA checklist, without load,
     rate-limit or attack tests.
5. Tell Users how to connect (README "Connect an AI client") and to reconnect
   existing clients after the release.

### 14.3 Disable

- **Full disable:** set `MCP_ENABLED=false` in the env file (or remove the
  line), then `$M deploy RELEASE=<current-release-id> APPROVAL=<ref>`; no MCP
  approval is needed. Every MCP and OAuth endpoint then answers 404; grants
  are kept but unusable.
- **Apply and reject only:** set `MCP_CHANGE_SET_REVIEW_ENABLED=false` and
  deploy the current release the same way. The write server loses the two
  tools and keeps staging; humans still apply in the Metrics tab. Clients that
  cached the tool list get "Unknown tool".
- The redeploy keeps the release gates. If the latest restore evidence is
  failed or missing, rehearse the newest backup first (8.3). If MCP must stop
  before that is possible, `$M stop` takes the whole application down (10.2)
  until the redeploy can run.
- Re-enabling needs a new recorded approval and `MCP_APPROVAL` (14.2).

### 14.4 Offboarding

Disabling the Entra account alone does **not** end MCP access: a grant lives up
to 30 days, renewed by refresh, without an Entra check (ADR-015 accepted
trade-off). When a person leaves or loses access:

1. soft-delete their Schatten User in the Users tab, which stops every MCP call
   at once (the next call gets 401), **or**
2. if the User must stay, use **Revoke AI connections** on the User in the
   Users tab, which revokes all of the User's grants (`reason=admin_revoke`).

Users can revoke their own connections in the connections list. Admin session
revocation ends browser sessions only, not grants.

### 14.5 Client Cap

`MCP_OAUTH_MAX_CLIENTS` (10,000 non-deleted registered clients) bounds client
rows. When it is full, `POST /api/oauth/register` answers 503
`temporarily_unavailable` and the backend logs
`MCP OAuth client registration refused: the cap of <n> non-deleted clients is
reached`. Only new registrations are blocked; existing clients and grants keep
working. Stale clients (no active grant, unused for 30 days) are cleaned up
lazily. The immediate remedy is to raise `MCP_OAUTH_MAX_CLIENTS` in the env
file and deploy the current release again (14.1; a release built before
TASK-069P keeps 10,000, so deploy a newer one); no MCP approval is needed.
Lowering the `register` rate limit only slows refilling and does not unblock a
full cap.

### 14.6 Incident Procedure

Use it when MCP access or an MCP-applied change is suspicious. It needs no
manual database change.

1. **Stop MCP.** Full disable (14.3): `MCP_ENABLED=false` in the env file and
   a redeploy of the current release. When only applies or rejects through MCP
   are suspicious, set `MCP_CHANGE_SET_REVIEW_ENABLED=false` instead; staging
   stays available.
2. **Revoke.** An admin uses **Revoke AI connections** on every affected User
   (or soft-deletes the User); Users may revoke their own connections. Both
   work while MCP is disabled.
3. **Review change sets.** Reject suspicious submitted change sets in the
   Metrics tab AI panel, which works while MCP is disabled. Find change sets
   applied or rejected through MCP by their "via <client> (MCP)" label, or with
   the read service's `list_change_sets` (`reviewed_via`,
   `review_client_name`) after re-enabling. Applied changes are corrected
   through the normal UI; there is no automatic undo.
4. **Re-enable** only with a new recorded human approval, given to the deploy
   as `MCP_APPROVAL` (14.2).

Record times, the release IDs, the affected change set keys and the number of
revoked grants, without names, tokens or client ids.

### 14.7 What To Check In Logs

```bash
BACKEND=$(docker ps -q --filter label=com.docker.compose.project=schatten --filter label=com.docker.compose.service=backend)
CADDY=$(docker ps -q --filter label=com.docker.compose.project=schatten --filter label=com.docker.compose.service=frontend)
docker logs --since 24h "$BACKEND" 2>&1 | grep -E 'MCP OAuth|AI change set'
docker logs --since 24h "$CADDY" 2>&1 | grep -E '/api/oauth/|/api/mcp/' | grep -c '"status":429'
```

| Entry | Meaning |
| --- | --- |
| `MCP OAuth client registered: client_id=... self_declared_client_name=...` | A new client registration; the name is self-declared |
| `MCP OAuth grant revoked: reason=... actor=... user_id=... grant_key=...` | `user_revoke`, `admin_revoke`, `code_reuse`, `refresh_token_reuse` and others; reuse reasons can mean a stolen token and deserve a look |
| `MCP OAuth client registration refused: the cap of ...` | Client cap reached (14.5) |
| `MCP OAuth lazy cleanup step ... skipped after a lock conflict` | Harmless; cleanup retries on a later request |
| `AI change set <key> apply failed in step ...` | An apply rolled back; the change set is `failed` and the AI stages a new one |
| Caddy `429` on `/api/oauth/*` or `/api/mcp/*` | A rate-limit bucket is full (per client address for OAuth, per grant for MCP) |

The logs never contain tokens, authorization codes, pending request ids or tool
arguments: Caddy replaces `request`, `return_to`, `code`, `state`, token query
parameters, every `Authorization` request header and every `Location` response
header with `REDACTED`. Seeing any such value is itself an incident. Summarize
rather than paste log lines.

### 14.8 Tool Schema Changes

MCP tool results are strict (`additionalProperties: false`). Claude Code
validates results against the output schema it cached when it connected, so
after a release that adds a field to a tool result (TASK-069O added the review
channel to every change-set summary) already-connected Claude Code sessions
reject those results until they reconnect (`/mcp` in Claude Code). With every
release that changes tool results, tell Users to reconnect their clients (in
claude.ai and Claude Desktop, reconnect the connector). Whether vendor-cloud
connectors cache schemas the same way is a pending production check.

### 14.9 Observed Client Behaviour

From the local run of 2026-10-30
([checklist](qa/AI-MCP-QA-CHECKLIST.md)); production clients are pending.

- **Approval of apply and reject.** The human decision is the client's tool
  approval plus the user's instruction in the chat. Claude Code running in
  auto mode called `apply_change_set` and `reject_change_set` **without a
  prompt**; any setting that allows these tools without asking has the same
  effect, and then only the user's instruction and the review fingerprint
  stand between the AI and the data. Advise Users to keep these two tools on
  "ask". Claude Code's default-mode prompt, Claude Desktop and claude.ai are
  recorded at enablement.
- **Concurrent sessions.** Claude Code uses one client registration per
  configured server and reuses it on reconnect. Re-authorizing a client for the
  same User and resource revokes that grant's earlier tokens, so another
  session holding them is signed out until it reconnects (ADR-015 accepted
  consequence). Whether vendor connectors share one `client_id` across Users is
  recorded at enablement.
- **Elicitation.** Claude Code 2.1.314 ships MCP elicitation support; Schatten
  does not use it (ADR-015 defers server-side confirmation).
