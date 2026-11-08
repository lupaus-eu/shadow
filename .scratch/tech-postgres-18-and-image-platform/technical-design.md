# Technical design: PostgreSQL 18 and the image platform

Status: accepted

## Current and target state

- **Current state:** `images.yml` builds `linux/amd64`; `postgres:17-alpine` in `docker-compose.yml`, `docker-compose.prod.yml` and CI, with the data volume `postgres_data` mounted at `/var/lib/postgresql/data`.
- **Target state:** ADR-0053: PostgreSQL 18 with the volume `postgres18_data` mounted at `/var/lib/postgresql`, a documented dump-and-restore upgrade. The image platform stays `linux/amd64`: an arm64 switch was tried for an Ampere host and reverted when the host became an Intel server (history in ticket 01).

## Changes

- `docker-compose.yml`, `docker-compose.prod.yml`: `postgres:18-alpine` for `db` and `authentik-db-init`; volume `postgres18_data` at `/var/lib/postgresql`; `docker-compose.dev.yml` needs no change.
- `.github/workflows/ci.yml`: `postgres:18-alpine`.
- `.gitignore`: `/backups/`.
- Documents: `docs/runbooks/postgres-major-upgrade.md` (new), `deployment.md`, `docker.md`, `stack.md`, C4 (`deployment.c4`, `model.c4`), ADR-0035 closing line.

## Testing

- A throwaway Compose project (`-p`, its own port and volume) starts the `db` service on PostgreSQL 18 and checks the version, the init scripts (test database, Authentik role and database) and the volume layout.
- The dumps taken from the running PostgreSQL 17 stack are restored into it with `pg_restore --clean --if-exists --no-owner` (the upgrade rehearsal).
- The whole backend suite against that PostgreSQL 18 (`TEST_DATABASE_URL`).
- `docker compose config`, `python3 scripts/check-compose-ports.py`, `make models`.

## Configuration

No new variables.

## Architecture effects

No service or boundary change; the database engine version and the image platform change.

## Documentation effects

- [x] ADR-0053 accepted; closing line in ADR-0035
- [x] `docs/runbooks/postgres-major-upgrade.md`, `docs/architecture/{deployment,docker,stack}.md`, C4

## Options and decision

1. Keep amd64 (chosen, since the host is x86-64): no workflow change. An arm64 build with QEMU was tried for an Ampere host and reverted; it checked that every base image and Prophet support arm64, so a later arm64 host needs only `platforms` and a QEMU step.
2. Keep the volume name `postgres_data` and mount it at the new path: the new cluster would sit in a subdirectory of the old PostgreSQL 17 data, a confusing mix. Rejected for a renamed volume.
3. Upgrade in place with `pg_upgrade`: needs both binaries in one image. Rejected; dump and restore is the project's tested backup path.
