# Git-Free Source Delivery QA (TASK-059H1-H3)

This record holds TASK-059H1 evidence for the source manifest, the verified
receive (`shadow-receive`) and `build-release --source`
([ADR-013](../../adr/0013-shared-entra-local-https-deployment.md#source-delivery-without-git-on-the-server)).
All runs used **disposable** local infrastructure and synthetic secrets. **No
production host, GitHub setting, secret, upload account, SSH/UFW rule or
provider was touched.** TASK-059H2 evidence for the upload gate and workflow
is in [its own section](#upload-gate-and-deploy-to-production-task-059h2), and
TASK-059H3 evidence for the server Makefile, the `service` command, the host
audit and the runbook in
[its section](#server-makefile-service-command-and-runbook-task-059h3), and
TASK-059J evidence for operator SSH from any address in
[the last section](#deploy-and-root-ssh-from-any-address-task-059j).

## Environment

| Item | Value |
| --- | --- |
| Date | 2026-09-29 |
| Base | `main` at `c6a78fb2c4bf` plus the TASK-059H1 working tree, committed only in a scratch clone as `57bf341fe451` (not a repository commit); its `deploy/` and `.github/` trees were identical to the reviewed working tree |
| Run A | Workstation Ubuntu 24.04 userland, isolated daemon `docker:28.5.2-dind@sha256:2a232a42…` (harness default) |
| Run B | Same workstation, `QA_DIND_IMAGE=docker:29.8.1-dind@sha256:3f3c01aa…` |
| Run C | `ubuntu:26.04` (26.04.1) container **without Git** (`command -v git` fails, no `/usr/bin/git*`): uutils coreutils 0.8.0, GNU tar 1.35, Python 3.14.4, Docker CLI 29.8.1, Compose 5.5.1 and Buildx 0.37.1 from Docker's `resolute` APT repository; isolated daemon `docker:29.8.1-dind@sha256:3f3c01aa…` |

## Disposable Runtime Harness (Runs A And B)

```bash
QA_LOG_FILE=<file> .github/scripts/verify-production-runtime.sh
QA_DIND_IMAGE=docker.io/library/docker:29.8.1-dind@sha256:3f3c01aaaebf7cce837356b688b7c059a4749f10bd7660dec7c58fc454a283f0 \
  QA_LOG_FILE=<file> .github/scripts/verify-production-runtime.sh
```

Result: **pass in both runs** (`EXIT=0`, 66 `PASS` lines each). The G/E checks
all passed unchanged on the release built through the new path, including
first install, restore gates, cleanup protection of current/previous images,
fix-forward and the schema-compatible rollback.

| Check | Evidence (both runs) |
| --- | --- |
| Manifest | 460 tracked files with Git modes and SHA-256; a second export gave a byte-identical manifest and the same printed digest; `SOURCE_DATE_EPOCH` equals the commit time; scratch repositories with a symlink and a submodule were refused |
| Git-free server side | `PATH` replaced by a symlink farm without `git`/`git-*`; `command -v git` failed; `check-host`, `init-state`, receive, build and all later steps ran with it |
| Receive rejections | Wrong digest; unknown digest (no matching upload); changed, missing, symlinked and FIFO file; symlinked parent; symlinked upload folder; `..` and absolute paths; duplicate entry; `refs/heads/feature`; commit not equal to the folder name. The sources folder stayed empty after every rejection |
| Receive acceptance | Default discovery by digest; stale file and stale directory not copied; `docker-compose.production.yml` uploaded as `0755` accepted as `0444`, `deploy/bin/build-release` uploaded as `0644` accepted as `0555`; no writable entry; a later change in the upload folder left the accepted copy's hash unchanged and `--verify` passing; a second receive was refused (`already exists`) |
| `build-release` | The old commit argument and an unverified (writable, changed) folder were refused without leaving a work directory; `release.env` records `SOURCE_COMMIT`, `SOURCE_DATE_EPOCH`, `SOURCE_REF=refs/heads/main`, `SOURCE_RUN_ID=1059` and `SOURCE_MANIFEST_SHA256`, and no `GIT_VERSION`; the frozen release source re-verifies against its manifest |

### Review F-001 Re-Run (Run A Only)

After AI review `TASK-059H1/review-001` F-001, `build-release` refuses any
folder not directly under `SHADOW_SOURCES_DIR`. The harness now checks that a
self-consistent read-only copy outside the sources directory passes
`--verify` on its own but is refused by `build-release`, and runs the
unverified-folder case from inside the sources directory. Run A was repeated
from a scratch-clone commit `58af9856b2b8` (this branch with the F-001
fix applied): **pass** (`EXIT=0`, 67 `PASS` lines). Run B and Run C were not repeated;
the change touches only `build-release` argument checking before any build.

One harness portability issue was found and fixed during QA: a pyenv
`python3` shim became very slow with the farm `PATH`, so the harness links
`python3` to the real interpreter. Hosts and CI use `/usr/bin/python3`.

## Ubuntu 26.04 Without Git (Run C)

The manifest was created on the workstation (Git allowed there) with a stale
file added, then copied into the container as an upload owned by a separate
`shadow-upload` account (`0750`, group-readable by `deploy`). As root, the
container installed `shadow-receive` from the approved tree with
`install -o root -g root -m 0755`; all other steps ran as non-root `deploy`
in the socket group.

| Step | Result |
| --- | --- |
| `init-state` | Created `/opt/apps/shadow-sources` among the state directories |
| `check-host` | `PASSED`; tools `python3`, `flock`, `sha256sum`, `tar` (no Git); `/opt/apps/shadow-sources` writable; `/usr/local/bin/shadow-receive root-owned mode 755` |
| `shadow-receive <digest>` | Accepted into `/opt/apps/shadow-sources/57bf341f…`; the installed receiver's SHA-256 equals its manifest entry |
| `build-release --source` (from the verified copy) | Frozen release `20260929T101401Z-57bf341fe451` with `sha256:` image IDs, `SOURCE_REF`, `SOURCE_RUN_ID=2059`, `SOURCE_MANIFEST_SHA256`, Engine 29.8.1 and no `GIT_VERSION`; the frozen source verifies |
| `check-host` (from the verified copy) | `PASSED` |
| `audit-host` | `git absent (not needed)`; the receiver `ok`, with owner, mode and hash; one received commit with `manifest=present` and its digest |

Separately, in a fresh container, `audit-host` reported attention for a
group-writable receiver (`0775`), a received folder without `SOURCE_MANIFEST`,
leftover `<commit>.incomplete` staging and an unexpected entry.

## Static Checks

`shellcheck --severity=warning` (koalaman/shellcheck:stable) passed on
`create-source-manifest.sh`, `verify-production-runtime.sh`, `build-release`,
`check-host`, `init-state`, `audit-host` and `common.sh`. `ruff check` and
`ruff format` with the backend configuration passed on `shadow-receive`.

## Not Covered

- Real GitHub runs; the host installation and first real receive (F). The
  H2 sshd container test is recorded below.
- A file changed *during* a receive, between staging copy and verification:
  the design verifies only the staged copy, and the post-acceptance change
  above shows the upload is not read again. Because the manifest has no file
  sizes, a file that keeps growing while it is copied is caught only by the
  hash check after the copy.

## Upload Gate And Deploy To Production (TASK-059H2)

Disposable run of `.github/scripts/verify-upload-gate.sh` on 2026-09-29. Only
a throwaway container, a temporary folder and synthetic keys were used; **no
GitHub environment, secret, host account or server was touched**, and the
workflow has not run on GitHub.

| Item | Value |
| --- | --- |
| Tree | TASK-059H2 working tree on `main` at `b05bd6bd5356`; the uploaded source is that commit (463 files) |
| sshd host | `ubuntu:26.04@sha256:da6fc2be…` (26.04.1), OpenSSH 10.2p1 (Ubuntu-2ubuntu3.6), GNU tar 1.35; `restrict,command="/usr/local/bin/upload-gate"` in a root-owned `authorized_keys`, public-key only |
| Client | `appleboy/scp-action` `entrypoint.sh` at `ff85246acaad7bdce478db94a363cd2bf7c90345` (v1.0.0) with the workflow step's inputs, running `drone-scp` 1.8.0 (SHA-256 `05bed7f4…c59ed7649`) on an x86_64 workstation |
| Result | **pass** (`EXIT=0`, 12 `PASS` lines) |

Remote commands captured from `SSH_ORIGINAL_COMMAND` through a recording
forced command (archive name random per run):

```text
ver
scp -tr /opt/apps/shadow-upload/EmwIdLYFsW.tar.gz
mkdir -p /opt/apps/shadow-upload/b05bd6bd53564f3d51689af481221ed61944a9e7
tar -zxf /opt/apps/shadow-upload/EmwIdLYFsW.tar.gz --strip-components 1 --overwrite -C /opt/apps/shadow-upload/b05bd6bd53564f3d51689af481221ed61944a9e7
rm -rf /opt/apps/shadow-upload/EmwIdLYFsW.tar.gz
```

| Check | Evidence |
| --- | --- |
| Upload through the gate | Delivered `SOURCE_MANIFEST` and files owned by `shadow-upload`, nothing accessible to others, archive removed; a repeated upload overwrote; the `drone-scp` the action downloaded has the recorded hash |
| Host key | The ECDSA host key's fingerprint succeeds; the Ed25519 fingerprint and a wrong fingerprint fail with `host key fingerprint mismatch` before any command (the Ed25519 case in an earlier run of the same test) |
| Receive | `shadow-receive <digest from the job summary>` as `deploy` accepted 463 files; `--verify` passes; `prepare-production-upload.sh` refused `refs/heads/feature` |
| Refused by the gate | Shell (pty denied by `restrict` with `-tt`), `id`, `sh -c id`, `ver`, `cat /etc/shadow`, `internal-sftp`, `scp -t`/`scp -f`, uploads to `/tmp`, into a commit folder or via `..`, `mkdir` of other paths, `;`, `&&`, `$(...)` and double spaces, `tar` into `/tmp`, other strip counts or other archives, removal of a commit folder, `SOURCE_MANIFEST`, the upload area or `/tmp` files, `rm -f`, and a two-path `rm -rf` |
| Refused by sshd/`restrict` | sftp, scp over SFTP and legacy scp (`-O`), `-W` stdio forwarding and `-R` remote forwarding |
| Crafted archives | `..` and absolute members did not escape; symlink and hardlink members and extraction into a folder with a planted symlink were refused; no file owned by `shadow-upload` outside the upload area |
| Mutation check | With the gate's member-type check disabled, the test failed (`symlink archive not refused by upload-gate`) |

`actionlint` 1.7.9 (Docker image) passed on `deploy-production.yml`;
`shellcheck --severity=warning` passed on `upload-gate`,
`prepare-production-upload.sh` and `verify-upload-gate.sh`. Agent forwarding
has no observable effect without a shell and is covered only by `restrict`.

### Rerun After Review-001 Fixes (TASK-059H2)

Disposable rerun of `.github/scripts/verify-upload-gate.sh` on 2026-09-29
after the fixes for `docs/ai-reviews/TASK-059H2/review-001.json`, with the
same host image, OpenSSH, GNU tar, pinned action and `drone-scp` hash as above.
The uploaded source was the branch commit `a394c348e6ad` (468 files). Again, no
GitHub environment, secret, host account or server was touched.

| Check | Evidence |
| --- | --- |
| F-001 reproduction precondition | At the pinned commit, `entrypoint.sh` always runs curl to `<DRONE_SCP_RELEASE_URL>/v<version>/<binary>` and then runs that binary with the key inputs, so a check of a separate download does not bind what runs |
| F-001 fix | The action logged its copy `from file://<verified folder>` instead of GitHub, and the binary it ran has the recorded SHA-256 |
| F-002 reproduction | With the earlier gate (`HEAD` version) and the new serialization check, the test **failed**: a parallel `rm -rf` of an archive name was accepted while another gate `scp` session was still running, so a checked archive could be replaced before its extraction. A full archive swap was not attempted |
| F-002 fix | With the lock, a parallel `rm -rf`, `scp -tr` and `mkdir -p` are refused with `another upload-gate command is running`; after the held session ends, the gate accepts commands again and no archive is left |
| Result | **pass** (`EXIT=0`, 14 `PASS` lines); all earlier checks still pass |

`actionlint` 1.7.9 (Docker image) passed on `deploy-production.yml`;
`shellcheck --severity=warning` (Docker image `koalaman/shellcheck:stable`)
passed on `upload-gate`, `prepare-production-upload.sh` and
`verify-upload-gate.sh`.

### Rerun After Review-002 (TASK-059H2)

Disposable rerun of `.github/scripts/verify-upload-gate.sh` on 2026-09-29
after adding the gate's `timeout --kill-after=10s 10m` around `scp` and `tar`
(`docs/ai-reviews/TASK-059H2/review-002.json` F-001), with the same image,
action, `drone-scp` hash and synthetic keys. No GitHub environment, secret,
host account or server was touched.

| Check | Evidence |
| --- | --- |
| Upload through the gate | The action's upload, repeat (overwrite) and receive still pass with `scp` and `tar` under `timeout` |
| Held session | While an `scp` sink was held open (stdin kept open), a parallel `rm -rf`, `scp -tr` and `mkdir -p` were refused as busy; the held `scp` ran as `timeout --kill-after=10s 10m scp -t -- <archive>` |
| Expiry | `SIGALRM` to that `timeout` (its own expiry path) ended the session with exit 124, left no archive, and the gate accepted the next command |
| Result | **pass** (`EXIT=0`, 14 `PASS` lines); `shellcheck --severity=warning` and `actionlint` 1.7.9 pass |

## Server Makefile, Service Command And Runbook (TASK-059H3)

Disposable runs on 2026-09-29. Only isolated Docker daemons, throwaway
containers, temporary folders, synthetic secrets and synthetic keys were used;
**no production host, GitHub environment, secret, upload account, SSH/UFW rule
or provider was touched**, and the Action has not run on GitHub.

### Disposable Runtime Harness Through The Makefile

The TASK-059H3 working tree was committed only in a scratch clone as
`a4453ae484d0` (`main` at `472a6f1f` plus this branch's changes; not a
repository commit) and the harness ran from that clone, so the uploaded,
received and built source is that tree.

| Run | Daemon | Result |
| --- | --- | --- |
| A | `docker:28.5.2-dind@sha256:2a232a42…` (harness default) | **pass** (`EXIT=0`, 82 `PASS` lines) |
| B | `QA_DIND_IMAGE=docker:29.8.1-dind@sha256:3f3c01aa…` | **pass** (`EXIT=0`, 82 `PASS` lines) |

| Check | Evidence (both runs) |
| --- | --- |
| Git-free `PATH` | `make` and every server-side step ran with `command -v git` failing |
| Makefile shape | Exactly the targets `help check audit build deploy first-install status ps logs stop start backup restore cleanup-dry-run`; the nine wrapped commands (`check-host`, `audit-host`, `build-release`, `deploy-release`, `ops-status`, `service`, `backup-now`, `restore-rehearsal`, `docker-cleanup`) exist in the verified copy; no recipe runs `down`, prune, volume removal, `--apply`, rollback, initialization or the receiver |
| Required variables | `deploy`/`first-install` without `RELEASE` or `APPROVAL` and `restore` without `BACKUP` or `KEY` stop with `... is required` and a usage line (exit 2); a release ID of another commit is refused (`was not built from this source copy`) |
| Injection | `SERVICE='backend; touch /tmp/pwned'` is refused as an unknown service; values reach the commands through the environment |
| `make check` | Off Ubuntu 26.04 it stops only at the OS check |
| `make build` | Built the first frozen release from the read-only verified copy; the recorded commit, manifest digest, ref, run ID and image IDs match as before |
| `make first-install`, `make deploy` | First install of release one; release two deployed through `make deploy` after the restore-evidence gate; the existing gate, rollback (direct command) and fix-forward checks passed unchanged |
| `make backup`, `make restore`, `make status` | Encrypted backup `0600`; passphrase-key restore with the initialized admin/reference rows; status lists the backup and `STATUS=success` |
| `make ps`, `make logs` | `ps` names the current release and lists database, migration, API, worker and frontend; `logs` shows each service, `SERVICE=backend` only the API; no `POSTGRES_PASSWORD=`, `DATABASE_URL=` or `OIDC_CLIENT_SECRET=` in the output |
| `make stop` / `make start` | Stop left no service running, with the same container IDs and volumes, recorded `database backend prediction-worker frontend`, and refused a second stop; start brought the same containers back healthy, HTTPS `/health` returned `OK`, the migration container's start time was unchanged, the record was removed and a start without a record was refused |
| With the scheduler | After `--enable-scheduler`, stop recorded and stopped Ofelia too and start restarted it |
| Secret scan | The synthetic secrets were absent from the QA log (which includes all make output), container logs and image history |

One defect was found by the harness and fixed before these runs: `service logs
<unknown>` checked for a current release before validating its argument; the
arguments are now checked first.

### Rerun After Review-001 Fixes (TASK-059H3)

Disposable reruns on 2026-09-30 after the fixes for
`docs/ai-reviews/TASK-059H3/review-001.json`. As above, the working tree was
committed only in a scratch clone as `0a950cab7b75` (the branch commit
`08814c6841f9` plus the fixes; not a repository commit). No production host,
GitHub environment, secret or provider was touched.

| Check | Evidence (both runs) |
| --- | --- |
| F-001 fix | While `make stop` has services recorded, `make deploy` and a direct `deploy-release --rollback --confirm-schema-compatible` are refused with `Services are stopped by service stop`. Nothing is started, `current` is unchanged and no deployment record is written. After `make start`, the later release-two deployment, rollback and scheduler checks pass unchanged. The refusal happens under the release lock, which `service stop` also holds. The earlier behavior was found by code analysis and was not reproduced against the old `deploy-release` |
| F-002 fix | While stopped, `make status` lists `stopped by service stop` with the recorded release and `SERVICES=database backend prediction-worker frontend`; after `make start` the section is gone |
| F-003 fix | `make restore` refuses a relative `KEY=` (`KEY must be an absolute path`) and a relative `PASSPHRASE=`; the absolute-path restore rehearsal still passes |
| Run A, `docker:28.5.2-dind` (harness default) | **pass** (`EXIT=0`, 86 `PASS` lines: the earlier 82 plus the four new refusal cases) |
| Run B, `QA_DIND_IMAGE=docker:29.8.1-dind@sha256:3f3c01aa…` | **pass** (`EXIT=0`, 86 `PASS` lines) |
| Secret scan | The synthetic secrets were absent from both QA logs, container logs and image history |

`shellcheck --severity=warning` (koalaman/shellcheck:stable) passed on
`service`, `deploy-release`, `ops-status`, `audit-host`, `check-host` and
`verify-production-runtime.sh`. `audit-host` was not changed, so the host
audit below was not rerun.

### Host Audit And SSH Setup (Ubuntu 26.04 Container)

`ubuntu:26.04@sha256:da6fc2be…` without Git, OpenSSH 10.2p1, sudo-rs, set up
like the reported baseline (locked `deploy` with a key and NOPASSWD sudo, the
image's `ubuntu` user, a root key, the cloud-init `PasswordAuthentication no`
drop-in, UFW with OpenSSH/80/443 from `Anywhere`, a fail2ban `sshd` jail
5/600/3600, `Europe/Helsinki`, root-owned `/opt` directories, no `make`). The
repository was mounted read-only; `make audit` ran from a read-only copy under
a 40-hex commit name.

| Stage | Result |
| --- | --- |
| Baseline, `audit-host` as `deploy` directly and through `bash -s` | Identical findings, exit 0. Attention: `tool make is not installed`, root SSH not disabled (`prohibit-password`), `AllowUsers is not set`, SSH from `Anywhere` while root login is enabled, root-owned `/opt/apps`, backup directory `0:0 755`. Facts: `git absent (not needed)`, upload account, upload folder, `upload-gate` and `shadow-receive` absent |
| Runbook 2.1 drop-in | `sshd -t` silent; `sshd -T` showed `permitrootlogin no`, `passwordauthentication no`, `kbdinteractiveauthentication no`, `allowusers deploy@127.0.0.1/32` and `allowusers shadow-upload` |
| Optional `Match User shadow-upload` block | `sshd -t` valid; `sshd -T -C user=shadow-upload,...` showed `channeltimeout session=15m`, `deploy` showed `none`; removed again |
| SSH access after reload (`SIGHUP` in place of `systemctl reload`) | `deploy` from inside the CIDR accepted; root and password/keyboard-interactive refused (`Permission denied (publickey)`); the upload key reached only the gate (`refused: interactive login is not allowed`, `refused: command not allowed` for `id`); with `deploy@192.0.2.0/24` the same `deploy` login was refused |
| Runbook 2.2 | GNU Make 4.4.1 installed; `/opt/apps` changed non-recursively; account, root-owned home/`.ssh`/`authorized_keys` with `restrict,command=`, `0750` upload folder, both tools installed with `install -o root -g root -m 0755` and hash-equal to the source; `ssh-keygen -lf /etc/ssh/ssh_host_ecdsa_key.pub` printed a `SHA256:` value of type `(ECDSA)` |
| `make audit` after 2.1/2.2 | Only container artefacts remain (cloud-init, no Docker daemon, host sysctl). `ok`: `tool make`, `deploy is source-restricted by AllowUsers (1 pattern(s))`, `AllowUsers admits shadow-upload`, upload password locked, only its own group, no sudo rules, `deploy` in its group, root-owned home/`.ssh`/key file, every key with `restrict` and the gate, upload folder `750`, both tools root-owned; fact: SSH from `Anywhere` accepted as public-key only |
| Negative variants | Attention for `AllowUsers deploy shadow-upload ubuntu` (bare `deploy`, extra account, no source-restricted `deploy`), the upload account in `docker`, a second key without the forced command (`1 of 2`), a `0775` gate, a `0770` upload folder; with password login re-enabled, SSH from `Anywhere` became attention again |
| Sanitization | Neither public key's material appeared in any audit output |

`shellcheck --severity=warning` (koalaman/shellcheck:stable) passed on
`service`, `audit-host`, `check-host` and `verify-production-runtime.sh`. The
relative links and anchors of the changed documents resolve. The historical
records `UPCLOUD-RUNBOOK-QA.md` and `PRODUCTION-RUNTIME-QA.md` are unchanged.

### Not Covered

- `systemctl reload ssh.service`, the real UFW and UpCloud firewall rules,
  lockout safety and fresh sessions from the real operator network (F).
- The workstation copy of the real approved commit, the GitHub `production`
  environment and secrets, the first real Action run with its run page checks
  and `file://` log line, and the first real receive and tool hash comparison
  (F).
- `make check` and `make audit` against a real Ubuntu 26.04 host with Docker;
  `check-host` passing on Ubuntu 26.04 without Git is recorded in Run C above.

## Deploy And Root SSH From Any Address (TASK-059J)

Disposable run on 2026-10-01 for the
[ADR-013 amendment](../../adr/0013-shared-entra-local-https-deployment.md#operator-ssh-access-from-any-address).
Only a throwaway container, a throwaway Docker network and synthetic keys were
used; **no production host, GitHub setting, UpCloud resource, SSH/UFW rule or
provider was touched.**

Host: `ubuntu:26.04@sha256:da6fc2be…` (Ubuntu 26.04.1 LTS), OpenSSH 10.2p1,
sudo-rs, set up like the observed host: locked `deploy` with one key and
NOPASSWD sudo, the image's `ubuntu` user, locked root with one key without the
cloud-init `disable_root` prefix, the cloud-init `PasswordAuthentication no`
drop-in and `PermitRootLogin yes` appended to the main `sshd_config`. A stub
`ufw` printed `22/tcp (OpenSSH) ALLOW IN Anywhere` and 80/443, because UFW
cannot run in the container. `audit-host` ran as `deploy` through `bash -s`.
Logins came from a second container on the network (an address in no former
operator CIDR).

| Stage | Result |
| --- | --- |
| Baseline audit | `permitrootlogin=yes` attention (`root SSH is not key-only`), `AllowUsers is not set` attention, password and keyboard-interactive `ok`; facts `account root ... password=L authorized_keys=1` and `0 of 1` `disable_root`-prefixed keys |
| Amended 2.1 drop-in | `sshd -t` silent; `sshd -T` and `sshd -T -C user=root,host=workstation,addr=203.0.113.9` showed `permitrootlogin prohibit-password`, `passwordauthentication no`, `kbdinteractiveauthentication no`, `allowusers deploy`, `allowusers root`, `allowusers shadow-upload`: the `10-` drop-in overrides the main file's `yes` |
| Audit after 2.1 | `ok`: `root SSH is key-only`, password and keyboard-interactive disabled, `AllowUsers admits deploy from any address`, `... root from any address`, `AllowUsers admits shadow-upload`; facts: main-file `PermitRootLogin yes` overridden, SSH from `Anywhere` accepted |
| Logins | `deploy` and root with their keys accepted; password/keyboard-interactive as `deploy` and root refused with `Permission denied (publickey)`; `ubuntu` with the `deploy` key refused |
| Stricter variants | `deploy@198.51.100.0/24 root@198.51.100.0/24` reported as `admits ... only from 1 address pattern(s)` facts; `PermitRootLogin no` with no `root` entry reported as facts (root disabled, shut out); SSH from `Anywhere` stayed accepted |
| Negative variants | `AllowUsers root shadow-upload ubuntu`: attention for the extra account and for no `deploy` entry; no `PermitRootLogin` in the drop-in (main-file `yes` effective): attention for root and for SSH from `Anywhere`; `PasswordAuthentication yes` in the drop-in: attention for password authentication and SSH from `Anywhere` |
| Sanitization | No key material, key comment or fingerprint appeared in any audit output |

`shellcheck --severity=warning` (koalaman/shellcheck:stable) passed on
`audit-host`. The relative links and anchors of the changed documents resolve.

### Not Covered (TASK-059J)

- `systemctl reload ssh.service`, the real host's drop-in order, the real UFW
  and UpCloud firewall rules and fresh sessions from the operators' networks
  (F).
- UpCloud's disk-move password reset, web console and storage snapshot; they
  need the UpCloud account and are documented, not exercised.
- A root key login by the real root key holder (optional in F).
