# TASK-059H1 Source Manifest, Verified Receive And Git-Free Build

## Source Plan

[TASK-059H](TASK-059H-github-source-delivery-architecture.md) and its approved
ADR-013 amendment. Depends on H being merged. The server must not use git:
delivered source is verified against a manifest instead of `git archive`.

## Goal

Replace the server-side git build input with a manifest-verified source copy:
a manifest generator that runs where git exists, a root-owned receiver that
verifies an uploaded folder and copies only the listed files into a
deploy-owned read-only source folder, and `build-release --source` that builds
from that folder. The frozen-release, image and release-gate contracts stay
otherwise unchanged.

## Requirements

- `.github/scripts/create-source-manifest.sh` (runner and QA only; uses git):
  export the exact commit (`git archive`) into an output folder and write
  `SOURCE_MANIFEST` with `SOURCE_COMMIT`, `SOURCE_REF`, `SOURCE_DATE_EPOCH`
  (commit time), `SOURCE_RUN_ID`, the file count and one line per tracked file
  with mode (`644`/`755`), SHA-256 and relative path, sorted. Refuse symlinks
  and submodules. Output must be byte-identical for the same commit and inputs.
  Print the manifest SHA-256.
- `deploy/bin/shadow-receive <manifest-sha256> [--upload <folder>]`
  (installed root-owned in `/usr/local/bin`; runs as `deploy`):
  - in this order: (1) copy only the manifest into deploy-owned staging
    `/opt/apps/shadow-sources/<commit>.incomplete`; (2) verify its SHA-256
    equals the operator-supplied digest; (3) parse it from those bytes and
    check its format, count and paths (relative only; no `..`, absolute paths
    or duplicate entries), `SOURCE_REF=refs/heads/main` and `SOURCE_COMMIT`
    equal to the upload folder name; (4) only then copy the listed files into
    staging, opening every upload path and parent without following symlinks
    and accepting only regular files; verify only the staged copy, never the
    upload folder in place;
  - verify every staged file's hash; ignore unlisted (stale) upload files;
    fail on any missing, changed, non-regular or symlinked file;
  - set modes from the manifest (not from the upload), make the tree read-only
    and rename it to `<commit>`; refuse to replace an existing commit folder;
    remove the staging folder on failure; print `SOURCE_DIR=`, `SOURCE_COMMIT=`
    and `SOURCE_MANIFEST_SHA256=`;
  - never execute, source or `make` anything from the upload folder; read it
    only as data; no git.
- `deploy/bin/build-release --source <verified folder>`: replace the commit
  argument and all `git` calls. Re-verify the folder against its manifest
  before building, copy it into the release `source/` as today, take
  `SOURCE_COMMIT`/`SOURCE_DATE_EPOCH` from the manifest, and record
  `SOURCE_MANIFEST_SHA256`, `SOURCE_REF` and `SOURCE_RUN_ID` in `release.env`;
  drop `GIT_VERSION`. Keep release-ID format, locks, secret checks, frozen
  image IDs and all downstream consumers (`deploy-release`, cleanup) working.
  Remove the git build path rather than keeping it as a fallback.
- `deploy/bin/check-host`: drop `git` from required tools; require
  `/opt/apps/shadow-sources` (created by `init-state`) and report whether
  `/usr/local/bin/shadow-receive` exists, is root-owned and not writable by
  others.
- `deploy/bin/audit-host`: remove `git` from required tools (presence is a
  fact only); replace the source-checkout remote check with the newest received
  commits and whether each has a manifest; report `shadow-receive` ownership.
- `deploy/bin/init-state`: create `/opt/apps/shadow-sources` (deploy-owned).

## Acceptance Criteria

- [ ] The manifest is deterministic, lists every tracked file with mode and
      hash, and refuses symlinks/submodules.
- [ ] `shadow-receive` accepts a matching upload and rejects a wrong digest,
      changed/missing file, symlinked file or parent, non-regular file,
      `..`/absolute path, duplicate entry, non-`main` ref, commit not matching
      the upload folder and an existing target; stale extra files are ignored;
      modes come from the manifest; a file changed in the upload folder after
      staging does not affect the accepted copy.
- [ ] `build-release --source` produces a release whose images, frozen source
      and `release.env` satisfy the existing deploy, rollback and cleanup gates.
- [ ] No server-side command calls git: the disposable harness runs the
      server-side steps with a `PATH` without git, and an Ubuntu 26.04
      container without git runs receive, build and `check-host`.
- [ ] `check-host`/`audit-host`/`init-state` reflect the git-free layout.

## Out Of Scope

- The GitHub workflow and upload account (H2); Makefile, `service` and runbook
  (H3); any host or GitHub change (F); building on GitHub.

## Implementation Notes

- Existing tooling: `deploy/lib/common.sh` (`release_dir`, locks,
  `compose_release`), `deploy/bin/build-release`, the disposable harness
  `.github/scripts/verify-production-runtime.sh`.
- The repository currently has 448 tracked files (about 4.4 MB), 24 executable,
  no symlinks or submodules; verification cost is negligible.
- Harness: replace `build-release <commit>` with manifest -> upload-style folder
  (with a stale extra file) -> `shadow-receive` -> `build-release --source`,
  and add the rejection cases above.

## Testing

Required:

- [ ] Integration tests: disposable runtime harness (Engine 28.5.2 default and
      `QA_DIND_IMAGE` Engine 29), including the git-free `PATH`.
- [ ] Manual verification: Ubuntu 26.04 container without git.
- [ ] Lint: shellcheck on new and changed scripts.

Not applicable:

- [x] Frontend/backend unit tests, typecheck, build: no application code changes.

```bash
.github/scripts/verify-production-runtime.sh
docker run --rm -v "$PWD:/mnt:ro" -w /mnt koalaman/shellcheck:stable --severity=warning <scripts>
```

## Documentation

- `docs/operations/testing.md` (harness build path, receive tests), `docs/architecture/deployment.md`
  command/storage tables and `release.env` fields, `.github/workflows/ci.yml`
  script and required-file checks. Runbook changes follow in H3.

Record eventual Step 13 reviews under `docs/ai-reviews/TASK-059H1/`.

## Included Fix: Review Record Task IDs

The AI-review record validator accepted only `TASK-XXX` and `TASK-XXXA`, so
`TASK-059H1` records failed validation. With developer approval this branch
also extends `scripts/ai_review_records.py` to accept `TASK-XXXA1`, adds a
validator test for accepted and rejected suffixes, and documents the form in
`docs/agents/ai-review-records.md`. H2 and H3 records use the same form.
