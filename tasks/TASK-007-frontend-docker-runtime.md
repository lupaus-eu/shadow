# TASK-007 Frontend Docker Runtime

## Source Plan

Approved plan: add Docker runtime support for the frontend in both local development mode and production-like preview mode.

The plan covers:

- `frontend/Dockerfile`
- `frontend/.dockerignore`
- `docker-compose.yml`
- `frontend/vite.config.ts`
- `.env.example`
- `docs/LOCAL-DEVELOPMENT.md`
- `README.md`

## Goal

Make the frontend runnable from a Docker container for local development and for production-like preview of the built Vite output.

This implements the ADR-001 and `ARCHITECTURE.md` local runtime direction where the frontend runs in its own Docker container.

## Requirements

- Add a multi-stage frontend Dockerfile with `dev`, `build` and `preview` stages.
- Use `node:22-bookworm-slim` as the frontend container base image.
- Use pnpm through Corepack and the existing `packageManager` version.
- Add a frontend `.dockerignore` that excludes dependencies, build output, Vite cache, logs and TypeScript build cache files.
- Add root-level Docker Compose services:
  - `frontend` for Vite dev server on port `5173`.
  - `frontend-preview` for Vite preview server on port `4173` behind a `preview` profile.
- Use a named volume for `/app/node_modules` in the dev service so the source bind mount does not hide container dependencies.
- Make the Vite dev `/api` proxy target configurable with `VITE_DEV_API_PROXY_TARGET`.
- In Compose, set `VITE_DEV_API_PROXY_TARGET` from `FRONTEND_DEV_API_PROXY_TARGET`, defaulting to `http://host.docker.internal:8000`.
- Keep existing frontend `VITE_API_BASE_URL` behavior unchanged.
- Update local development documentation and README with the Docker commands.

## Acceptance Criteria

- [ ] `docker compose up frontend` starts the frontend dev container.
- [ ] Frontend dev server is available at `http://localhost:5173`.
- [ ] Frontend source edits are visible in the dev container without rebuilding the image.
- [ ] `docker compose --profile preview up frontend-preview` builds and serves the frontend preview container.
- [ ] Frontend preview is available at `http://localhost:4173`.
- [ ] Vite dev proxy uses configurable `FRONTEND_DEV_API_PROXY_TARGET` through Compose.
- [ ] No new pnpm dependencies are added.
- [ ] Backend, database, authentication, CI and deployment behavior are unchanged.
- [ ] No ADR is added because the task implements the existing Docker local runtime direction.

## Out Of Scope

- Adding backend or database containers.
- Adding production deployment configuration.
- Changing CI behavior.
- Changing authentication, authorization or backend API behavior.
- Adding new npm/pnpm dependencies.
- Replacing Vite preview with Nginx or another static server.

## Implementation Notes

- Backend scaffolding is not present yet, so the frontend dev container proxies `/api` to a host backend by default.
- `host.docker.internal` is enabled for Linux hosts through Compose `extra_hosts`.
- Preview mode serves the built frontend with Vite preview and does not add API proxy behavior.
- No architecture ADR is expected because ADR-001 already selects Docker containers for local runtime.

## Testing

Required:

- [x] Frontend tests
- [ ] Backend tests
- [ ] Integration tests
- [x] Manual verification
- [x] Lint
- [x] Build
- [x] Docker Compose validation
- [x] Docker image build

Not applicable:

- [x] Backend tests: no backend code changes.
- [x] Integration tests: no backend/database container exists in this task.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build

cd ..
docker compose config
docker compose build frontend
docker compose up -d frontend
curl -f http://localhost:5173
docker compose down

docker compose --profile preview build frontend-preview
docker compose --profile preview up -d frontend-preview
curl -f http://localhost:4173
docker compose --profile preview down
```

If `curl` is not available, manually verify the URLs in a browser and document that in the PR.

## Documentation

Update:

- `README.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `.env.example`

## Notes For AI Agent

- Lue `AGENTS.md`, `ARCHITECTURE.md`, `docs/decisions/ADR-001-tech-stack.md`, `docs/TESTING.md` ja tämä task ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Älä lisää backend- tai database-kontteja tässä taskissa.
- Lisää testejä ei tarvita, koska muutos koskee runtime-konfiguraatiota ja dokumentaatiota, ei sovelluksen business-logiikkaa.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
