# TASK-037 Database Migration Tool

## Source Plan

Approved plan: add paired rollback SQL for the existing migration chain and a
small Python/Psycopg migration runner that records applied migrations, applies
all pending migrations with `up`, and safely runs a specified `.down.sql`
migration.

This task also establishes the permanent migration-pair convention, documents
how databases created before migration tracking are adopted, and adds automated
verification for the migration lifecycle.

## Goal

Provide a repository-owned migration tool for applying Schatten's versioned
PostgreSQL migrations in a repeatable and auditable way.

Every up migration must have a reviewed down counterpart. Existing databases
must be adoptable explicitly without replaying already-applied SQL, while fresh
databases must be able to apply the complete migration chain automatically.

## Requirements

- As the first implementation step, add down counterparts for all existing
  migrations:
  - `001_create_core_schema.down.sql`
  - `002_add_org_state_name_and_org_name_unique_index.down.sql`
  - `003_alter_scenario_target_dates_not_null.down.sql`
  - `004_alter_graphs_to_scenarios.down.sql`
  - `005_add_graph_logical_delete_dates.down.sql`
  - `006_create_customers.down.sql`
  - `007_create_contacts.down.sql`
  - `008_create_customer_addresses.down.sql`
- Each down migration must reverse the schema changes made by the up migration
  with the same stem and use dependency-safe ordering.
- Keep rollback SQL strict: unexpected schema drift must fail visibly instead
  of being silently ignored.
- Migration 004 rollback must:
  - recreate the legacy `graphs` schema and indexes
  - map current graph nodes and edges back through an organisation state only
    when every affected scenario has exactly one organisation state
  - fail before making changes if the lost association cannot be inferred
    unambiguously
  - run atomically so a failed inference leaves the schema and data unchanged
- Add an ADR for the repository-owned Python/Psycopg migration runner before
  implementing the runner itself.
- Add an executable Python entry point at `backend/migrate.py` and keep its
  testable implementation under `backend/app/core/`.
- Use the existing Psycopg dependency and existing `DATABASE_URL`
  configuration. Do not add a migration framework or another dependency.
- Support these commands from the repository root:

  ```bash
  uv run --project backend python backend/migrate.py up
  uv run --project backend python backend/migrate.py 008_create_customer_addresses.down.sql
  uv run --project backend python backend/migrate.py baseline 008
  ```

- `up` must discover valid up migrations, compare them with database history,
  and apply every pending migration in ascending numeric order.
- A `.down.sql` argument must be an exact basename from `db/migrations/`.
  Reject paths, traversal attempts, malformed names, unknown files and version
  shorthand.
- Permit a down migration only when its matching up migration is the latest
  applied migration. Reject unapplied or non-latest targets without changing
  the database.
- Validate the migration directory before execution:
  - up names follow `NNN_lowercase_snake_case.sql`
  - down names follow `NNN_lowercase_snake_case.down.sql`
  - every up migration has exactly one matching down migration
  - versions are unique, contiguous and start at `001`
- Create and maintain a tool-owned `schema_migrations` table containing:
  - integer migration version as the primary key
  - unique up-migration filename
  - SHA-256 checksum of the up-migration contents
  - application timestamp with time zone
- Treat recorded migration history as valid only when it is a contiguous prefix
  of the repository migration chain. Reject unknown records, missing records,
  renamed files and checksum drift before running migration SQL.
- Protect each command with a PostgreSQL session-level advisory lock so two
  migration runners cannot modify the same database concurrently.
- Execute each migration and its history-table update in one transaction.
  Earlier successfully committed up migrations may remain applied if a later
  pending migration fails, but the failing migration must leave no partial
  schema or history changes.
- A repeated `up` with no pending migrations must succeed as a no-op.
- On a genuinely empty database, `up` must create the history table and apply
  the migration chain normally.
- If non-tool schema objects exist but migration history does not, `up` must
  fail with guidance to use `baseline` instead of replaying migrations.
- `baseline <version>` must:
  - accept a known three-digit migration version
  - be allowed only when migration history is empty and non-tool schema objects
    already exist
  - record every migration from `001` through the selected version, including
    current checksums, without executing migration SQL
  - clearly state that the operator is asserting the schema already matches the
    selected migration level
- Keep `schema_migrations` present and empty after migration 001 is rolled back.
- Print concise migration filenames and outcomes without printing database
  credentials. Return a nonzero process exit code for validation, history,
  connection or SQL failures.
- Add PostgreSQL-backed integration coverage to CI using PostgreSQL 18.
- Update project documentation and agent guidance so every future up migration
  must always include its matching `.down.sql` migration.

## Acceptance Criteria

- [x] Down migrations exist for migrations 001 through 008 and each filename
      exactly matches its up migration plus the `.down.sql` suffix.
- [x] Applying migrations 001 through 008 to an empty PostgreSQL database with
      `up` succeeds and creates correct history records.
- [x] Running `up` again succeeds without executing already-applied SQL.
- [x] Rolling migrations down from 008 through 001 in reverse order succeeds,
      removes the corresponding history records, and permits the entire chain
      to be reapplied.
- [x] A requested down migration is rejected unless it is the latest applied
      migration.
- [x] Arbitrary paths, malformed filenames, missing migration pairs, numbering
      gaps and duplicate versions are rejected before SQL execution.
- [x] Applied migration checksum or filename drift is detected and blocks both
      up and down operations.
- [x] A SQL failure rolls back that migration's schema and history changes.
- [x] Concurrent runners are serialized by an advisory lock.
- [x] An existing untracked schema is not modified by `up` and receives clear
      baseline guidance.
- [x] `baseline 008` records migrations 001 through 008 without executing them,
      after which `up` is a no-op.
- [x] Migration 004 rollback restores the legacy shape when graph-to-org-state
      mapping is unambiguous.
- [x] Migration 004 rollback fails atomically when an affected scenario has zero
      or multiple organisation states.
- [x] Logs and errors do not expose database credentials.
- [x] No new project dependency is added.
- [x] The migration policy, commands, baseline procedure, rollback limitations
      and destructive-data warning are documented.
- [x] CI runs the PostgreSQL migration integration tests alongside backend lint,
      tests and type checking.

## Out Of Scope

- Automatically running migrations during backend startup.
- Railway, staging or production deployment automation.
- Inferring an existing database's migration level automatically.
- Allowing arbitrary or non-latest migrations to be rolled back.
- Cascading automatically through multiple down migrations from one target.
- Editing the contents of already accepted up migrations 001 through 008.
- Changing application domain behavior, API behavior or the logical data model.
- Running development seed data as part of the migration tool.
- Adding Alembic or another third-party migration framework.

## Implementation Notes

- Read these sources before implementation:
  - `AGENTS.md`
  - `ARCHITECTURE.md`
  - `docs/decisions/ADR-001-tech-stack.md`
  - `docs/data/DATABASE.md`
  - `db/migrations/README.md`
  - `db/init/README.md`
  - `docs/LOCAL-DEVELOPMENT.md`
  - `docs/TESTING.md`
  - this task
- Implement the down SQL files before the Python runner, as required by the
  approved plan.
- Create `docs/decisions/ADR-002-database-migrations.md` after the down files and
  before runner implementation. Record the custom runner, paired SQL convention,
  migration ledger, checksums, transaction boundary, advisory locking,
  baselining and latest-only rollback rule.
- Keep SQL files free of `BEGIN` and `COMMIT`; the runner owns the transaction.
- Resolve migration files from the repository's `db/migrations/` directory, not
  from the process working directory.
- Use only trusted repository migration files as executable SQL. Never accept an
  arbitrary path from the CLI.
- Use a session-level advisory lock for the full command and release it in a
  `finally` path or by closing the connection.
- Create the history table as runner infrastructure rather than as a numbered
  domain migration. It remains after the application schema is rolled back.
- For migration 004, document that the original graph metadata and association
  were discarded by the existing up migration and cannot be reconstructed
  exactly. Use a deterministic replacement only for the approved unambiguous
  case; do not guess when multiple mappings are possible.
- Integration tests should use an isolated temporary PostgreSQL schema or
  database and must clean up only resources created by the test suite.
- Do not use a developer's normal local schema as a destructive test target.
- The migration ledger is infrastructure metadata. Add it to the physical
  database documentation and diagram, but do not add it to domain or logical
  data-model documentation.

## Testing

Required:

- [x] Backend unit tests
- [x] PostgreSQL integration tests
- [x] Manual migration verification
- [x] Migration SQL verification
- [x] Documentation verification
- [x] Diagram generation verification
- [x] Lint
- [x] Typecheck
- [x] CI workflow validation

Not applicable:

- [x] Frontend tests: no frontend behavior changes.
- [x] Frontend build: no frontend source or build configuration changes.
- [x] Backend build: the change adds a command-line tool rather than a separate
      application build artifact.

Unit-test at least:

- migration discovery, matching and numeric ordering
- duplicate versions, gaps and missing pairs
- filename and path validation
- CLI parsing and error exit codes
- applied-history prefix and checksum validation
- latest-only down selection
- empty and untracked database classification logic

PostgreSQL integration-test at least:

- fresh `up` through migration 008
- repeated no-op `up`
- full reverse rollback followed by full reapply
- history updates on successful up and down operations
- transaction rollback after failing SQL
- explicit adoption with `baseline 008`
- rejection of untracked existing schemas by `up`
- rejection of non-latest and unapplied down migrations
- migration 004 unambiguous success and ambiguous atomic failure
- serialization of concurrent runners

Commands:

```bash
docker compose up -d database

cd backend
uv run ruff check .
uv run pytest
uv run pyright

cd ..
docker compose --profile docs run --rm diagram-renderer
git diff --check
git status --short
```

Manual verification must use a disposable database or isolated test schema and
exercise:

```bash
uv run --project backend python backend/migrate.py up
uv run --project backend python backend/migrate.py 008_create_customer_addresses.down.sql
uv run --project backend python backend/migrate.py up
```

## Documentation

Update:

- `AGENTS.md` with the mandatory up/down migration-pair rule.
- `ARCHITECTURE.md` to replace the migration-tool TBD status.
- `README.md` with the primary migration command.
- `CONTRIBUTING.md` with the contributor-facing migration-pair requirement.
- `docs/LOCAL-DEVELOPMENT.md` with up, down and baseline usage, replacing the
  manual migration command list.
- `docs/TESTING.md` with migration runner and PostgreSQL integration checks.
- `docs/data/DATABASE.md` with the runner, migration ledger and rollback policy.
- `db/migrations/README.md` with naming, pairing, validation, ordering,
  destructive rollback and command conventions.
- `db/init/README.md` so migrations are run through the tool before development
  seed data.
- `tasks/TASK-TEMPLATE.md` so future schema tasks require an up/down pair.
- `docs/diagrams/db-physical-schema.puml` with the infrastructure migration
  ledger.
- `docs/diagrams/generated/db-physical-schema.svg` regenerated from PlantUML.
- `.github/workflows/ci.yml` with PostgreSQL 18-backed migration integration
  testing.
- `docs/decisions/ADR-002-database-migrations.md` with the accepted migration
  strategy.

No domain or concept documentation update is required because this task does
not change domain meaning, ownership, invariants or lifecycle. No logical data
model update is required because `schema_migrations` is infrastructure metadata.

## Notes For AI Agent

- Read `AGENTS.md`, this task, `ARCHITECTURE.md`, ADR-001, the new ADR-002 once
  created, database documentation, migration/init instructions and
  `docs/TESTING.md` before implementing the relevant stage.
- Implement only this task's scope and preserve the required implementation
  order.
- Do not edit existing up migrations 001 through 008.
- Do not add dependencies without separate developer approval.
- Do not execute destructive verification against a non-disposable database.
- Do not change production or staging databases.
- Update tests and documentation as specified.
- Report the exact verification commands and results when implementation is
  complete.
