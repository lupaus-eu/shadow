# TASK-019 Tighten Scenario Target Dates Schema

## Source Plan

Approved plan: tighten the physical database schema so both
`org_states.target_date` and `events.target_date` are not nullable.

The API/service layer already requires organisation state `target_date`.
`events.target_date` should also be treated as required at the physical schema
and ORM level.

## Goal

Align the database schema and SQLAlchemy models with the intended scenario
data model: organisation states and events are dated scenario records and must
always have `target_date`.

## Requirements

- Add a new migration `003_*` in `db/migrations/`.
- Do not edit existing migrations `001` or `002`.
- Make `org_states.target_date` `NOT NULL`.
- Make `events.target_date` `NOT NULL`.
- Fail the migration clearly if existing rows contain null target dates.
- Update SQLAlchemy models to match the physical schema.
- Update relevant data documentation and physical schema diagram.
- Do not add new dependencies.
- Do not implement Event CRUD.

## Acceptance Criteria

- [ ] A new migration exists with the next migration number.
- [ ] The migration checks for null `org_states.target_date` values before altering the column.
- [ ] The migration checks for null `events.target_date` values before altering the column.
- [ ] `org_states.target_date` is `NOT NULL` after the migration.
- [ ] `events.target_date` is `NOT NULL` after the migration.
- [ ] `OrgState.target_date` is non-nullable in SQLAlchemy typing and column config.
- [ ] `Event.target_date` is non-nullable in SQLAlchemy typing and column config.
- [ ] Existing org-state API validation behavior remains unchanged.
- [ ] Documentation describes both target-date columns as required at DB level.
- [ ] The physical schema PlantUML source and generated SVG are updated.
- [ ] No Event CRUD endpoint is added.

## Out Of Scope

- Event CRUD.
- Frontend changes.
- Authentication or authorization.
- Backfilling production data.
- Introducing a migration framework.
- Changing unrelated nullable columns.
- Editing already-created migration files.

## Implementation Notes

Read these before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0001-tech-stack.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/concepts/ORGANISATION_STATE.md
docs/architecture/concepts/SCENARIO.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
db/migrations/README.md
docs/operations/testing.md
```

Expected migration shape:

```sql
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM org_states WHERE target_date IS NULL) THEN
        RAISE EXCEPTION 'Cannot set org_states.target_date NOT NULL: null values exist';
    END IF;

    IF EXISTS (SELECT 1 FROM events WHERE target_date IS NULL) THEN
        RAISE EXCEPTION 'Cannot set events.target_date NOT NULL: null values exist';
    END IF;
END $$;

ALTER TABLE org_states
    ALTER COLUMN target_date SET NOT NULL;

ALTER TABLE events
    ALTER COLUMN target_date SET NOT NULL;
```

Expected model updates:

- `OrgState.target_date` should use `Mapped[dt_date]` and `nullable=False`.
- `Event.target_date` should use `Mapped[dt_date]` and `nullable=False`.
- Tighten org-state response schema if required by type checking.

Expected documentation updates:

- `docs/architecture/data/DATA-MODEL.md`
- `docs/architecture/data/DATABASE.md`
- `docs/architecture/diagrams/db-physical-schema.puml`
- `docs/architecture/diagrams/generated/db-physical-schema.svg`
- local migration instructions if they mention only the first migration

No ADR is expected because this tightens an existing schema invariant and does
not change architecture or technology choices.

## Testing

Required:

- [ ] Backend tests
- [ ] Migration verification
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests: no frontend behavior changes.
- [ ] Frontend build: no frontend behavior changes.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Migration verification should cover:

- applying migrations `001`, `002` and `003` to an empty local PostgreSQL database succeeds
- migration `003` fails clearly if `org_states.target_date` contains nulls
- migration `003` fails clearly if `events.target_date` contains nulls
- PostgreSQL rejects new null values for both columns after migration `003`

## Documentation

Update documentation only for the implemented schema tightening.

Expected documentation targets:

- `docs/architecture/data/DATA-MODEL.md`
- `docs/architecture/data/DATABASE.md`
- `docs/architecture/diagrams/db-physical-schema.puml`
- `docs/architecture/diagrams/generated/db-physical-schema.svg`
- `docs/operations/local-development.md`, only if migration instructions need updating

## Notes For AI Agent

- Toteuta vain tämän taskin scope.
- Älä muuta tuotantotietokantaa käsin.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Älä toteuta Event CRUDia.
- Lisää tai päivitä testit muutoksen riskin mukaan.
- Jos et lisää testejä, perustele miksi.
- Lopuksi kerro mitä muutettiin ja miten työ tarkistettiin.
