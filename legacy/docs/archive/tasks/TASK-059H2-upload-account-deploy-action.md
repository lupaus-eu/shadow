# TASK-059H2 Upload Account Gate And "Deploy To Production" Action

## Source Plan

[TASK-059H](TASK-059H-github-source-delivery-architecture.md) and its approved
ADR-013 amendment; depends on
[H1](TASK-059H1-source-manifest-git-free-build.md) for the manifest script.
The product owner requires the example workflow's shape: manual start,
checkout, SCP action with `overwrite: true`, GitHub secrets.

## Goal

Add the manually started GitHub workflow that delivers the exact `main` commit
and its manifest to the host, and the forced-command gate that limits the
upload account's key to writing files in its upload folder.

## Requirements

- `.github/workflows/deploy-production.yml`, name "Deploy to production":
  - `on: workflow_dispatch` only; refuse any ref other than `refs/heads/main`;
    `environment: production`; `permissions: contents: read`; one run at a time
    (`concurrency`);
  - `actions/checkout` with `persist-credentials: false`;
  - run `.github/scripts/create-source-manifest.sh` into `release-source/`;
  - copy with the SCP action from the example: the example names only a
    placeholder (`dummyname/scp-action`), so identify the real action in H2 (a
    candidate is `appleboy/scp-action`, whose `overwrite`, `strip_components`
    and `fingerprint` inputs match the example), pin it by full commit SHA and
    record its version; this new third-party action needs
    developer approval before use. Inputs: `host`, `username`, `key`, `port`
    and `fingerprint` from secrets `SSH_HOST`, `SSH_USER`, `SSH_KEY`,
    `SSH_PORT`, `SSH_FINGERPRINT`; `source: release-source`; target
    `/opt/apps/shadow-upload/${{ github.sha }}`; `overwrite: true`;
    `strip_components` set so files land directly in the target;
  - write the commit, run ID and manifest SHA-256 to the job summary; never
    print secrets.
- `deploy/bin/upload-gate` (installed root-owned in `/usr/local/bin`; forced
  command for the upload key via `restrict,command="/usr/local/bin/upload-gate"`):
  - allow only the exact remote commands the pinned SCP action issues (capture
    them from `SSH_ORIGINAL_COMMAND` in the disposable test rather than
    guessing), confined to `/opt/apps/shadow-upload/<40-hex>/` and the
    action's temporary file; refuse everything else with a nonzero exit and a
    short message;
  - no shell, no port/agent/X11 forwarding (from `restrict`), no writes outside
    the upload area, no `rm` beyond the action's own temporary file.
- The upload account itself is F setup: `shadow-upload`, locked password, no
  sudo, `docker` or `adm` membership and member of none of `deploy`'s groups,
  owner of `/opt/apps/shadow-upload` (`0750`, group: its own primary group,
  with `deploy` as supplementary member). Document the exact
  commands for F.

## Acceptance Criteria

- [ ] The workflow passes actionlint, is dispatch-only, main-only, least
      privilege, and uses the pinned SCP action with host-key fingerprint
      verification and no persisted checkout credentials.
- [ ] In a disposable Ubuntu 26.04 sshd container, the pinned action's upload
      (run from the action at the same commit) succeeds through `upload-gate`,
      and the key is refused for a shell, other commands, port forwarding,
      writes outside the upload area and deletion of other files.
- [ ] A delivered upload is accepted by H1's `shadow-receive` with the digest
      from the job summary.
- [ ] No GitHub environment, secret, host account or server change is made.

## Out Of Scope

- Creating the GitHub environment/secrets, the upload account, SSH/UFW changes
  and the first real workflow run (F). GitHub only offers a manual run once the
  workflow is on `main`.
- Building images on GitHub or GHCR.

## Implementation Notes

- The example's `rm` option is not used; stale files from earlier uploads are
  ignored by the manifest-based receive (H1).
- `overwrite: true` makes the remote tar extraction replace existing files; it
  does not delete files removed from the repository.

## Testing

Required:

- [ ] Integration tests: disposable sshd container test of the pinned action
      through `upload-gate`, followed by `shadow-receive`.
- [ ] Lint: actionlint (Docker image, not a project dependency) and shellcheck.

Not applicable:

- [x] Frontend/backend tests, typecheck, build: no application code changes.

## Documentation

- `docs/operations/testing.md` (upload-gate and workflow checks), `docs/architecture/deployment.md`
  (workflow, secrets, upload area), `.github/workflows/ci.yml` (lint and
  required files). Runbook setup steps follow in H3.

Record eventual Step 13 reviews under `docs/ai-reviews/TASK-059H2/`.

## Implementation Record

- Developer approval (2026-09-29): `appleboy/scp-action` v1.0.0, pinned as
  `ff85246acaad7bdce478db94a363cd2bf7c90345`, with a hash check of the
  `drone-scp` 1.8.0 linux-amd64 binary it downloads at run time
  (`05bed7f47f57fffadfa9c3e53ef5b203cb66b1bc83751e261246584c59ed7649`, equal to
  the release's `checksums.txt`). The release is not immutable, so the workflow
  verifies the binary before the upload and hands that file to the action via
  `DRONE_SCP_RELEASE_URL=file://...` (review-001 F-001); the step after the
  upload confirms it was used.
- `upload-gate` serializes its commands with a non-blocking lock on the upload
  area, so its archive and folder checks cannot race with a parallel session
  (review-001 F-002; the missing serialization was reproduced in the disposable
  test against the earlier gate). `scp` and `tar` run under
  `timeout --kill-after=10s 10m`, so a session kept open cannot hold the lock
  for longer (review-002 F-001); a per-account sshd limit is left to H3/F as an
  optional extra layer.
- `tar_tmp_path: /opt/apps/shadow-upload/` keeps the action's temporary
  archive inside the upload area; `shadow-receive` ignores it (not a commit
  name).
- `SSH_FINGERPRINT` is the host's ECDSA key fingerprint: drone-scp's Go SSH
  client prefers ECDSA P-256 over Ed25519.
- Evidence: [SOURCE-DELIVERY-QA.md](../../operations/qa/SOURCE-DELIVERY-QA.md#upload-gate-and-deploy-to-production-task-059h2).
