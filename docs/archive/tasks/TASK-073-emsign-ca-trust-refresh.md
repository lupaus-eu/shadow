# TASK-073 emSign CA Trust Refresh

## Source Plan

A security advisory pasted into the developer chat on 2026-10-27: eMudhra
intermediate CAs had weak keys, so the emSign root was removed from CA bundles
(Chrome removed emSign ECC Root CA - G3 on 2026-10-27; Mozilla stopped trusting
it on 2026-10-20). The advisory asks for upgrades to at least certifi
2026.10.19, uv 0.13.4 and pip 26.2.2, and for images to be rebuilt without the
layer cache.

The impact check on `main` (84ca37d):

| Item | Where | Version | Status |
|---|---|---|---|
| certifi (httpx/httpcore, sentry-sdk, fastmcp; Entra OIDC calls) | `backend/uv.lock` | 2026.10.23 | Already fixed |
| uv in the backend image (`uv sync` fetches from pypi.org during builds) | `backend/Dockerfile:3` | 0.11.24 | **Affected** |
| uv in CI | `.github/workflows/ci.yml` `setup-uv@v7`, no version pin | latest | Probably fine, not reproducible |
| pip in `python:3.12-slim` | backend image | old | Not used (uv installs everything) |
| System CA store | digest-pinned `python:3.12-slim`, `node:22-bookworm-slim`, `caddy:2.11.4-alpine` | old digests | Stale, low risk |
| sigstore, conda, pixi, virtualenv | — | — | Not used |

The task also covers the Node.js security releases of 2026-10-21
(<https://nodejs.org/en/blog/vulnerability/october-2026-security-releases>,
reported in <https://cybersecuritynews.com/node-js-releases-security-updates/>).
They fix 4 high, 3 medium and 3 low severity issues, including TLS
hostname-verification bypasses, an out-of-bounds write in the Brotli decoder,
and `dns.resolve` NUL truncation. The fixed versions are 22.23.4, 24.22.1 and
26.12.1.

| Item | Where | Version | Status |
|---|---|---|---|
| Node in the frontend build stages (`pnpm install`, `pnpm build`) | `frontend/Dockerfile:1` `node:22-bookworm-slim@sha256:43ac…` | 22.23.3 | **Affected** (build time only) |
| Node in the production runtime | — | — | Not used; Caddy serves the static `dist` |
| Node in CI | `.github/workflows/ci.yml` `setup-node`, `node-version: 22` | newest 22.x | Probably fine |
| Node on the developer workstation | local | 24.18.0 | **Affected** |

## Goal

Make sure production images build with a uv that no longer trusts the emSign
root, that the frontend build runs on a Node with the October 2026 security
fixes, and that their system CA stores are current. Then roll the rebuilt
images out to the UpCloud host through the normal release flow.

## Requirements

- `backend/Dockerfile`: set `ghcr.io/astral-sh/uv` to >= 0.13.4 and pin its new
  `@sha256` digest.
- Refresh the digest pins of `python:3.12-slim` (`backend/Dockerfile`) and
  `node:22-bookworm-slim` (`frontend/Dockerfile`) to the current upstream
  digests, without changing the tags.
- Caddy: pin `caddy:2.11.7-alpine` by digest in `frontend/Dockerfile` and in
  the local proxy in `docker-compose.yml`. The `caddy:2.11.4-alpine` tag has
  not been rebuilt since 2026-09-17 and still ships Alpine
  `ca-certificates 20260909-r0`, which trusts emSign ECC Root CA - G3;
  `caddy:2.11.7-alpine` (2026-10-21, Alpine 3.23.7) ships `20261020-r0`.
  The developer chose this patch upgrade on 2026-11-02 instead of an unpinned
  `apk upgrade` in the image, which an earlier commit on this branch used and
  this one removes, so every image stays fully pinned.
- The new `node:22-bookworm-slim` digest must contain Node >= 22.23.4
  (`NODE_VERSION` in the image config). If the newest digest does not yet,
  stop and ask the developer.
- `.github/workflows/ci.yml`: add `version: "0.13.4"` (or newer) to the
  `setup-uv` step.
- `.github/scripts/verify-production-runtime.sh`: read the dind container's
  IP from the per-network `bridge` entry instead of the deprecated top-level
  field (added 2026-11-02 for the CI failure on PR 126). Resolve the address
  once after the daemon starts and again after its restart, and stop with a
  clear failure if it is empty or not IPv4; the certificate-persistence check
  fails on an empty fingerprint (AI review round 2, F-003). A failing first
  fingerprint and a daemon that does not come back after the restart also stop
  with a clear failure (AI review round 3, F-001 and F-002).
- Do not change `backend/uv.lock`; certifi 2026.10.23 is already fixed.
- Release to production through the runbook (`docs/runbooks/production.md`
  sections 3 and 5), with human approval.

## Acceptance Criteria

- [ ] The backend image reports `uv --version` >= 0.13.4.
- [ ] The production backend image reports certifi `2026.10.23` or newer.
- [ ] The new base image digests are pinned, and the builds use them (the
      digest change invalidates the old layers).
- [ ] The emSign root is not in the CA store of the backend and frontend images
      (see Testing).
- [ ] The pinned `node:22-bookworm-slim` image reports Node >= 22.23.4.
- [ ] CI is green, and its "Set up Node" step logs Node >= 22.23.4.
- [ ] Production runs the new release; the narrow smoke (runbook section 7)
      passes and the release record is complete.
- [ ] The operator workstation's uv is >= 0.13.4 (`uv self update` or the
      package manager), and its Node is >= 24.22.1 (or >= 22.23.4).

## Out Of Scope

- Upgrading the Python, Node or Caddy release lines (Python and Node change only
  their digests and patch versions; Caddy goes from 2.11.4 to 2.11.7 within
  the 2.11 line, see Requirements).
- Ubuntu host packages beyond normal `unattended-upgrades`; the host's
  `ca-certificates` is checked, not managed by this task.
- Adding `--no-cache` to `deploy/bin/build-release` permanently.
- Off-server builds (GHCR).

## Implementation Notes

- **"Rebuild without the layer cache" is not enough on its own here.** Every
  base image is digest-pinned and neither Dockerfile runs `apt-get`, so
  `--no-cache` with unchanged pins rebuilds the same stale CA store. The fix is
  the new pins; changing them invalidates the cache automatically. For an extra
  guarantee the operator may run the first build after this change with
  `docker builder prune` beforehand (optional; it only costs build time).
- `deploy/bin/build-release` runs `docker buildx build` without
  `--no-cache`/`--pull`; this is fine because the base images are referenced
  by digest.
- Get the digests with, for example,
  `docker buildx imagetools inspect ghcr.io/astral-sh/uv:0.13.4` (and the same
  for each base image), and use the multi-arch index digest.
- Bumping a pinned build tool or base image digest does not add a new
  dependency. It still changes the build toolchain, so the developer approves
  it in the PR.
- Branch: `chore/TASK-073-emsign-ca-trust-refresh`.
- Deployment follows ADR-013 / TASK-059H: run the manual "Deploy to production"
  GitHub Action from `main`, `shadow-receive <manifest sha>`, `$M2 build`,
  rehearse the latest backup, `$M2 check`,
  `$M2 deploy RELEASE=$R2 APPROVAL=<ref>`, then smoke. The approval reference
  for the release record is this task plus the advisory.
- Rollback: the previous release is schema-compatible (no migrations), so
  `deploy-release <previous> --rollback --confirm-schema-compatible` is
  possible. It would reintroduce the old uv/CA store only into the images, not
  into running TLS clients that matter (the runtime uses certifi from the lock).

## Testing

Required:

- [ ] Backend tests (CI)
- [ ] Frontend tests (CI)
- [ ] Build (local `docker compose build` and the production build on the host)
- [ ] Manual verification (image checks below, production smoke)

Not applicable:

- [ ] Reason: no application code changes; only image pins and the CI tool version.

Commands:

```bash
# Local
docker compose build
docker buildx build --load --target production -t shadow-backend:check -f backend/Dockerfile .
docker run --rm --entrypoint uv shadow-backend:check --version
docker buildx imagetools inspect --format '{{json .Image}}' docker.io/library/node:22-bookworm-slim@sha256:<new-digest> | grep -o 'NODE_VERSION=[^"]*'
docker run --rm shadow-backend:check python -c "import certifi; print(certifi.__version__)"
# emSign should be absent from certifi and from the system store
docker run --rm shadow-backend:check sh -c 'grep -c "emSign" "$(python -c "import certifi; print(certifi.where())")" /etc/ssl/certs/ca-certificates.crt || true'

# On the host after build (release env printed by $M2 build)
docker run --rm --entrypoint uv shadow-backend:<release-id> --version
dpkg -l ca-certificates   # host package, informational
```

Note: the system stores may still contain other emSign roots (for example the
RSA G1) until Debian/Alpine drop them. Record what `grep` shows; only the ECC
G3 root removal is required by Chrome/Mozilla.

## Verification Results (2026-10-30 and 2026-11-02)

- Backend image: `uv 0.13.4`, Python 3.12.16, certifi 2026.10.23. certifi
  and the Debian store no longer contain emSign ECC Root CA - G3; they still
  contain emSign Root CA - G1, and the Debian store also has C1 and the ECC C3.
- Frontend build stage: Node v22.23.4; Node's bundled root store contains
  only emSign Root CA - G1.
- Frontend production (2026-11-02): Caddy v2.11.7 on Alpine 3.23.7 with
  `ca-certificates 20261020-r0`. Of the 13 base64 lines of the emSign ECC G3
  certificate, all 13 are in the `caddy:2.11.4-alpine` bundle and none in the
  new image's; only emSign Root CA - G1 is left. The image runs as user 10001.
  `caddy validate` passes for `frontend/Caddyfile` (acme mode) and for
  `local/Caddyfile` with the local development certificates.
- Backend: ruff, pyright, and pytest (1224 passed, 76 skipped) pass.
- Frontend: format check, lint, tests (401) and build pass.
  `docker compose --env-file .env.entra.local build` passes.
- 2026-11-02, after AI review round 1: `python:3.12-slim` re-pinned to the
  tag's current index digest (upstream re-pushed the index; the linux/amd64
  manifest is unchanged, Python 3.12.16).
- 2026-11-02, CI on PR 126: `verify-production-runtime.sh` failed to read the
  dind container's IP, because the runner's Docker no longer returns the
  deprecated top-level `NetworkSettings.IPAddress`. The script now reads the
  `bridge` network's address instead. This fix is outside the original scope,
  added at the developer's request so that the PR's CI can pass.
- 2026-11-02, F-003: the runtime QA script resolves and validates the dind
  address up front and after the daemon restart. A missing container and a
  container without a bridge network both stop with a clear failure, and a
  normal container returns its address. shellcheck passes.
- 2026-11-02, round-3 F-001 and F-002: a harness under the script's shell
  options shows that a failing or empty first fingerprint and a post-restart
  wait timeout each stop with their own FAIL message, and a daemon that comes
  back lets the run continue. shellcheck passes.
- Operator workstation (2026-11-02): uv 0.13.6; Node v24.22.2 (nvm default
  switched from v24.18.0, checked in a fresh shell).
- Not done: production release.

## Documentation

- `docs/runbooks/production.md`: no change expected; if the
  `docker builder prune` step is used, record it in the release record, not in
  the runbook.
- Release record (runbook section 11).

## Notes For AI Agent

- Read `AGENTS.md`, `docs/architecture/overview.md` and ADR-013 before the change.
- Do not deploy; production release needs human approval and is run by the
  operator.
- Keep the change to the files listed in Requirements.
