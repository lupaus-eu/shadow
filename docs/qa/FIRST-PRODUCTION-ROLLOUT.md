# First Production Rollout Record (TASK-059F)

This is the F record named by the
[production runbook](../PRODUCTION-RUNBOOK.md): sanitized evidence for the
authorized setup of the existing UpCloud host and the first production release
of [TASK-059F](../../tasks/TASK-059F-first-production-rollout.md). The
operator fills it in while following the runbook; section numbers in brackets
refer to runbook sections.

**Status (2026-11-02): host setup, delivery, first install, initialization,
backups with restore rehearsals, scheduler activation, the first scheduled
backups and the 7-day retention prune are recorded for release
`20261002T085353Z-0db661289165`, with the product owner's confirmations of
UpCloud two-factor authentication, the host-key deviation, the TASK-059B
evidence scope, the shared Entra coupling and backup key access; the UpCloud
provider firewall is enabled, smoke item 5 passes and smoke item 4 is an
accepted risk; the 2.7 Entra scopes and assignment-count confirmations and the
Entra cleanup are deferred as accepted deviations. Accepted by the main
developer on 2026-11-02 and tagged `v0.1.0`.**
Entries still
marked *Pending* have not been performed or confirmed; *Accepted deviation*
and *Not performed* entries are explained in the
[failure log](#10-failure-and-deviation-log). This record authorizes nothing.
Disposable evidence stays in
[UPCLOUD-RUNBOOK-QA.md](UPCLOUD-RUNBOOK-QA.md) (E) and
[SOURCE-DELIVERY-QA.md](SOURCE-DELIVERY-QA.md) (H1-H3, J). SSH access follows
the [ADR-013 TASK-059J amendment](../decisions/ADR-013-shared-entra-local-https-deployment.md#operator-ssh-access-from-any-address):
`deploy` and key-only root from any address.

## Recording Rules

| Label | Meaning |
| --- | --- |
| Reported | Operator-supplied information (the cloud-init baseline, a role's own statement); not evidence |
| Tested (E, H1-H3, J) | Exercised against disposable local infrastructure |
| Verified (F) | Observed on the real host/provider under approval and recorded here |
| Recorded | A decision or acknowledgement by the named role; nothing to observe |
| Not performed | Not done: an optional check, or a required one whose gap is in the [failure log](#10-failure-and-deviation-log) |
| Accepted deviation | Not performed or not as the runbook requires; the gap and who accepted it are in the [failure log](#10-failure-and-deviation-log) |
| Pending | Not yet performed; never mark it complete without doing it |

- Record identifiers, counts, statuses, versions, hashes, fingerprints and
  times only. Use roles (operator, repository admin, tenant administrator,
  tester), not names.
- Never record `production.env` contents, `docker compose config` output, full
  `docker inspect` of application/database/backup containers, private keys,
  passphrases, SSH keys, secret values, cloud-init user-data, raw auth/callback
  logs, cookies, tokens, personal names, personal emails or operator IP
  addresses/CIDRs. Write `<operator-cidr>` instead of the real network.
- Record only checks actually performed. Leave blocked or skipped items
  *Pending*, or *Accepted deviation* once a role accepts the gap, and note why
  in the [failure log](#10-failure-and-deviation-log).
- Stop at the first failed gate (runbook section 0).

## Authorizations

Each provider mutation and production operation needs explicit operational
approval before it is performed. `APPROVAL=` values are short non-personal
references such as a PR number or change ID.

| Scope | Approval reference | Approver role | Date | Status |
| --- | --- | --- | --- | --- |
| Host access/SSH/UFW/provider firewall changes (2.1) | CHG-10-01-2026-upcloud-deploy-schatten | Product owner | 2026-10-01 | Approved |
| `/opt/apps`, `make`, upload account and source tools (2.2) | CHG-10-01-2026-upcloud-deploy-schatten | Operator (developer) | 2026-10-01 | Approved |
| GitHub `production` environment and secrets (2.2 step 6) | CHG-10-01-2026-upcloud-deploy-schatten | Operator (developer) | 2026-10-01 | Approved |
| Protected configuration, backup key and backup directory (2.3-2.5) | CHG-10-01-2026-upcloud-deploy-schatten | Operator (developer) | 2026-10-01 | Approved |
| DNS for `schatten.lupaus.eu` (2.6) | CHG-10-01-2026-upcloud-deploy-schatten | Operator (developer) | 2026-10-01 | Approved |
| Entra production callback and secret (2.7) | CHG-10-01-2026-upcloud-deploy-schatten | Operator (developer) | 2026-10-01 | Approved |
| Entra cleanup of Authentik callbacks and Graph `User.Read` (2.7) | CHG-10-01-2026-upcloud-deploy-schatten | Operator (developer) | 2026-10-01 | Approved |
| First release and first install, `APPROVAL=` (3-4) | CHG-10-01-2026-upcloud-deploy-schatten | Operator (developer) | 2026-10-01 | Approved |
| Backup activation and scheduler activation (4 step 11, 9) | CHG-10-01-2026-upcloud-deploy-schatten | Operator (developer) | 2026-10-01 | Approved |
| Planned reboot, if a reboot is pending (10.3) | CHG-10-01-2026-upcloud-deploy-schatten | Operator (developer) | 2026-10-01 | Approved |

## 1. Host Baseline (Read-Only) [1]

| Item | Value |
| --- | --- |
| Host identifier (UpCloud server name/UUID, no IP) | `ubuntu-1cpu-2gb-fi-hel1` |
| Operator role, date/time | Operator (developer), 2026-10-01 |
| `audit-host` source (approved `main` commit via `bash -s`, or `$M audit`) | `0db6612891651b9d7e378885efaf084fa2c7c65a` via `git show ... \| ssh ... bash -s` |
| `SUMMARY attention=N missing=M` | `attention=7 missing=0` |

### 1.1 Fresh sessions [1.1]

| Account | Key login | Password/keyboard-interactive | Status |
| --- | --- | --- | --- |
| `deploy` | accepted (exit 0) | refused: `Permission denied (publickey)`, no prompt | Verified (F), 2026-10-01 |
| `root` | Not performed (optional; root key holder only) | refused: `Permission denied (publickey)`, no prompt | Verified (F), 2026-10-01 |
| Image default user (`ubuntu`) | Not tested (operator holds no key for it) | refused: `Permission denied (publickey)`, no prompt | Verified (F), 2026-10-01 |

Host keys accepted by the operator workstation (2026-10-01, from
`ssh-keygen -F <host> -l`; public fingerprints, not secret):

| Type | Fingerprint |
| --- | --- |
| ED25519 | `SHA256:MbxCz2o9Mobu/M+B4ztYODX2M7e+v5anwJntBxvMTSw` |
| RSA | `SHA256:lLN5AgTVZSoRrc3QUZk1Yyn22vtqzr1mI3eVwtB6NNg` |
| ECDSA | `SHA256:fdYOAAbPROxBgc45aU+BFeo19YukPIs3cqeLjJFmeWA` |

Comparison (2026-10-01): the operator compared the fingerprints over
connections from different network paths and they matched. No out-of-band
comparison with the UpCloud console was performed; the product owner accepted
the network-path comparison on 2026-10-30 (see the
[failure log](#10-failure-and-deviation-log)).

### 1.2 Audit results [1.2]

| Area | Reported | Verified (F) | Status |
| --- | --- | --- | --- |
| OS/kernel, uutils coreutils, sudo-rs, required tools | Ubuntu 26.04 LTS | Ubuntu 26.04.1 LTS, kernel 7.0.0-29-generic, uutils coreutils 0.8.0, sudo-rs 0.2.13-0ubuntu1.2; `python3`, `curl`, `gpg`, `openssl`, `flock`, `ss` ok; `make` not installed (attention) | Verified (F) |
| Git presence (fact only) | | Git 2.53.0 present; not used by Schatten | Verified (F) |
| cloud-init status, error/recoverable-error counts | | `status=done exit=0 errors=0 recoverable=0` | Verified (F) |
| Accounts: password status, key counts, sudo/docker/adm | Default user retained; `deploy` locked password, keys, `sudo`/`docker`, passwordless sudo | `deploy` uid 1000, password `L`, 2 authorized keys (main developer, product owner), groups `sudo,docker`, passwordless sudo; `docker` group members: `deploy` only | Verified (F) |
| Root: password status, key count, keys with the `disable_root` prefix | Observed before F (not evidence): locked, 1 key, 0 prefixed; the key belongs to the product owner | Password `L`, 1 authorized key, 0 of 1 with the `disable_root` prefix | Verified (F) |
| SSH effective settings (`sshd -T`) | `ssh_pwauth: false`, `disable_root: false`; observed before F: main `sshd_config` sets `PermitRootLogin yes` | Port 22 on IPv4/IPv6; `permitrootlogin=yes` (attention), `passwordauthentication=no`, `kbdinteractiveauthentication=no`, `pubkeyauthentication=yes`, `authenticationmethods=any`, `permitemptypasswords=no`, `usepam=yes`, `maxauthtries=6`; `allowusers`/`allowgroups` unset (attention); `ssh.socket` and `ssh.service` active | Verified (F) |
| UFW rules | Deny incoming; allow OpenSSH, TCP 80/443 | Active; default deny incoming, allow outgoing, deny routed; 22/tcp (OpenSSH), 80/tcp, 443/tcp allowed from Anywhere on IPv4 and IPv6; nothing else. SSH-from-Anywhere attention until 2.1 | Verified (F) |
| UpCloud provider firewall IPv4/IPv6 (manual) | | Per the UpCloud account holder's console view (2026-10-01): firewall status disabled, 0 rules; listed defaults (incoming drop all, outgoing accept all) and an outgoing SMTP-block rule (TCP 25) are not applied while disabled. UFW is the only packet filter; see the attention decisions | Verified (F), by the account holder |
| Non-loopback listeners, Docker API listener | | TCP: only 22 (IPv4/IPv6). UDP: DHCP client (68) and DHCPv6 client (546) only; other listeners loopback. No 2375/2376 Docker API listener | Verified (F) |
| Docker Engine/containerd/Compose/Buildx versions | Docker APT repository packages | Engine 29.8.1, containerd v2.3.5, runc 1.5.1, docker-init 0.19.0, Compose 5.5.1, Buildx v0.37.1; overlayfs, cgroup 2, apparmor + seccomp; `daemon.json` absent; socket `660` `root:docker` (gid 1000) | Verified (F) |
| Containers publishing ports other than 80/443 | | No containers (`running=0 all=0`) | Verified (F) |
| Swap, `vm.swappiness`/`vm.vfs_cache_pressure`, CPUs, memory, disk | 2 GiB swap, 10/50 | `/swapfile` 2 GiB, 1 fstab entry, 0 used; 10/50; 1 CPU; 1849 MiB memory, 1271 MiB available; `/`, `/var/lib/docker` and `/opt` share `/dev/vda2`, 20062 MiB, 12694 MiB available | Verified (F) |
| Timezone, NTP | `Europe/Helsinki` | `Europe/Helsinki`, NTP synchronized | Verified (F) |
| fail2ban `sshd` jail, ban counts, `maxretry`/`findtime`/`bantime` | Enabled, 5/600/3600 | Active, `sshd` jail present, currently banned 2, total 40, 5/600/3600 | Verified (F) |
| unattended-upgrades, automatic reboot, pending reboot, held packages | Enabled | Enabled and active, `apt-daily-upgrade.timer` enabled, periodic update/upgrade 1; `Automatic-Reboot` unset (no automatic reboot); **reboot pending** (attention); no held packages | Verified (F) |
| `/opt/apps`, `/opt/caddy`, `/opt/postgres-backups` owner/mode/entry count | Created | Each `root:root` `755`, 0 entries, on `/dev/vda2`; no Schatten paths; 0 backup manifests; upload account, upload folder, `upload-gate` and `schatten-receive` absent | Verified (F) |

Attention items and the F decision for each (runbook 1.2 table):

| Audit finding | Decision | Status |
| --- | --- | --- |
| `tool make is not installed` | Install `make` (2.2 step 1) | Done: `ok tool make` in the post-reboot audit |
| `permitrootlogin=yes`: root SSH is not key-only | Hardening drop-in with `PermitRootLogin prohibit-password` (2.1) | Done: `ok root SSH is key-only` |
| `AllowUsers is not set` | `AllowUsers deploy root schatten-upload` (2.1) | Done: `allowusers=deploy,root,schatten-upload` |
| SSH allowed from Anywhere while root login is not key-only | Harden SSH first (2.1); afterwards an accepted fact | Done: reported as an accepted fact |
| Reboot pending | Planned reboot after 2.1 and before the first release, while nothing runs; needs the 10.3 authorization row | Done 2026-10-01: rebooted after 2.1 and `make`; kernel 7.0.0-29 -> 7.0.0-34, `no reboot pending` |
| `/opt/apps` owner root | `chown deploy:deploy`, non-recursive (2.2 step 1) | Done 2026-10-01 (directory was empty) |
| `/opt/postgres-backups` owner `0:0` mode `755` | `chown 10002:10002`, `chmod 0700`, non-recursive (2.5) | Done 2026-10-02 |
| UpCloud provider firewall disabled (not an audit line; manual check) | Account holder's decision 2026-10-01: keep the provider firewall at its defaults (disabled) and filter with UFW; revisit at the provider if needed. Docker-published ports bypass UFW, so exposure relies on only the frontend publishing 80/443 (verified in 5 and 6). Revisited 2026-10-30: the main developer enabled the provider firewall with the product owner's agreement | Done 2026-10-30: enabled (2.1) |

## 2. Remaining Setup [2]

### 2.1 SSH and port 22 [2.1]

| Check | Expected | Observed | Status |
| --- | --- | --- | --- |
| `sshd -t` | No output | No output (2026-10-01) | Verified (F) |
| `sshd -T` | `permitrootlogin prohibit-password` (alias `without-password`), `passwordauthentication no`, `kbdinteractiveauthentication no`, `allowusers deploy`, `allowusers root` and `allowusers schatten-upload` | All six lines as expected (2026-10-01) | Verified (F) |
| `sshd -T -C user=root,host=workstation,addr=203.0.113.9` | `permitrootlogin prohibit-password`, `passwordauthentication no`, `kbdinteractiveauthentication no` | All three as expected (2026-10-01) | Verified (F) |
| New session after reload | `deploy` accepted with its key; password and keyboard-interactive as `deploy` and root refused; image default user refused | 2026-10-01: `deploy` key login exit 0; password/keyboard-interactive as `deploy`, root and `ubuntu` refused (`Permission denied (publickey)`) | Verified (F) |
| Root key login by the root key holder | Optional; "not performed" is acceptable | Not performed | Not performed |
| UFW | 22/tcp from Anywhere (v4/v6), 80/443 public, nothing else | 2026-10-01: active, default deny incoming; 22/tcp (OpenSSH), 80/tcp, 443/tcp from Anywhere on IPv4 and IPv6; nothing else | Verified (F) |
| UpCloud provider firewall | TCP 22 (IPv4; IPv6 only if intended), TCP 80/443, nothing else | 2026-10-30: enabled by the main developer with the product owner's agreement. The firewall is stateless, so it also needs rules for replies to the host's own connections (see the failure log). Defaults: incoming drop, outgoing accept (account-level TCP 25 block unchanged). Auto-add DNS rules on. Incoming accept: TCP 22 on IPv4 only (no SSH over IPv6), TCP 80 and 443 on IPv4 and IPv6; ICMP and ICMPv6 (any type); replies from TCP source ports 443, 80 and 4460 (NTS key exchange) and UDP source port 123; DHCP (UDP 67 -> 68) and DHCPv6 (UDP 547 -> 546); reply, ICMP and DHCP rules for both IPv4 and IPv6. The reply rules match the source port only and accept any destination port, so for such packets the provider firewall is no second filter: UFW, which is stateful, stays the effective one ([12](#12-follow-up)). Time sync: chrony, `chronyc -N authdata` lists only plain-NTP `ubuntu.pool.ntp.org` sources; the NTS sources configured in `/etc/chrony` are not in use, rule 4460 kept for them. Checks after enabling (main developer): new `deploy` SSH session ok; `/health` `OK`; on the host `login.microsoftonline.com` resolves, the Entra OpenID configuration and the Let's Encrypt ACME directory return `200`, `apt-get update` without errors, `chronyc sources` reachability rising; Entra sign-in to Schatten works | Verified (F) |
| Provider firewall: next-day SSH and `/health` (DHCP lease renewal) | Both still work a day after enabling | 2026-11-02, three days after enabling (main developer): new `deploy` SSH session ok; `/health` `OK` | Verified (F) |
| Rerun `audit-host` | `ok`: `root SSH is key-only`, password and keyboard-interactive disabled, `AllowUsers admits deploy from any address`, `AllowUsers admits root from any address`, `AllowUsers admits schatten-upload`; facts: main-file `PermitRootLogin yes` overridden, SSH from `Anywhere` accepted | 2026-10-01, after reboot: all listed `ok` lines and both facts present; `SUMMARY attention=2 missing=0` (remaining: `/opt/apps` and `/opt/postgres-backups` ownership, 2.2/2.5) | Verified (F) |
| Key counts after 2.1 | `deploy`: one key per operator; root: unchanged (1), 0 with the `disable_root` prefix | `deploy`: 2 (main developer, product owner); root: 1, 0 prefixed; passwords locked | Verified (F) |
| Root key holder | Role (product owner) | Product owner (reported; key count unchanged at 1, verified in the row above) | Reported |
| Optional upload `ChannelTimeout` | Developer decision: used / not used | Not used (developer decision 2026-10-01; `upload-gate`'s 10-minute limit applies); may be revisited | Recorded |

Recovery ([runbook 2.1](../PRODUCTION-RUNBOOK.md#recovery-without-ssh)):
`AllowUsers` shuts out the image default user and every account other than
`deploy`, root and `schatten-upload`. All passwords stay locked; recovery uses
another working key or UpCloud's disk-move procedure, never a commented-out
`Include` or password SSH.

| Item | Observed | Status |
| --- | --- | --- |
| UpCloud account access holder (role; initially the product owner) | Product owner | Recorded, 2026-10-01 |
| Its authentication set up (as reported by the holder) | Two-factor authentication enabled; confirmed by the holder (product owner) on 2026-10-30 | Reported, by the account holder |
| Recovery path acknowledged by (role/date) | Main developer, authorized by the product owner, 2026-10-01 | Recorded |

### 2.2 Operator directory, upload account, tools, GitHub [2.2]

| Item | Observed | Status |
| --- | --- | --- |
| `/opt/apps` owner/mode (non-recursive change only) | 2026-10-01: was `root:root` `755`, empty; now `deploy:deploy` `755` (non-recursive) | Verified (F) |
| `make` installed (only if missing) | Installed 2026-10-01 (`ok tool make`) | Verified (F) |
| `/opt/apps/schatten-sources` created by `deploy`, `0755` | 2026-10-01: `deploy:deploy` `755` | Verified (F) |
| Approved `main` commit for the tools (ancestor of `origin/main`) | `0db6612891651b9d7e378885efaf084fa2c7c65a` (head of `origin/main`; `merge-base --is-ancestor` ok) | Verified (F) |
| `upload-gate` SHA-256: workstation = host | Workstation `723349b3699aebeb54e9a56255bc5963482515f0d38f49d5d3287375ade1877c` (equals the approved commit's blob); host copy before `install` and installed `/usr/local/bin` file: equal (2026-10-01) | Verified (F) |
| `schatten-receive` SHA-256: workstation = host | Workstation `f08ca5d1d70a7bf6781bd8b7a5e3ad2914f925bb1d9ee270f95053275de23c25` (equals the approved commit's blob); host copy before `install` and installed `/usr/local/bin` file: equal (2026-10-01) | Verified (F) |
| Both installed root-owned `0755` in `/usr/local/bin` | 2026-10-01: `upload-gate` and `schatten-receive` `root:root` `755` | Verified (F) |
| `schatten-upload`: locked password, own group only, no sudo/docker/adm/deploy groups | 2026-10-01: uid 1001, `groups=1002(schatten-upload)` only; `passwd -S` status `L` | Verified (F) |
| `deploy` member of the `schatten-upload` group | 2026-10-01: `deploy` groups `deploy`, `sudo`, `docker`, `schatten-upload` (after re-login) | Verified (F) |
| Root-owned home, `.ssh` and `authorized_keys`; one key with `restrict,command="/usr/local/bin/upload-gate"` | 2026-10-01: home and `.ssh` `root:root` `755`, `authorized_keys` `root:root` `644`; one line starting `restrict,command="/usr/local/bin/upload-gate" ssh-`; `ssh-keygen -lf` fingerprint equals the generated key `SHA256:nLCc4lWuRV6dorQ9s1DU9PJwvwrlW3dgRZa8GlDchIk` | Verified (F) |
| `/opt/apps/schatten-upload` `schatten-upload:schatten-upload` `0750` | 2026-10-01: `schatten-upload:schatten-upload` `750` | Verified (F) |
| Upload key pair generated on the operator workstation (ed25519, comment `schatten-upload`), fingerprint | 2026-10-01: `SHA256:nLCc4lWuRV6dorQ9s1DU9PJwvwrlW3dgRZa8GlDchIk` | Verified (F) |
| Workstation upload private key deleted after GitHub secret set | 2026-10-01: deleted; clipboard cleared | Verified (F) |
| ECDSA host key fingerprint (`SHA256:...`), compared with console | 2026-10-01: host `ssh-keygen -lf /etc/ssh/ssh_host_ecdsa_key.pub` = `SHA256:fdYOAAbPROxBgc45aU+BFeo19YukPIs3cqeLjJFmeWA`, equal to the workstation's accepted ECDSA key (1.1). Console comparison not performed; the product owner accepted the 1.1 network-path comparison instead (2026-10-30) | Verified (F) |
| GitHub `production` environment limited to `main` | Not configured by F: the operator cannot create environments; the product owner decided on 2026-10-01 to use repository secrets instead (see the failure log). 2026-11-02: a `production` environment exists; the main developer takes as known that it is used only with `main`; its deployment-branch setting was not observed | Accepted deviation |
| Environment secret names present: `SSH_HOST`, `SSH_USER`, `SSH_KEY`, `SSH_PORT`, `SSH_FINGERPRINT` (names only) | Repository secrets (accepted deviation) `SSH_HOST`, `SSH_USER`, `SSH_KEY`, `SSH_PORT`, `SSH_FINGERPRINT` set 2026-10-01 | Verified (F) |
| `main` protection: direct/force push and deletion blocked; required approvals; admin bypass | 2026-10-01: no ruleset applies to `main`; classic branch protection not visible to the operator (no admin access). Push, force-push, deletion and bypass settings were configured and accepted by the product owner (repository admin); not independently verified, and whether administrators can bypass the protection is not known (see the [failure log](#10-failure-and-deviation-log)). Required approvals: none (sole developer). GitHub refuses to delete the default branch | Accepted deviation |
| No GitHub deploy key, no host checkout | 2026-10-01: no deploy keys; no Schatten checkout on the host (`/opt/apps` held only `schatten-sources`, `schatten-upload`) | Verified (F) |

### 2.3-2.5 Configuration, backup key, backup directory [2.3-2.5]

| Item | Observed | Status |
| --- | --- | --- |
| `/opt/apps/schatten-config` `0700`; `production.env` `0600`, contract keys only (no values recorded) | 2026-10-02: folder `deploy` `700`, file `deploy` `600`; exactly the 11 contract keys `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL`, `OIDC_DISCOVERY_URL`, `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `PUBLIC_ORIGIN`, `DOCKER_SOCKET_GID`, `SCHATTEN_BACKUP_PUBLIC_KEY`; no image keys; no empty values | Verified (F) |
| `DOCKER_SOCKET_GID` matches socket group | 2026-10-02: `1000`, equal to the socket group `docker` (gid 1000) | Verified (F) |
| Production-only `OIDC_CLIENT_SECRET` (owner role, expiry date) | 2026-10-02: new production-only client secret created; owner: product owner (Entra administrator); expires 2027-02-20; rotate before expiry (runbook 2.7) | Verified (F) |
| Backup key fingerprint (not secret) | 2026-10-02: `31A0AE2E1EF129E4AAC542262CAED7FC30C3B720` (read from the host's public key file) | Verified (F) |
| Private key and passphrase stored separately off-host; custodian roles for each | 2026-10-02: private key and passphrase in separate password-manager entries; custodian of both: main developer. 2026-10-30: both transferred securely to the product owner; custodians of both: main developer and product owner | Verified (F) |
| `backup-public-key.asc` on host `0644`, no secret key material | 2026-10-02: `deploy:deploy` `644`; 0 `PRIVATE KEY` lines | Verified (F) |
| `/opt/postgres-backups` `10002:10002` `0700`, existing contents preserved | 2026-10-02: `10002:10002` `700`; directory was empty (audit: 0 entries), change non-recursive | Verified (F) |

### 2.6 DNS and TLS [2.6]

| Item | Observed | Status |
| --- | --- | --- |
| `A schatten.lupaus.eu` points to the host | 2026-10-01: `dig +short A` returns the host's address (compared by the operator with the SSH `HostName`; address not recorded). Record was created before F; see the 2.6 authorization row | Verified (F) |
| `AAAA` decision (recommended: none initially) | 2026-10-01: `dig +short AAAA` returns nothing; no `AAAA` record published, following the recommendation | Verified (F) |
| Certificate issuer and expiry after first start (section 7 command) | 2026-10-02, from the operator workstation: `issuer=C=US, O=Let's Encrypt, CN=YE1`, `notAfter=Dec 31 08:58:30 2026 GMT`; `https://schatten.lupaus.eu/health` returned `OK` | Verified (F) |

### 2.7 Entra shared registration [2.7]

| Setting | Expected | Verified | Status |
| --- | --- | --- | --- |
| Production Web redirect URI | `https://schatten.lupaus.eu/api/v1/auth/callback` | Added 2026-10-02 | Verified (F) |
| Production post-logout return | `https://schatten.lupaus.eu/login` | Added 2026-10-02 | Verified (F) |
| Development entries kept | `https://app.localhost/api/v1/auth/callback`, `https://app.localhost/login` | Kept 2026-10-02 | Verified (F) |
| Issuer | `https://login.microsoftonline.com/<tenant-id>/v2.0` (exact) | 2026-10-02: `OIDC_ISSUER` in `production.env` has this form (operator) | Verified (F) |
| Scopes and claims | `openid profile email`; no Graph calls; no `email_verified` requirement | Not confirmed; deferred until after the rollout (main developer, 2026-11-02; see the [failure log](#10-failure-and-deviation-log)) | Accepted deviation |
| Separate secrets and databases per environment | Development and production independent | 2026-10-02: production uses its own new client secret and its own `production.env`/database; development secret unchanged | Verified (F) |
| Shared coupling recorded | Consent, permissions, assignments and callbacks shared by both environments | Acknowledged by the product owner (Entra administrator) on 2026-10-30 | Recorded |
| Enterprise-app assignments | Designated testers and production users assigned (count only) | Count not recorded; deferred until after the rollout (main developer, 2026-11-02; see the [failure log](#10-failure-and-deviation-log)) | Accepted deviation |
| Remaining consumers of Authentik callbacks and Graph `User.Read` | Checked before removal; coordinated with B cutover | Unknown whether the product owner has checked; deferred until after the rollout (main developer, 2026-11-02; see the [failure log](#10-failure-and-deviation-log)) | Accepted deviation |
| Cleanup performed | Only unused configuration removed; required scopes and unrelated consumers kept; identity rows not rewritten | Not performed; deferred with the consumer check above | Accepted deviation |

### 2.8 Operator state and prerequisites [2.8]

Runs after the first receive (section 4 below).

| Check | Expected | Observed | Status |
| --- | --- | --- | --- |
| `$B/init-state` | Missing state/lock files created only | 2026-10-02T08:46:37Z: created `schatten-releases` (+`retired`), `schatten-state` with `locks`, `deployments`, `restore-evidence` and the `maintenance`, `backup`, `release` lock files; backup directory ownership verified, not changed | Verified (F) |
| `$M check` | `PASSED host prerequisites` | All `ok` (Ubuntu 26.04, tools, Engine 29.8.1, Compose 5.5.1, Buildx v0.37.1, private env file, socket group 1000 mode 660, writable paths, root-owned `schatten-receive`, backup directory `10002:10002` `700`, public key); free disk 12687 MiB, memory available 1336 MiB; `PASSED host prerequisites` | Verified (F) |

## 3. Local Direct-Entra Evidence [3 step 2]

The real local browser evidence is the
[TASK-059B record](AUTHENTICATION-QA-CHECKLIST.md#task-059b-direct-entra-local-evidence)
(2026-09-24). Before release approval F confirms it still covers the release's
authentication scope, or records a new authorized run here.

| Item | Value | Status |
| --- | --- | --- |
| Authentication changes between the TASK-059B commits and the release commit | 2026-10-02: application code at fix commit `3d6ffb45` equals the squash merge `e9a0b3f` (#82). From `e9a0b3f` to release `0db6612` no OIDC, session, CSRF or identity-linking code changed. Related changes: the User email check moved into a shared `validate_user_email_address` (same pattern), now also used by the admin bootstrap (#84); production `frontend/Caddyfile` became the TLS edge, forwarding `{remote_host}` instead of trusted-proxy `{client_ip}` (#85), tested in E's disposable QA | Verified (F) |
| Decision: existing evidence covers the scope / new run recorded (reference) | Existing TASK-059B evidence covers the authentication scope; the production TLS edge and callback are covered by the narrow production smoke (section 8). Confirmed by the product owner on 2026-10-30, after the deployment instead of before release approval (see the [failure log](#10-failure-and-deviation-log)) | Recorded |

## 4. Delivery, Receive And Build [3]

| Item | Value | Status |
| --- | --- | --- |
| Approved commit (head of `main` when the Action started) | `0db6612891651b9d7e378885efaf084fa2c7c65a`; `origin/main` head on 2026-10-02 before the run; the run used this commit | Verified (F) |
| CI run URL for that commit | https://github.com/reflector-oy/schatten/actions/runs/36849690862, conclusion success, all jobs passed (2026-10-02) | Verified (F) |
| "Deploy to production" run URL and run ID | https://github.com/reflector-oy/schatten/actions/runs/36984268698, run ID `36984268698` | Verified (F) |
| Run page: workflow, event `workflow_dispatch`, branch `main`, commit, conclusion `success` | 2026-10-02: workflow "Deploy to production", "Manually triggered" (`workflow_dispatch`), ref `refs/heads/main`, commit `0db6612891651b9d7e378885efaf084fa2c7c65a`, status Success. Summary upload folder `/opt/apps/***/0db6612...` (GitHub masks `schatten-upload` because it equals the `SSH_USER` secret) | Verified (F) |
| Upload step log shows `Downloading drone-scp-1.8.0-linux-amd64 from file://.../drone-scp-release/v1.8.0` | `Downloading drone-scp-1.8.0-linux-amd64 from file:///home/runner/work/_temp/drone-scp-release/v1.8.0` | Verified (F) |
| `SOURCE_MANIFEST_SHA256` (from the job summary) | `b929961199148b2f397a9585fffd8e19061e42bac8bc1e82dedf4ee02ed696ae` | Verified (F) |
| `schatten-receive` output: `SOURCE_DIR`, `SOURCE_COMMIT` equals approved commit | 2026-10-02: `Accepted 482 files`; `SOURCE_DIR=/opt/apps/schatten-sources/0db6612891651b9d7e378885efaf084fa2c7c65a`, `SOURCE_COMMIT=0db6612891651b9d7e378885efaf084fa2c7c65a` (approved commit), `SOURCE_MANIFEST_SHA256` equals the run summary's | Verified (F) |
| Installed `upload-gate` and `schatten-receive` match the manifest | `upload-gate matches`, `schatten-receive matches` | Verified (F) |
| `RELEASE_ID` | `20261002T085353Z-0db661289165` (built 2026-10-02T08:55:15Z; `SOURCE_REF=refs/heads/main`, `SOURCE_DATE_EPOCH=1790850693`) | Verified (F) |
| `SOURCE_RUN_ID` | `36984268698` (equals the Action run) | Verified (F) |
| Backend and frontend image IDs | `schatten-backend:20261002T085353Z-0db661289165` `sha256:6ac5da49ccd05f2969a569571f28283f804da15cef692d8993227abf90e13441`; `schatten-frontend:20261002T085353Z-0db661289165` `sha256:0d8930318f36ba0e8f591da04d672aea7fb19e221fb042de4fbffd37bd84e192` | Verified (F) |
| Tool versions from `release.env` | Docker Engine 29.8.1, Compose 5.5.1, Buildx v0.37.1, kernel 7.0.0-34-generic | Verified (F) |
| `BUILD_DURATION_SECONDS`, `BUILD_MEMORY_AVAILABLE_BEFORE_BYTES` | 82 s; 1407832064 bytes (about 1343 MiB) | Verified (F) |
| Resource observations during build (`free -m`, `docker stats`) | Not captured; build completed in 82 s without OOM or failure, no application running yet (see the [failure log](#10-failure-and-deviation-log)) | Not performed |
| Build location decision: on-host adequate / off-server build needed | On-host adequate (main developer, 2026-10-02): 82 s, no OOM. Reassess if a later build, which runs beside the live application, is slow, fails or causes OOM/swap contention | Recorded |
| Artifacts frozen; no rebuild after approval | Release `20261002T085353Z-0db661289165` frozen 2026-10-02; the first-install record's image IDs equal `release.env` | Verified (F) |

## 5. First Installation [4]

| Step | Expected | Observed (sanitized) | Status |
| --- | --- | --- | --- |
| 1 `$M check` | `PASSED host prerequisites` | 2026-10-02: passed | Verified (F) |
| 2 `$M first-install` | `PRE_CHANGE_BACKUP_ID` recorded; migrations exit 0; API, one worker, frontend healthy; `STATUS=succeeded`; no `previous` | Record `20261002T095601Z-20261002T085353Z-0db661289165.env`: started 09:56:01Z, finished 09:57:03Z; `MODE=first-install`, `APPROVAL=CHG-10-01-2026-upcloud-deploy-schatten`, `PREVIOUS_RELEASE=none`, `PRE_CHANGE_BACKUP_ID=schatten-20261002T095628Z-pre-release-aea673`, `MIGRATION_EXIT_CODE=0`, `SCHEDULER=not-activated`, `STATUS=succeeded`; image IDs equal `release.env`; `PASSED runtime hardening`. `$M ps`: `database`, `backend`, one `prediction-worker` and `frontend` running and healthy; `migration` exited (0); `backup-runner` and `cleanup-runner` created, not running | Verified (F) |
| 2 PostgreSQL | Image reference/version 18, volume `schatten_postgres_data`, no published port | Image `docker.io/library/postgres:18.6@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280` (Compose pin); volume `schatten_postgres_data` present; `schatten-database-1` shows only unpublished `5432/tcp` | Verified (F) |
| 2 Pre-migration baseline restore | Isolated rehearsal of the baseline backup, `STATUS=success` (evidence file) | 2026-10-02T10:19:41Z: `BACKUP_ID=schatten-20261002T095628Z-pre-release-aea673` into a disposable network-isolated `postgres:18.6` (pinned digest); checksum, decrypt-and-restore, schema-migrations (version 0), table-count (0 tables) and constraints all `pass`; `STATUS=success`. Version 0 and 0 tables are expected: the backup precedes the first migration | Verified (F) |
| 3 `verify-runtime-hardening` | `PASSED runtime hardening` | 2026-10-02: `PASSED runtime hardening` | Verified (F) |
| 4 `initialize status` | `users_including_deleted=0`, `active_default_metamodels=0`, `organisations=0` | 2026-10-02: `schema_version=15`; all counts 0 (`active_default_metamodels`, `node_types`, `edge_types`, `type_attributes`, `allowed_connections`, `users_including_deleted`, `active_admins`, `user_identities`, `auth_sessions`, `organisations`) | Verified (F) |
| 5 `initialize reference-seed`, status | `active_default_metamodels=1`, non-zero type counts, `users_including_deleted=0` | 2026-10-02: `Reference data seed completed.`; `active_default_metamodels=1`, `node_types=11`, `edge_types=9`, `type_attributes=40`, `allowed_connections=14`; users, admins, identities, sessions and organisations 0 | Verified (F) |
| 6 `initialize bootstrap-admin` (private terminal, recording off) | `Administrator bootstrap completed.` | 2026-10-02: `Administrator bootstrap completed.`; name and email entered privately, not recorded. Admin: main developer (admin Entra account) | Verified (F) |
| 7 `initialize status` | `users_including_deleted=1`, `active_admins=1`, `user_identities=0`, `auth_sessions=0` | 2026-10-02: `users_including_deleted=1`, `active_admins=1`, `user_identities=0`, `auth_sessions=0`, `organisations=0`; reference counts unchanged | Verified (F) |
| 8 `$M backup` | Initialized `BACKUP_ID` | 2026-10-02T10:39:30Z: `BACKUP_ID=schatten-20261002T103929Z-manual-4395b2`, `status=completed`, 134983 bytes, sha256 `836c4bcefaaac8c1592aafd773c135122748e9932af2a131e7e3e42ed81299d1`, `retention_days=7 retention=ok pruned=0`, free 10126958592 bytes (about 9.4 GiB) | Verified (F) |
| 9 Restore rehearsal of that ID | `STATUS=success`; `users` count 1, `metamodels` count 1; evidence file | 2026-10-02T10:52:13Z: `BACKUP_ID=schatten-20261002T103929Z-manual-4395b2` into a disposable network-isolated `postgres:18.6`; checksum, decrypt-and-restore, schema-migrations (version 15), table-count (27) and constraints `pass`; rows `users=1`, `metamodels=1`, `node_types=11`, `edge_types=9`, `type_attributes=40`, `allowed_connections=14`, `schema_migrations=15`, all other tables 0; `STATUS=success`; evidence file `20261002T105204Z-46311-schatten-20261002T103929Z-manual-4395b2.txt` | Verified (F) |
| 10 `$M status` | Both backups listed; latest restore evidence `STATUS=success` | 2026-10-02: current `20261002T085353Z-0db661289165`, no previous; backups `schatten-20261002T103929Z-manual-4395b2`, `schatten-20261002T095628Z-pre-release-aea673`; latest evidence 10:52:13Z for the manual backup, `STATUS=success`; Ofelia not running (not yet activated) | Verified (F) |
| 11 `--enable-scheduler` | Hardening incl. Ofelia passes; `SCHEDULER=active` | 2026-10-02 ~11:00Z: deployment record `SCHEDULER=active`; `schatten-ofelia-1` running; services unchanged and healthy. `PASSED runtime hardening` including Ofelia; record `PRE_CHANGE_BACKUP_ID=schatten-20261002T105943Z-pre-release-69b3f2`, `MIGRATION_EXIT_CODE=0` (no-op), `SCHEDULER=active`, `STATUS=succeeded` | Verified (F) |
| 12 First admin login; consultant provisioned via Users administration | Guarded first link; one identity | 2026-10-02 14:45 (main developer): bootstrapped admin (main developer's admin Entra account) signed in through Entra and was linked; via Users administration an admin User for the product owner and a consultant User (main developer's second Entra account) were created; the consultant then signed in and was linked. Status: `users_including_deleted=3`, `active_admins=2`, `user_identities=2` (bootstrapped admin, consultant; the product owner has not signed in), `auth_sessions=0` after logout. One organisation created by the main developer during testing (`organisations=1`); it copies the default metamodel, so type counts doubled to 22/18/80/28 while `active_default_metamodels=1`. The main developer decided on 2026-11-02 to retain the organisation as the designated isolated smoke record (runbook section 7), not business data | Verified (F) |
| 13 Narrow smoke | See [section 8](#8-narrow-production-smoke-7) | Items 1-3 (2026-10-02) and 5 (2026-10-30) pass; item 4 not run in production, accepted risk (see the [failure log](#10-failure-and-deviation-log)) | Verified (F) |
| 14 Next day `$M status` | A `-scheduled-` backup listed; Ofelia `failed: false` | Checked 2026-10-05, not on 2026-10-03 (see the [failure log](#10-failure-and-deviation-log)): current `20261002T085353Z-0db661289165`, no previous; scheduled backups `schatten-20261002T233000Z-scheduled-6bcb34`, `schatten-20261003T233001Z-scheduled-8cfa6b`, `schatten-20261004T233001Z-scheduled-ab38a7` listed above the three 2026-10-02 backups; Ofelia (last 48 h) `postgres-backup` 2026-10-04 02:30 and 2026-10-05 02:30 (+03:00) `failed: false, skipped: false, error: none`; latest restore evidence unchanged (2026-10-02T10:52:13Z, `STATUS=success`) | Verified (F) |

No development User inserts, manual production SQL, automatic startup seed or
identity creation occurred: confirmed by the operator (main developer),
2026-10-02. Users were created only by `bootstrap-admin` and Users
administration; identities only by Entra sign-in.

## 6. Scheduler And Docker Control Boundary [9]

Verified against
[ADR-013's hardening contract](../decisions/ADR-013-shared-entra-local-https-deployment.md#operational-scheduler-and-docker-control-boundary)
before recording activation. Any failed control blocks activation.

| Control | Observed | Status |
| --- | --- | --- |
| Ofelia, backup-runner, cleanup-runner images digest-pinned (references) | Ofelia running `docker.io/mcuadros/ofelia:0.3.22@sha256:efcbe2c5cf658a25de6443c1462d653f9cc03791d642e01fc6c638a00f97e492`; Compose pins backup runner `postgres:18.6@sha256:4ef4dbc9...2280` and cleanup runner `docker:28.5.2-cli@sha256:625d9431...dd4d` | Verified (F) |
| API, migration, worker and frontend run the frozen image IDs | Deployment records carry `release.env`'s backend `sha256:6ac5da49...3441` and frontend `sha256:0d893031...e192`; the cleanup dry run keeps exactly these two as `release-or-container` | Verified (F) |
| Only the frontend publishes ports, only 80/tcp and 443/tcp | 2026-10-02: `schatten-frontend-1` publishes `0.0.0.0`/`[::]` 80/tcp and 443/tcp; its `443/udp` and `2019/tcp` and the backend/worker `8000/tcp` and database `5432/tcp` are image-exposed only, not published | Verified (F) |
| Ofelia and cleanup runner `network_mode: none`; others only on `schatten_data` | 2026-10-02 `verify-runtime-hardening` after activation (all `ok`, `PASSED runtime hardening`): Ofelia and cleanup runner `network_mode none`; backup runner, database, migration and worker join only the private data network; data network internal | Verified (F) |
| Non-root, read-only root filesystem, all capabilities dropped, `no-new-privileges`, not privileged, no host namespaces/devices/supplementary groups | 2026-10-02 `verify-runtime-hardening` after activation (all `ok`, `PASSED runtime hardening`): every container (backend, frontend, migration, worker `10001:10001`; backup runner `10002:10002`; database `999:999`; Ofelia and cleanup runner `65534:1000`) passes all of these; all protected from Docker cleanup | Verified (F) |
| Socket mounted only into Ofelia and cleanup runner; mode `660`; no TCP listener | 2026-10-02 `verify-runtime-hardening` after activation (all `ok`, `PASSED runtime hardening`): only Ofelia and the cleanup runner have the local Docker socket, all others have none; socket mode `660` and no Docker TCP listener per `check-host`/`audit-host` | Verified (F) |
| Ofelia without `--docker`; job file read-only; jobs only start pre-created runners | Ofelia `cmd=[daemon --config /etc/ofelia/config.ini]` (no `--docker`); 2026-10-02 `verify-runtime-hardening` after activation (all `ok`, `PASSED runtime hardening`): label discovery disabled, job file read-only, jobs `postgres-backup` and `docker-cleanup` only start pre-created runners | Verified (F) |
| Only backup runner has writable bind mount and database credential; no host root, PostgreSQL data or Caddy storage mounts | 2026-10-02 `verify-runtime-hardening` after activation (all `ok`, `PASSED runtime hardening`): only the backup runner has a writable bind mount (`/backups`) and it receives only the database credential; Ofelia, cleanup runner and frontend receive no secrets; no container mounts the host root; each mounts only its own persistent volumes | Verified (F) |
| Weekly cleanup exclusions (`$M cleanup-dry-run` candidates reviewed; volumes, backups, current/previous images protected) | 2026-10-02T11:03Z dry run (7 days): keeps `schatten-migration-1` (retain label) and both current release images; only candidate BuildKit cache (762.2 MB reclaimable, older than 168 h); no volume, network or backup candidates; `containers_removed=0 images_removed=0 failures=0`. First scheduled run: Ofelia `docker-cleanup` 2026-10-04 04:30 (+03:00) `failed: false, skipped: false, error: none`; on 2026-10-05 `$M status` showed the release unchanged and all six backups still present. 2026-10-18 04:30 (+03:00) run `failed: false, skipped: false, error: none`; on 2026-10-19 the release is unchanged | Verified (F) |
| Non-overlap: backup and maintenance locks | `backup.lock`, `maintenance.lock` and `release.lock` created by `init-state` (2.8, Verified (F)); exclusion behavior tested in E, not exercised on the host | Tested (E) |
| Single application prediction worker; Ofelia does not replace it | 2026-10-02 after activation: exactly one `prediction-worker` container, healthy; Ofelia runs as a separate `ofelia` service | Verified (F) |

## 7. Backups [8]

| Item | Observed | Status |
| --- | --- | --- |
| Daily job `postgres-backup` 02:30 `Europe/Helsinki` active | 2026-10-05 `$M status`: one scheduled backup per night at 23:30Z (02:30 `Europe/Helsinki`, EEST) on 2026-10-02, 10-03 and 10-04 UTC; files written Oct 3, 4 and 5 02:30 local time, 136324 bytes each. 2026-10-19 `$M status`: one scheduled backup per night from 2026-10-11 to 2026-10-18 at 23:30Z, no gaps; Ofelia `postgres-backup` 2026-10-18 and 2026-10-19 02:30 (+03:00) `failed: false, skipped: false, error: none` | Verified (F) |
| 7-day retention active (first prune observed, or date it becomes observable) | 2026-10-19 `$M status`: the eight completed backups are the scheduled ones from `schatten-20261011T233001Z-scheduled-2c6c47` to `schatten-20261018T233000Z-scheduled-9cb3e4`, one per night; every backup older than 7 days is gone, including the three 2026-10-02 daytime backups (`pre-release-aea673`, `manual-4395b2`, `pre-release-69b3f2`) and the scheduled backups of 2026-10-02 to 2026-10-10. The 2026-10-11T23:30:01Z backup is kept at the 2026-10-18T23:30:00Z run because it is just under 7 days old. The individual `pruned=` counts are outside the 48-hour window and were not captured | Verified (F) |
| Backup files `0600`, owner `10002`, encrypted for the recorded key fingerprint | 2026-10-05 `sudo ls -l /opt/postgres-backups`: 12 files (6 `.dump.gpg` + `.manifest` pairs), each `-rw-------` (`0600`) `10002:10002`; no other files. All six manifests record `ENCRYPTION_KEY_FINGERPRINT=31A0AE2E1EF129E4AAC542262CAED7FC30C3B720`, equal to the recorded backup key fingerprint (2.3-2.5) | Verified (F) |
| First scheduled `BACKUP_ID` and Ofelia `failed: false` | `schatten-20261002T233000Z-scheduled-6bcb34` (written 2026-10-03 02:30 local time). Its Ofelia line is outside the 48-hour window `$M status` showed on 2026-10-05; the next two runs (2026-10-04 and 2026-10-05 02:30) logged `failed: false` | Verified (F) |
| Failure reporting understood (exit 1 failure, exit 2 retention failure, no automatic retry) | Confirmed by the operator (main developer), 2026-10-05: exit `1` = failed backup, nothing published (`status=failed`); exit `2` = backup completed but retention failed; no automatic retry, fix the cause and run `$M backup`. Failures are visible only on the host through `$M status` (newest backups, Ofelia `failed:` results for 48 h) and the Ofelia container log (runbook 8.1, 8.2, 9); there is no automatic alerting | Recorded |
| Key material removed from `/run/user/<uid>/schatten-restore` after each rehearsal | 2026-10-02 after both rehearsals (baseline and step 9): host folder removed (`removed`); workstation copies deleted | Verified (F) |

Accepted limitation: backups share the host and disk with the database, so
host or disk loss can destroy both. Accepted until separately planned
off-server protection (ADR-013).

## 8. Narrow Production Smoke [7]

| Item | Tester role | Time | Result |
| --- | --- | --- | --- |
| 1 `/health` returns `OK`; certificate publicly trusted | Main developer | 2026-10-02, after step 11 | Pass: `OK`; `issuer=C=US, O=Let's Encrypt, CN=YE1`, `notAfter=Dec 31 08:58:30 2026 GMT` |
| 2 Admin: login, clean callback, session on reload, Users visible, logout to `/login`, session `401` | Main developer | 2026-10-02 14:45 | Pass (all checks) |
| 3 Consultant: login, no Users administration, logout | Main developer | 2026-10-02 14:45 | Pass: no Users administration |
| 4 Unmatched account fails generically; no User/identity/session created (status counts) | Main developer | 2026-10-30 | Not run in production: no suitable account (a designated tenant account without a matching Schatten User) is available. Passed locally (reported by the main developer); risk accepted by the product owner (see the [failure log](#10-failure-and-deviation-log)) |
| 5 One prediction on an isolated record: queued -> calculating -> completed, one worker | Main developer | 2026-10-30 | Pass: prediction on the test organisation (the designated isolated smoke record, retained; see [5](#5-first-installation-4) step 12) queued -> calculating -> completed. `$M ps` afterwards (rerun with `M` set, see the [failure log](#10-failure-and-deviation-log)): release `20261002T085353Z-0db661289165`, exactly one `prediction-worker`, running and healthy; `backend`, `database` and `frontend` healthy, `ofelia` running; the frontend alone publishes ports, 80/tcp and 443/tcp |

Commit and image IDs tested: `0db6612891651b9d7e378885efaf084fa2c7c65a`,
backend `sha256:6ac5da49ccd05f2969a569571f28283f804da15cef692d8993227abf90e13441`,
frontend `sha256:0d8930318f36ba0e8f591da04d672aea7fb19e221fb042de4fbffd37bd84e192`
(release `20261002T085353Z-0db661289165`). No broad, destructive, load or security
suites were run in production: confirmed by the operator (main developer),
2026-10-02; only the narrow smoke checks above.

## 9. Release Record [11]

| Field | Value |
| --- | --- |
| Release ID, approved commit, CI run URL | `20261002T085353Z-0db661289165`; `0db6612891651b9d7e378885efaf084fa2c7c65a`; https://github.com/reflector-oy/schatten/actions/runs/36849690862 (success) |
| Deploy run URL, `SOURCE_RUN_ID`, `SOURCE_MANIFEST_SHA256` | https://github.com/reflector-oy/schatten/actions/runs/36984268698; `36984268698`; `b929961199148b2f397a9585fffd8e19061e42bac8bc1e82dedf4ee02ed696ae` (run checks in [4](#4-delivery-receive-and-build-3)) |
| Backend and frontend image IDs | `sha256:6ac5da49ccd05f2969a569571f28283f804da15cef692d8993227abf90e13441`; `sha256:0d8930318f36ba0e8f591da04d672aea7fb19e221fb042de4fbffd37bd84e192` |
| Tool versions, build duration, available memory | Docker Engine 29.8.1, Compose 5.5.1, Buildx v0.37.1, kernel 7.0.0-34-generic; 82 s; 1407832064 bytes |
| Local/CI evidence and local Entra evidence reference | CI run 36849690862; [TASK-059B record](AUTHENTICATION-QA-CHECKLIST.md#task-059b-direct-entra-local-evidence) (2026-09-24), scope review in [3](#3-local-direct-entra-evidence-3-step-2) |
| Approval reference | `CHG-10-01-2026-upcloud-deploy-schatten` |
| Mode, previous release | `first-install`, none (first release) |
| Pre-change backup ID | First install: `schatten-20261002T095628Z-pre-release-aea673`; scheduler activation: `schatten-20261002T105943Z-pre-release-69b3f2` |
| Latest successful restore evidence: file, time, backup ID, result | `/opt/apps/schatten-state/restore-evidence/20261002T105204Z-46311-schatten-20261002T103929Z-manual-4395b2.txt`; 2026-10-02T10:52:13Z; `schatten-20261002T103929Z-manual-4395b2`; `STATUS=success`. That backup and both pre-change backups were removed by the 7-day retention by 2026-10-19 (as designed); the next release first rehearses the newest completed backup (runbook 5 step 2) |
| Migration exit code, services replaced, scheduler state, result | First install: `MIGRATION_EXIT_CODE=0`, services started, `SCHEDULER=not-activated`, `STATUS=succeeded` (record `20261002T095601Z-20261002T085353Z-0db661289165.env`); scheduler activation: `MIGRATION_EXIT_CODE=0` (no-op), `SCHEDULER=active`, `STATUS=succeeded` |
| Initialization status counts, initialized backup ID and its restore evidence | After seed and bootstrap: `schema_version=15`, `active_default_metamodels=1`, 11/9/40/14 types, `users_including_deleted=1`, `active_admins=1`, `user_identities=0`, `auth_sessions=0`, `organisations=0`; backup `schatten-20261002T103929Z-manual-4395b2`; rehearsal 2026-10-02T10:52:13Z `STATUS=success` (27 tables, `users=1`, `metamodels=1`) |
| Tester role, time, smoke results | Main developer, 2026-10-02 (after step 11 and 14:45); items 1-3 pass; 2026-10-30: item 5 passes; item 4 not run in production, accepted risk ([8](#8-narrow-production-smoke-7)) |
| Prior stable tag and image IDs | None (first release) |
| Stable SemVer tag (created only after human acceptance) | `v0.1.0`, annotated (tag object `9131da8ac6be6e87d1798f8c6175ee3f84464b95`), on commit `0db6612891651b9d7e378885efaf084fa2c7c65a`; backend `sha256:6ac5da49ccd05f2969a569571f28283f804da15cef692d8993227abf90e13441`, frontend `sha256:0d8930318f36ba0e8f591da04d672aea7fb19e221fb042de4fbffd37bd84e192`. Created and pushed 2026-11-02 by the main developer after acceptance; listed on GitHub, and `origin` resolves it to the release commit |
| Acceptance by (role), date | Main developer, 2026-11-02 |

## 10. Failure And Deviation Log

| Time | Step | Observation (sanitized) | Action and approval | Outcome |
| --- | --- | --- | --- | --- |
| 2026-10-01 | 2.6 DNS | The `A` record for `schatten.lupaus.eu` already existed when F started; it was created outside this record | Operator (developer) approved 2.6 retroactively under CHG-10-01-2026-upcloud-deploy-schatten on 2026-10-01 | Closed |
| 2026-10-01 | 1.2 / 2.1 provider firewall | UpCloud provider firewall disabled with 0 rules; runbook 2.1 expects provider rules for TCP 22/80/443 only | UpCloud account holder decided to keep the provider defaults and rely on UFW; Docker-published ports are covered by the frontend-only 80/443 publication control. 2026-10-30: provider firewall enabled (2.1) | Closed |
| 2026-10-01 | 2.2 step 6 GitHub | The operator cannot create the `production` environment; DEPLOYMENT.md and ADR-013 require environment secrets limited to `main`. Repository secrets are readable by workflows on any branch pushed by a collaborator | Product owner decided to use repository secrets: the repository has only two collaborators (product owner, main developer) and no other projects. Compensating controls: upload key restricted to `upload-gate`; operator verifies workflow, event `workflow_dispatch`, branch `main` and commit on the run page and receives only the run summary's digest. Reassess before adding any collaborator ([12](#12-follow-up)). 2026-11-02: a `production` environment exists; the main developer takes as known that it is used only with `main` (the upload job runs only for `refs/heads/main`); its deployment-branch setting was not observed | Accepted deviation |
| 2026-10-01 | 2.2 step 6 `main` protection | No ruleset applies to `main` and its classic branch protection is not visible to the operator, so the push, force-push and deletion settings are not independently verified and whether administrators can bypass the protection is not known. ADR-013 rests source integrity on this protection, and the deploy secrets are repository-wide (row above) | The product owner (repository admin), who configured the settings, accepted them without independent verification on 2026-10-01 | Accepted deviation |
| 2026-10-01 | 2.2 step 6 clipboard | `xclip` was installed on the host by mistake | Operator removed `xclip` and the dependencies installed with it; no other host change | Closed |
| 2026-10-01 | 1.1 host key | Fingerprints compared over connections from different network paths instead of with the UpCloud console; all matched | Weaker than an out-of-band check (does not exclude interception next to the host); the product owner accepted the network-path comparison on 2026-10-30 | Accepted deviation |
| 2026-10-02 | 3 release approval | The only release approval, `CHG-10-01-2026-upcloud-deploy-schatten` (2026-10-01), precedes the CI check, build and freeze of 2026-10-02; runbook section 3 confirms CI and the local Entra evidence for the exact commit before approval and freezes the release after it. The product owner confirmed that the TASK-059B evidence covers the release's authentication scope ([3](#3-local-direct-entra-evidence-3-step-2)) on 2026-10-30, after the 2026-10-02 installation | The main developer accepted the change approval preceding the freeze and the scope confirmation following the deployment on 2026-11-02 | Accepted deviation |
| 2026-10-02 | 4 build resources | The running resources were not watched during the build (runbook section 3 step 8, `free -m`, `docker stats --no-stream`); only the build duration and the memory available before the build are recorded | No application ran yet and the build finished in 82 s without OOM or failure. Later builds run beside the live application: watch them and reassess the build location ([4](#4-delivery-receive-and-build-3)) | Closed |
| 2026-10-02 | 5 step 13 smoke item 5 | Smoke item 5 did not run with items 1-3 in section 4 step 13; it ran on 2026-10-30, four weeks after the first installation | Run on 2026-10-30 against the unchanged release `20261002T085353Z-0db661289165`: pass ([8](#8-narrow-production-smoke-7)) | Closed |
| 2026-10-03 | 5 step 14 | The next-day `$M status` check was not run on 2026-10-03; it ran on 2026-10-05 | Recorded on 2026-10-05: three scheduled backups present, Ofelia `failed: false` for the two runs in its 48-hour window | Closed |
| 2026-10-30 | 2.1 provider firewall | UpCloud's public firewall is stateless: replies to the host's own outgoing connections (DNS, Entra, Let's Encrypt, apt, image builds, NTP) arrive as incoming traffic, so runbook 2.1's "TCP 22, TCP 80/443, nothing else" with an incoming drop default would block them | Main developer, with the product owner's agreement, added DNS auto-add, reply, ICMP/ICMPv6 and DHCP/DHCPv6 rules (2.1); runbook 2.1 correction is a follow-up ([12](#12-follow-up)) | Accepted deviation |
| 2026-10-30 | 8 smoke 5 | After the prediction completed, `$M ps` ran in a shell where `M` was not set, so it printed the shell's own processes instead of the release's containers; the one-worker check is not verified | Rerun on 2026-10-30 with `S` and `M` set from the verified source copy (runbook "Always"): one `prediction-worker`, running and healthy (8) | Closed |
| 2026-10-30 | 8 smoke 4 | No designated tenant account without a matching Schatten User is available for production; the unmatched-account check passed locally only | Product owner accepted the risk on 2026-10-30: the generic failure, and that no User, identity or session is created, are not observed against production Entra and the production database | Accepted deviation |
| 2026-11-02 | 2.7 Entra cleanup | The remaining consumers of the Authentik callbacks and Graph `User.Read` were not checked and the cleanup was not performed; the unused Authentik redirect URIs and the `User.Read` permission stay on the shared registration | Main developer accepted deferring the consumer check and cleanup until after the rollout on 2026-11-02; the 2.7 authorization stays valid for it ([12](#12-follow-up)) | Accepted deviation |
| 2026-11-02 | 2.7 scopes and assignments | Not confirmed that the registration uses only `openid profile email` with no Graph calls and no `email_verified` requirement; the enterprise-app assignment count is not recorded | Main developer accepted deferring both until after the rollout on 2026-11-02 ([12](#12-follow-up)) | Accepted deviation |

First release has no earlier stable release and no rollback target. On
failure stop, keep the database and escalate for an approved forward fix. No
automatic down migrations, volume deletion, database reset or restoration;
production restoration needs separate authorization and impact review
(runbook section 6).

## 11. Acceptance

- [x] Ofelia and job-runner hardening verified before schedules were enabled,
      including weekly cleanup safeguards ([6](#6-scheduler-and-docker-control-boundary-9)).
      The Ofelia controls were verified by the activation gate itself: it
      starts Ofelia, runs `verify-runtime-hardening` and stops Ofelia on
      failure, before any scheduled job ran ([5](#5-first-installation-4)
      step 11).
- [x] Cloud-init baseline and effective access/firewall/service settings
      verified; only authorized changes, no reprovisioning
      ([1](#1-host-baseline-read-only-1), [2](#2-remaining-setup-2)).
      Except: `xclip` was installed on the host by mistake and removed the
      same day ([10](#10-failure-and-deviation-log)).
- [x] E's prerequisites and real local direct-Entra evidence complete;
      provider/host/tenant changes approved
      ([3](#3-local-direct-entra-evidence-3-step-2), [Authorizations](#authorizations)).
      The evidence scope was confirmed after the deployment, an accepted
      deviation ([10](#10-failure-and-deviation-log)).
- [x] Source delivered only through the Action and the upload account, accepted
      by `schatten-receive` with the run-summary digest; no deploy key,
      checkout or Git use ([4](#4-delivery-receive-and-build-3)). The `main`
      protection settings were stated as configured by the repository admin
      and are not independently verified, and whether administrators can
      bypass them is not known, an accepted deviation
      ([2.2](#22-operator-directory-upload-account-tools-github-22),
      [10](#10-failure-and-deviation-log)).
- [x] Ubuntu 26.04 LTS host, direct Caddy TLS and private PostgreSQL 18 without
      public backend/database exposure ([1](#1-host-baseline-read-only-1),
      [2.6](#26-dns-and-tls-26), [5](#5-first-installation-4)).
- [x] Shared registration callbacks, separate secrets, issuer/claims and
      consumer-checked cleanup verified without secrets or personal emails
      ([2.7](#27-entra-shared-registration-27)). Deferred as accepted
      deviations: the scopes/claims confirmation, the enterprise-app
      assignment count and the consumer check and cleanup
      ([10](#10-failure-and-deviation-log), [12](#12-follow-up)).
- [x] Frozen artifacts deployed without rebuild; migrations -> reference seed
      -> admin bootstrap succeeded with one healthy worker
      ([5](#5-first-installation-4)).
- [x] Release approval and narrow smoke recorded; schema-aware failure handling
      and first-release limitations explicit ([8](#8-narrow-production-smoke-7),
      [10](#10-failure-and-deviation-log)). Accepted deviations: the change
      approval preceded the freeze, and smoke item 4 was not run in
      production. Smoke item 5 ran on 2026-10-30
      ([10](#10-failure-and-deviation-log)).
- [x] Daily encrypted backups with 7-day retention active; pre-change and
      initialized-database backup IDs and successful isolated restore evidence
      recorded ([5](#5-first-installation-4), [7](#7-backups-8)).
- [x] Managed-service migration remains a separate follow-up; no prohibited
      database recovery/destruction occurred ([12](#12-follow-up)).

## 12. Follow-Up

| Item | Status |
| --- | --- |
| UpCloud Managed PostgreSQL migration (runbook section 12: data transfer, connection/TLS/advisory locks, cutover/rollback, backup capabilities, 7-day retention, restore verification) | Deferred; separate task not yet created |
| Off-server backup protection | Deferred; separately planned |
| Entra cleanup (2.7): check the remaining consumers of the Authentik callbacks and Graph `User.Read`, then remove only the unused configuration ([10](#10-failure-and-deviation-log)) | Deferred until after the rollout |
| Entra registration (2.7): confirm the scopes and claims (`openid profile email`, no Graph calls, no `email_verified` requirement) and record the enterprise-app assignment count ([10](#10-failure-and-deviation-log)) | Deferred until after the rollout |
| Runbook 2.1 provider firewall: list the rules a stateless UpCloud firewall needs (DNS auto-add, reply rules, ICMP/ICMPv6, DHCP, IPv6 copies), enabling last and the checks after enabling ([10](#10-failure-and-deviation-log)). Consider limiting the reply rules to the host's ephemeral destination port range so that the provider firewall becomes a second filter beside UFW (2.1) | Potential; not yet planned |
| GitHub secrets (2.2 step 6): reassess the repository-secrets deviation, and the `main` protection it relies on, before adding any collaborator ([10](#10-failure-and-deviation-log)) | Open; triggered by any new collaborator |
| Backup failure alerting: failed or missing scheduled backups (exit `1`/`2`, Ofelia `failed: true`) are visible only on the host through `$M status` and the Ofelia log, which `$M status` shows for 48 h ([7](#7-backups-8)); until then the operator checks `$M status` regularly | Potential; not yet planned |
