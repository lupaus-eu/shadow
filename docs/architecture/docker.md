# Docker

## Services

- `frontend` builds from `frontend/Dockerfile`.
- `backend` builds from `backend/Dockerfile`.
- `db` runs PostgreSQL and exposes a health check.
- `migrate` applies Alembic migrations after PostgreSQL becomes healthy and before the backend starts.
- `authentik-db-init` idempotently creates Authentik's separate logical database and owner.
- `authentik-server` and `authentik-worker` run the pinned self-hosted identity provider and share no application tables or credentials.
- `authentik-config-init` applies verified-email enrollment, MFA recovery, passkey, and mandatory second-factor policy, the Shadow OIDC application, the Shadow MCP application (ADR-0038), and the sign-in pages' look (ADR-0039) before the backend starts. The backend serves the MCP interface at `/api/mcp` on its existing port when `MCP_ENABLED` is true; it adds no port.
- `worker` runs the backend image with `python -m app.worker`. It delivers Invitation email, runs notification cleanup and Organization purge jobs, and expires Support Access grants.
- `caddy` uses the official `caddy:2-alpine` image. It belongs to the `edge`
  profile and starts only with `docker compose --profile edge up`.

## Project name and host ports

The Compose project is named `yearclock`, so containers, networks, and volumes
are named `yearclock-<service>-<n>` in every checkout. Services never set
`container_name`.

Yearclock owns host ports **8100–8199** on shared development machines. Other
projects on the same machine use their own ranges. Every published port binds
to `127.0.0.1` and is overridable through the variable shown. Containers reach
each other on the Compose network by service name and container port
(`db:5432`, `authentik-server:9000`, `backend:8000`), which these assignments
do not affect.

| Host port | Variable | Service or process | Container port |
| --- | --- | --- | --- |
| 8100 | `YEARCLOCK_BACKEND_PORT` | `backend`; also `uvicorn --port 8100` outside Compose | 8000 |
| 8132 | `YEARCLOCK_DB_PORT` | `db` (host pytest and Alembic) | 5432 |
| 8143 | `YEARCLOCK_HTTPS_PORT` | `caddy` HTTPS (`edge` profile) | 443 |
| 8173 | `YEARCLOCK_FRONTEND_PORT` | `frontend` Vite dev server; also `npm run dev` | 8173 |
| 8174 | — | Playwright browser-test server (`npm run dev:test`) | — |
| 8175 | — | `npm run preview` | — |
| 8176 | — | LikeC4 view browser (`make c4`) | — |
| 8180 | `YEARCLOCK_HTTP_PORT` | `caddy` HTTP (`edge` profile) | 80 |
| 8190 | `YEARCLOCK_AUTHENTIK_PORT` | `authentik-server` | 9000 |

Vite uses `strictPort`, so a busy port stops it instead of silently moving to
another one. When you change a host port, also change the URLs that contain it
in `.env` (`FRONTEND_URL`, `FRONTEND_ORIGINS`, `VITE_API_BASE_URL`,
`PUBLIC_API_BASE_URL`, `OIDC_ISSUER`, `OIDC_REDIRECT_URI`, `TEST_DATABASE_URL`).

`python3 scripts/check-compose-ports.py` enforces the project name, the port
syntax, the range, the `127.0.0.1` default, and unique ports. CI runs it on
every push.

## Persistence target

The application PostgreSQL database is wired into Compose with persistent storage. Local initialization also creates an isolated integration-test database. Authentik uses a separate logical database, owner, connection pool, and migration history on the same first-release PostgreSQL instance.

## Local Development

```bash
make up      # docker compose up -d --build
make down    # docker compose down (volumes are kept)
make help    # logs, tests, port check, Stripe webhook forwarding
```

### Live reload (`make dev`)

`docker-compose.dev.yml` is layered on `docker-compose.yml` and changes only how code reaches the
containers; it adds no service and no port, and Caddy stays behind the `edge` profile.

```bash
make dev         # docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
make dev-worker  # restart the worker after a backend change (it has no live reload)
make dev-down    # stop; data volumes are kept
```

- `backend` runs `uvicorn --reload` on `./backend/app`, `migrations` and `legal`, bind-mounted into the
  container, so a Python edit restarts the API within seconds. A new Alembic migration still needs
  `docker compose run --rm migrate`.
- `frontend` runs the Vite dev server on the bind-mounted `./frontend` with hot module replacement.
  `node_modules` lives in a named volume (`frontend_node_modules`) so the container's Linux packages are not
  hidden by the host folder; after changing `package.json` run `make dev` again (it rebuilds the image) and

  `VITE_USE_POLLING` (default `true`) makes Vite poll for file changes because events do not always cross a
  bind mount on macOS and Windows.
- `scripts/check-compose-ports.py` resolves the dev file together with the base file.

`make stripe-listen` forwards Stripe test-mode webhooks to the local backend
with the Stripe CLI, using `STRIPE_SECRET_KEY` from `.env`.

Use `.env` for local values. Keep `.env.example` synchronized when adding required variables, and `.env.production.example` when `docker-compose.prod.yml` or the backup scripts gain one.

## Deployment Notes

`docker-compose.yml` is the local development stack and the only one that
builds; `docker-compose.dev.yml` layers live reload on top of it (`make dev`). `docker-compose.prod.yml` is the production stack; it runs images from GHCR
selected by `YEARCLOCK_TAG` (ADR-0035) and builds nothing: only `caddy` publishes ports, with the same variables
and 81NN defaults so the port check passes; production sets
`YEARCLOCK_EDGE_BIND_ADDRESS=0.0.0.0`, `YEARCLOCK_HTTP_PORT=80`, and
`YEARCLOCK_HTTPS_PORT=443`. The port check gives required `${NAME:?}`
variables placeholder values when it resolves a file. See
`docs/architecture/deployment.md` and `docs/runbooks/production-readiness.md`.
