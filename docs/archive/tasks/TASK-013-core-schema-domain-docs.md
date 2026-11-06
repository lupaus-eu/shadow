# TASK-013 Core Schema And Domain Documentation Updates

## Source Plan

Approved plan: align the existing core schema and source-of-truth documentation with backend organisation defaults and domain boundaries.

This task prepares the database and documentation for later backend CRUD and organisation creation behavior.

## Goal

Update the core schema and documentation so organisation states can persist a display name and organisations have active case-insensitive name uniqueness.

Define the relevant Shadow core domains and concepts before implementing domain API behavior.

## Requirements

- Add a numbered SQL migration in `db/migrations/`.
- Add `org_states.name TEXT NOT NULL`.
- Add active case-insensitive organisation name uniqueness.
- Prefer database-enforced uniqueness with a normalized partial unique index.
- Keep soft-deleted historical organisation names reusable.
- Update physical and logical data documentation.
- Update database diagram PlantUML source and generated SVG when the schema changes.
- Add or update domain documentation for:
  - users
  - organisations
  - org_states
  - org_twin_structure
- Add or update concept documentation for:
  - Organisation
  - Scenario
  - Organisation State
  - Metamodel
- Do not rewrite already accepted baseline migration `001_create_core_schema.sql` unless explicitly approved.

## Acceptance Criteria

- [ ] Add migration `002_*` for `org_states.name TEXT NOT NULL`.
- [ ] Add active case-insensitive organisation name uniqueness, preferably DB-enforced with normalized partial unique index.
- [ ] Update `docs/architecture/data/DATABASE.md`, `docs/architecture/data/DATA-MODEL.md`, and db PlantUML/SVG.
- [ ] Add/update domain docs for `users`, `organisations`, `org_states`, and `org_twin_structure`.
- [ ] Add/update concept docs for Organisation, Scenario, Organisation State, and Metamodel.
- [ ] Existing migration `001_create_core_schema.sql` is not rewritten unless explicitly approved.

## Out Of Scope

- Backend FastAPI scaffold.
- SQLAlchemy models.
- API endpoints.
- Frontend changes.
- Authentication or authorization.
- Metamodel copy service implementation.

## Implementation Notes

- This task depends on `TASK-009 Core Database Schema`.
- Read `docs/architecture/data/DATABASE.md`, `docs/architecture/data/DATA-MODEL.md`, `db/migrations/README.md`, `docs/architecture/domains/DOMAIN.md`, `docs/architecture/concepts/CONCEPTS.md`, `docs/architecture/diagrams/README.md` and this task before implementation.
- Preserve current soft-delete conventions.
- Organisation name uniqueness should apply only when `deleted_time IS NULL`.
- If existing local data makes a `NOT NULL` migration unsafe, add a deterministic backfill/default strategy in the migration.

## Testing

Required:

- [ ] SQL migration verification
- [ ] Documentation verification
- [ ] Manual database verification

Not applicable:

- [ ] Frontend tests: no frontend code changes.
- [ ] Backend tests: no backend code changes.
- [ ] Integration tests: no backend/database integration code in this task.
- [ ] Build: docs and SQL only.
- [ ] Typecheck: no typed source code changes.

Commands:

```bash
docker compose up -d database
PGPASSWORD=shadow_dev_password psql -h localhost -p 5432 -U shadow -d shadow -f db/migrations/001_create_core_schema.sql
PGPASSWORD=shadow_dev_password psql -h localhost -p 5432 -U shadow -d shadow -f db/migrations/002_<name>.sql
```

## Documentation

Update:

- `docs/architecture/data/DATABASE.md`
- `docs/architecture/data/DATA-MODEL.md`
- `docs/architecture/domains/DOMAIN.md`
- relevant `docs/architecture/domains/*.md`
- `docs/architecture/concepts/CONCEPTS.md`
- relevant `docs/architecture/concepts/*.md`
- `docs/architecture/diagrams/db-physical-schema.puml`
- `docs/architecture/diagrams/generated/db-physical-schema.svg`

## Notes For AI Agent

- Toteuta vain tämän taskin scope.
- Älä lisää backend- tai frontend-koodia tässä taskissa.
- Kaikki skeemamuutokset pitää tehdä migraatioina.
- Älä muuta tuotantotietokantaa.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
