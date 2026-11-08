# Ticket 01: image platform (arm64 tried, reverted to amd64)

Status: resolved

## Goal

Build the production images for linux/arm64.

## Implementation

- `images.yml`: QEMU step and `platforms: linux/arm64`.
- `frontend/Dockerfile`: Node stages on `$BUILDPLATFORM`, Caddy stage on the target.
- Update `docs/architecture/deployment.md` and `stack.md`.

## Acceptance criteria

- [x] The workflow file is valid and builds only `linux/arm64`.
- [x] `docker buildx build --platform linux/arm64` succeeds locally for the backend image and the frontend `production` target, and `docker image inspect` shows `arm64`.
- [x] The frontend development target still builds (`make dev`).

## Testing

- [x] Migration/integration/architecture validation — see the technical design

## Ajetut tarkistukset

- [x] `.github/workflows/images.yml` — QEMU step and `platforms: linux/arm64` (not run here: needs GitHub)
- [x] `docker buildx build --platform linux/arm64` backend image — built; `docker image inspect` showed `arm64`
- [x] `docker buildx build --platform linux/arm64 --target production` frontend image — built; `docker image inspect` showed `arm64`
- [x] `docker compose -f docker-compose.yml -f docker-compose.dev.yml config -q` — dev config valid

## AI review

- [x] Self-review of the diff against ADR-0053 and the technical design

## Documentation effects

- [x] Update architecture or ADR

## Blocked by

None.

## Completion record

- The workflow builds only `linux/arm64` with QEMU; the frontend Node stages run on `$BUILDPLATFORM` and only the Caddy stage on the target. Both images built as arm64 locally. The first run on GitHub (a push to `main` or a `v*` tag) is the remaining check; `docs/architecture/deployment.md` and `stack.md` are updated.

## Outcome (2026-11-09)

- The arm64 switch was implemented and checked (the backend image and the frontend `production` target both built as arm64 locally), then reverted the same day when the first host became a Hetzner Intel server. `images.yml` and `frontend/Dockerfile` are back to their original `linux/amd64` form (the diff against the commit before the switch is empty). ADR-0053 and `deployment.md` / `stack.md` say amd64. Nothing to build for arm64 unless a later host needs it.
