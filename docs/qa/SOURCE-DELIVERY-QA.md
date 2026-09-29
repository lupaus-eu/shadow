# Git-Free Source Delivery QA (TASK-059H1)

This record holds TASK-059H1 evidence for the source manifest, the verified
receive (`schatten-receive`) and `build-release --source`
([ADR-013](../decisions/ADR-013-shared-entra-local-https-deployment.md#source-delivery-without-git-on-the-server)).
All runs used **disposable** local infrastructure and synthetic secrets. **No
production host, GitHub setting, secret, upload account, SSH/UFW rule or
provider was touched.** The upload gate and workflow (H2) and the Makefile and
runbook (H3) are not covered here.

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

- Real GitHub runs, the SCP upload through `upload-gate` and the H2 sshd
  container test (H2); the host installation and first real receive (F).
- A file changed *during* a receive, between staging copy and verification:
  the design verifies only the staged copy, and the post-acceptance change
  above shows the upload is not read again. Because the manifest has no file
  sizes, a file that keeps growing while it is copied is caught only by the
  hash check after the copy.
