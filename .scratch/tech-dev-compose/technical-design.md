# Technical design: Compose file for local development with live reload

Status: implemented

Technical work with no user-visible behaviour, so no PRD (`FEATURE_WORKFLOW.md`).

## Goal and scope

The product owner wants to test Shadow in the browser on their own machine, from a Compose file
separate from production, without Caddy, with the web side served by the Vite dev server rather than a
built container.

**Out of scope:** changes to `docker-compose.prod.yml`, the images, the Authentik setup, and the
ports.

## Current and target state

- **Current:** `docker-compose.yml` is already a local stack. Caddy is opt-in (`--profile edge`) and
  the frontend runs the Vite dev server in a container (target `development`). But both services copy
  the source into the image at build time, with no mounts: a code edit needs `make up` to rebuild, the
  API has no reload, and Vite's hot reload sees nothing.
- **Target:** `docker-compose.dev.yml`, layered on the base file, makes the edit-and-look loop work
  without rebuilds. Same services, same ports, same environment.

## Options and decision

1. **Override file on top of the base file (chosen).** The dev file only carries what differs:
   bind mounts, `uvicorn --reload`, polling for Vite. No second copy of Authentik, Postgres and the
   environment, which would drift. Run with `make dev`.
2. A standalone copy of the whole stack. Rejected: ~200 duplicated lines that must be edited twice.
3. Vite on the host outside Compose. Rejected for now: the sign-in pages and CORS settings assume
   `http://localhost:8173`, which the container already provides, and the Authentik theme is fetched
   from that origin. It remains possible (`npm run dev` after `docker compose stop frontend`).
4. Caddy is not started by either file: it stays behind the `edge` profile, so nothing to remove.

## Design

`docker-compose.dev.yml`:

- `backend`: command `uvicorn … --reload --reload-dir /app/app`; mounts `./backend/app`,
  `./backend/migrations`, `./backend/legal` over the image's copies.
- `worker`: same mounts, no reload (`make dev-worker` restarts it).
- `frontend`: mounts `./frontend` at `/app`, with the container's `node_modules` in the named volume
  `frontend_node_modules` so the host folder does not hide it; `VITE_USE_POLLING` (default `true`)
  turns on `server.watch.usePolling` in `frontend/vite.config.ts`.
- No `ports`, no `container_name`, `name: shadow`.

`Makefile`: `dev`, `dev-down`, `dev-worker`. `scripts/check-compose-ports.py` resolves override files
together with the base file, so the project-name and port rules still apply to the new file.

## Risks

- Bind mounts on macOS/Windows are slower, and file events can be lost; polling (300 ms) covers the
  frontend, uvicorn uses WatchFiles and was seen to reload.
- A new Alembic migration is not applied by a reload; the `migrate` service runs once per `up`.
- The `frontend_node_modules` volume can hold stale packages after a `package.json` change; `make dev`
  rebuilds the image, and `docker volume rm shadow_frontend_node_modules` resets it.

## Testing

- `docker compose -f docker-compose.yml -f docker-compose.dev.yml config -q`;
  `python3 scripts/check-compose-ports.py`.
- Run: `make dev` started every service; `touch backend/app/main.py` restarted the API worker process;
  an edit in `frontend/src` produced a Vite `hmr update` in the frontend log.
- Browser use of the stack is by the product owner.

## Documentation effects

- [x] `docs/architecture/docker.md` — Live reload section
- [x] `docs/architecture/project-layout.md` — file listed
- [x] `Makefile` help targets
