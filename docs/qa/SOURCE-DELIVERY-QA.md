# Git-Free Source Delivery QA (TASK-059H1)

This record holds TASK-059H1 evidence for the source manifest, the verified
receive (`schatten-receive`) and `build-release --source`
([ADR-013](../decisions/ADR-013-shared-entra-local-https-deployment.md#source-delivery-without-git-on-the-server)).
All runs used **disposable** local infrastructure and synthetic secrets. **No
production host, GitHub setting, secret, upload account, SSH/UFW rule or
provider was touched.** TASK-059H2 evidence for the upload gate and workflow
is in [its own section](#upload-gate-and-deploy-to-production-task-059h2); the
Makefile and runbook (H3) are not covered here.

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
folder not directly under `SCHATTEN_SOURCES_DIR`. The harness now checks that a
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
`schatten-upload` account (`0750`, group-readable by `deploy`). As root, the
container installed `schatten-receive` from the approved tree with
`install -o root -g root -m 0755`; all other steps ran as non-root `deploy`
in the socket group.

| Step | Result |
| --- | --- |
| `init-state` | Created `/opt/apps/schatten-sources` among the state directories |
| `check-host` | `PASSED`; tools `python3`, `flock`, `sha256sum`, `tar` (no Git); `/opt/apps/schatten-sources` writable; `/usr/local/bin/schatten-receive root-owned mode 755` |
| `schatten-receive <digest>` | Accepted into `/opt/apps/schatten-sources/57bf341f…`; the installed receiver's SHA-256 equals its manifest entry |
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
`ruff format` with the backend configuration passed on `schatten-receive`.

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
scp -tr /opt/apps/schatten-upload/EmwIdLYFsW.tar.gz
mkdir -p /opt/apps/schatten-upload/b05bd6bd53564f3d51689af481221ed61944a9e7
tar -zxf /opt/apps/schatten-upload/EmwIdLYFsW.tar.gz --strip-components 1 --overwrite -C /opt/apps/schatten-upload/b05bd6bd53564f3d51689af481221ed61944a9e7
rm -rf /opt/apps/schatten-upload/EmwIdLYFsW.tar.gz
```

| Check | Evidence |
| --- | --- |
| Upload through the gate | Delivered `SOURCE_MANIFEST` and files owned by `schatten-upload`, nothing accessible to others, archive removed; a repeated upload overwrote; the `drone-scp` the action downloaded has the recorded hash |
| Host key | The ECDSA host key's fingerprint succeeds; the Ed25519 fingerprint and a wrong fingerprint fail with `host key fingerprint mismatch` before any command (the Ed25519 case in an earlier run of the same test) |
| Receive | `schatten-receive <digest from the job summary>` as `deploy` accepted 463 files; `--verify` passes; `prepare-production-upload.sh` refused `refs/heads/feature` |
| Refused by the gate | Shell (pty denied by `restrict` with `-tt`), `id`, `sh -c id`, `ver`, `cat /etc/shadow`, `internal-sftp`, `scp -t`/`scp -f`, uploads to `/tmp`, into a commit folder or via `..`, `mkdir` of other paths, `;`, `&&`, `$(...)` and double spaces, `tar` into `/tmp`, other strip counts or other archives, removal of a commit folder, `SOURCE_MANIFEST`, the upload area or `/tmp` files, `rm -f`, and a two-path `rm -rf` |
| Refused by sshd/`restrict` | sftp, scp over SFTP and legacy scp (`-O`), `-W` stdio forwarding and `-R` remote forwarding |
| Crafted archives | `..` and absolute members did not escape; symlink and hardlink members and extraction into a folder with a planted symlink were refused; no file owned by `schatten-upload` outside the upload area |
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
