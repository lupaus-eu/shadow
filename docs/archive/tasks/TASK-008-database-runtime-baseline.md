# TASK-008 Database Runtime Baseline

## Source Plan

Approved plan: create the first PostgreSQL database baseline for Shadow.

This task covers only the local database runtime needed before schema and seed tasks can be used locally.

## Goal

Add a local PostgreSQL database container to the Docker Compose development environment.

This implements the ADR-001 and `docs/architecture/overview.md` direction where frontend, backend and database run in separate local containers.

## Requirements

- Add a root-level Docker Compose service named `database`.
- Use the official PostgreSQL image pinned to `postgres:18.0`.
- Use `postgres:18.0` for the local runtime so the container can actually start from an available official image.
- Document that production deployment should switch the PostgreSQL pin to `18.0.4` once the managed production target uses that version and the matching image or deployment target is available.
- Expose PostgreSQL on host port `5432`.
- Use a named Docker volume for database data.
- Configure database name, user and password from environment variables with safe local defaults.
- Add the database environment variables to `.env.example`.
- Do not add backend code, database schema, migrations, seed data or application logic in this task.
- Update local development documentation with database startup, shutdown and reset instructions.

## Acceptance Criteria

- [ ] `docker compose up database` starts a PostgreSQL container.
- [ ] The database service uses `postgres:18.0`, not `latest` or an unpinned major version.
- [ ] The task or local development documentation notes that production deployment should switch to `18.0.4` once available.
- [ ] PostgreSQL is reachable on `localhost:5432`.
- [ ] Database data persists across container restarts through a named volume.
- [ ] `.env.example` documents the local database variables.
- [ ] `docs/operations/local-development.md` explains how to start, stop and reset the local database.
- [ ] No schema tables are created by this task.
- [ ] No backend, frontend or application behavior is changed.
- [ ] No new project dependencies are added.

## Out Of Scope

- Database schema migrations.
- Init or seed SQL.
- Backend container scaffolding.
- Backend SQLAlchemy models or database connection code.
- Authentication, authorization or API behavior.
- Production or staging database provisioning.

## Implementation Notes

- Use service name `database`.
- Use volume name `database_data`.
- For PostgreSQL 18 images, mount `database_data` at `/var/lib/postgresql`, not `/var/lib/postgresql/data`.
- Recommended environment variables:
  - `POSTGRES_DB=${DATABASE_NAME:-shadow}`
  - `POSTGRES_USER=${DATABASE_USER:-shadow}`
  - `POSTGRES_PASSWORD=${DATABASE_PASSWORD:-shadow_dev_password}`
- Add `.env.example` entries:
  - `DATABASE_NAME=shadow`
  - `DATABASE_USER=shadow`
  - `DATABASE_PASSWORD=shadow_dev_password`
  - `DATABASE_HOST=localhost`
  - `DATABASE_PORT=5432`
- The local password is development-only and must be clearly documented as non-production.
- Do not mount `db/migrations/` or `db/init/` yet unless needed by later tasks.

## Testing

Required:

- [ ] Manual verification
- [ ] Docker Compose validation

Not applicable:

- [ ] Frontend tests: no frontend behavior changes.
- [ ] Backend tests: no backend code changes.
- [ ] Integration tests: no application/database integration in this task.
- [ ] Lint: no linted source code changes expected.
- [ ] Build: no application build changes.
- [ ] Typecheck: no typed source code changes.

Commands:

```bash
docker compose config
docker compose up -d database
docker compose ps database
docker compose down
```

Optional manual verification if `psql` is available locally:

```bash
PGPASSWORD=shadow_dev_password psql -h localhost -p 5432 -U shadow -d shadow -c "SELECT 1;"
```

## Documentation

Update:

- `.env.example`
- `docs/operations/local-development.md`

No ADR is required because ADR-001 already selects PostgreSQL and local Docker containers.

## Notes For AI Agent

- Lue `AGENTS.md`, `docs/architecture/overview.md`, `docs/adr/0001-tech-stack.md`, `docs/operations/local-development.md` ja tämä task ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää backend-, schema-, migration- tai seed-muutoksia tässä taskissa.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
