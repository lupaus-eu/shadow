# Ticket 01: docker-compose.dev.yml with live reload

Status: resolved

## Goal

`make dev` starts the local stack so that backend and frontend edits show up without a rebuild; no Caddy.

## Implementation

- `docker-compose.dev.yml` (override of `docker-compose.yml`), `Makefile` targets, `VITE_USE_POLLING` in `frontend/vite.config.ts`, override support in `scripts/check-compose-ports.py`, docs.

## Acceptance criteria

- [x] `make dev` starts db, Authentik, migrate, backend, worker and frontend; Caddy does not start.
- [x] A Python edit restarts the API without a rebuild.
- [x] A frontend edit triggers Vite hot reload.
- [x] No port, no `container_name`; the port check passes with the new file.

## Testing

- [x] Compose config, port check, a live run (below). Browser testing by the product owner.

## Ajetut tarkistukset

- `docker compose -f docker-compose.yml -f docker-compose.dev.yml config -q` — OK.
- `python3 scripts/check-compose-ports.py` — OK (dev, prod and base files).
- `make dev` — all services up; `/health` returned ok; frontend answered 200 on 8173.
- `touch backend/app/main.py` — the backend log shows the server process restarted.
- Edit to `frontend/src/models/messages.ts` — the frontend log shows `[vite] hmr update` (the edit was reverted).

## Documentation effects

- [x] `docs/architecture/docker.md`, `docs/architecture/project-layout.md`

## Blocked by

- None

## Completion record

Committed locally with the dev compose file.
