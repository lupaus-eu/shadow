# Deployment

## Target

- Repository: `lupaus-eu/yearclock`
- Domain: `yearclock.example.com` (placeholder; the production product name and
  domain are undecided)
- Expected platform: a single Docker Compose host. The alpha and beta run on an
  UpCloud cloud server (ADR-0035); Coolify or another Compose host also works.
- Images: built in CI, pushed to GHCR, and pulled on the host (ADR-0035).

## Services to deploy

- Caddy edge with production TLS
- React frontend served as a production build
- FastAPI backend
- `migrate` one-shot Alembic job, run before backend and worker rollout
- Python `worker` processes built from the backend image
- PostgreSQL instance with separate Yearclock and Authentik logical databases,
  owners, credentials, connection pools, migration histories, and backups
  (ADR-0011)
- Authentik server, worker, and configuration bootstrap

External services: Stripe Billing (ADR-0009) and Scaleway Transactional Email
(ADR-0023). Every required production key is listed in `.env.production.example` (local development
uses `.env.example`); production values
are deployment secrets and never committed.

## Production definition

- `docker-compose.prod.yml` is the production stack. It publishes only Caddy,
  requires every secret (`${NAME:?}`), runs `migrate` before `backend` and
  `worker`, restarts services, and keeps `postgres_data`, Authentik media, and
  Caddy certificates in volumes. It builds nothing: `migrate`, `backend`, and
  `worker` run the backend image and `frontend` the frontend image, both selected
  by `YEARCLOCK_TAG` (see "Images and deployment").
- The frontend image's `production` target builds the SPA with a same-origin
  API (`VITE_API_BASE_URL=""`) and serves it with Caddy, mapping every route,
  including `/platform`, to `index.html`. The local stack uses the
  `development` target (Vite).
- `caddy/` (mounted as a directory; `make deploy` runs `caddy reload`) holds the Caddyfile and serves the app, operator console, and API on
  `YEARCLOCK_SITE_ADDRESS` and Authentik on `YEARCLOCK_IDENTITY_ADDRESS`, with
  HSTS, a strict Content-Security-Policy (override with
  `YEARCLOCK_CONTENT_SECURITY_POLICY`), `nosniff`, a referrer policy, a
  permissions policy, and `Cache-Control: no-store` for `/api/*` and
  `/platform`. The local `edge` profile uses the same file; its CSP blocks the
  Vite dev server, so use it with a production-style build.
- The backend runs `BACKEND_WORKERS` uvicorn processes behind the proxy. Each
  process and the worker size their pool with `DATABASE_POOL_SIZE` and
  `DATABASE_MAX_OVERFLOW`; keep the total below `POSTGRES_MAX_CONNECTIONS`
  minus Authentik's connections.
- Monitoring: `docs/operations/monitoring.md`. Backups and restore drills:
  `scripts/ops/backup-databases.sh` and `scripts/ops/restore-drill.sh`, which
  dump and restore the two databases separately with their own owners.
  `scripts/ops/backup-offsite.sh` encrypts the dumps with restic into Scaleway
  Object Storage on a systemd timer and emails failures through Scaleway Transactional Email (optional heartbeat); see
  `docs/runbooks/backup.md`.
- Every production service rotates its `json-file` logs (`LOG_MAX_SIZE`,
  `LOG_MAX_FILE`); `scripts/check-compose-ports.py` fails when one does not. A
  host disk check (`scripts/ops/check-disk.sh`) alerts before the disk fills.
- Authentik enrollment is closed in production: an account needs an invitation
  link created in Authentik (`AUTHENTIK_ENROLLMENT_OPEN=false`;
  `docs/runbooks/authentik-invitations.md`).
- Steps that need production accounts, DNS, or secrets are listed in
  `docs/runbooks/production-readiness.md` and are not yet executed.

## Images and deployment

- `.github/workflows/images.yml` builds `yearclock-backend` and
  `yearclock-frontend` (the `production` target, same-origin API) for
  `linux/amd64` and pushes them to `ghcr.io/lupaus-eu/` on every push to `main`
  and every `v*` tag. Tags are `sha-<short>`, the Git tag, and `main`; there is no
  `latest`. `YEARCLOCK_IMAGE_PREFIX` overrides the registry path. CI deploys
  nothing and holds no host secret.
- The host needs Docker, `docker-compose.prod.yml`, `caddy/Caddyfile`, `authentik/`,
  `scripts/ops/`, and `.env.production`; it has no source tree to build.
- First time: `docker login ghcr.io -u <user>` with a token that has only
  `read:packages`.
- Release: cut a `v*` tag from a `main` commit whose CI run is green, wait for the
  Images workflow, set `YEARCLOCK_TAG` in `.env.production`, then:

  ```bash
  docker compose -f docker-compose.prod.yml --env-file .env.production pull
  docker compose -f docker-compose.prod.yml --env-file .env.production up -d
  ```

  `migrate` runs first, and `authentik-config-init` waits for a healthy Authentik
  server (its migrations done) and skips unchanged blueprints
  (`authentik/configure.sh`). Alembic migrations are forward-only in production, so
  roll back to an earlier tag only when it is compatible with the current schema;
  otherwise restore from backup (`docs/runbooks/backup.md`).
- The host's files (Compose file, Caddyfile, Authentik blueprints, scripts) are not in the images: copy them with the `rsync` command in `docs/runbooks/first-deployment.md` section 7 before each release that changes them.
- Rollback: set the previous `YEARCLOCK_TAG` and run the same two commands.
- `Makefile.prod`, copied to the host as `Makefile`, wraps these commands (`make deploy`, `make tag TAG=…`, `make logs`, `make authentik-apply`, `make enroll-platform`); it is not used in development (`docs/runbooks/production-commands.md`).
- Prune old tags in GHCR now and then; run `docker image prune -a` on the host.

## Host size (UpCloud, ADR-0035)

| Plan | Use |
| --- | --- |
| 1 GB | Not enough: Authentik alone needs about 1 to 1.5 GB |
| 2 GB, 2 CPU (EUR 8 on 2026-11-03) | Minimum for the test phase; add 2 GB swap |
| 4 GB, 2 CPU (EUR 12) | Recommended |

`scripts/ops/cloud-init.yml` prepares a fresh Ubuntu host (Docker with Compose,
restic, git, make, swap, ufw, automatic security updates) when pasted into the server's
user data; the first-start order is in `docs/runbooks/first-deployment.md`.

The test phase (fewer than five users) keeps PostgreSQL in its container, which
uses about 150 to 400 MB. Moving to a managed PostgreSQL is decided in ticket 08
of `tech-beta-launch`; it needs SSL, an allow-list for the host, a rewritten
`authentik-db-init`, pools under the managed `max_connections`, and remote
`pg_dump` in the backup scripts. Open only 22, 80, and 443 in the firewall.


## Beta and Stripe

The invited beta, its access gate, and its database and backup stance are in
`docs/runbooks/beta-launch.md` (ADR-0034, proposed); the Stripe live setup is in
`docs/runbooks/stripe-production.md`.

## Checklist

Follow `docs/runbooks/production-readiness.md`. In summary:

- Set production environment variables and secrets.
- Point DNS for the production domain at the host.
- Confirm Caddy can bind ports 80 and 443 and obtain certificates.
- Configure the Stripe Product, Price, tax, webhook endpoint, and Customer Portal
  with quantity updates disabled.
- Verify Scaleway sender identity, SPF, DKIM, DMARC, and MX.
- Confirm persistent volumes, backups, and independent restores for both
  databases.
