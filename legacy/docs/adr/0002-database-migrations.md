# ADR-002: Database Migration Tool

Status: Accepted

Date: 2026-08-06

---

# Context

Shadow stores schema changes as ordered PostgreSQL SQL files in
`db/migrations/`. The first eight migrations were applied manually and no
database-side history existed, so the project could not determine which
migrations were pending or safely coordinate concurrent migration attempts.

The project also needs an explicit rollback convention. Some rollback operations
are destructive, and migration 004 discarded information that cannot always be
reconstructed from the current schema.

# Decision

Shadow uses a repository-owned Python migration runner implemented with the
existing Psycopg dependency.

- Every `NNN_name.sql` up migration has a required
  `NNN_name.down.sql` counterpart.
- Migrations form one contiguous linear chain starting at `001`.
- `up` applies all pending up migrations in numeric order.
- A named down migration may run only when its up migration is the latest
  applied migration.
- The runner accepts only exact migration basenames from `db/migrations/`; it
  never executes an arbitrary path supplied by an operator.
- Applied migrations are recorded in a tool-owned `schema_migrations` table
  with version, filename, SHA-256 checksum and application timestamp.
- Recorded history must be a contiguous prefix of the repository chain and
  checksums must still match before any migration runs.
- A PostgreSQL session-level advisory lock serializes migration commands.
- Each migration SQL file and its history update run in one transaction.
- Existing databases created before the history table are adopted only through
  an explicit `baseline <version>` command. The runner does not infer migration
  state from schema objects.
- Rollback SQL is allowed to be destructive and must document material limits.
  Migration 004 may reconstruct the legacy graph relationship only when each
  affected scenario maps to exactly one organisation state; otherwise it fails
  atomically.

The migration runner is invoked explicitly. It is not run automatically during
FastAPI startup or container startup.

# Options Considered

## Alembic

Alembic provides a mature SQLAlchemy migration ecosystem, but adopting it would
add a dependency and replace or wrap the existing plain-SQL migration chain.
The current requirements are small and PostgreSQL-specific, so this was not
selected for the baseline.

## Continue Manual `psql` Execution

Manual execution preserves the existing files but cannot reliably answer which
migrations are pending, validate file drift, or serialize concurrent runners.

## Automatically Infer Existing Migration State

Schema inspection could make adoption appear automatic, but the historical
migrations include data changes and lossy transformations that cannot be
identified reliably from current database objects. Explicit baselining is safer.

## Allow Arbitrary Or Cascading Rollbacks

Running a non-latest down migration can leave newer migrations recorded against
an incompatible schema. Automatic cascading also broadens a single destructive
request. The selected policy requires explicit latest-first rollback commands.

# Consequences

Benefits:

- fresh databases can reach the current schema with one command
- migration history and file drift are auditable
- concurrent migration runs cannot interleave
- every new schema change includes an explicit rollback review
- databases created before the tool have a deliberate adoption path

Costs and constraints:

- contributors must maintain two SQL files per migration
- baselining trusts the operator's assertion that the schema matches the chosen
  version
- down migrations may lose data and are not a substitute for backups
- the custom runner must remain covered by unit and PostgreSQL integration tests
- deployment automation must invoke the runner separately if automatic
  deployment migrations are added later

# Implementation Rules

- Do not edit an already accepted up migration to fix production history; add a
  new paired migration.
- Do not log `DATABASE_URL` or credentials.
- Keep transaction control in the runner rather than individual SQL files.
- Fail closed on invalid filenames, incomplete pairs, history gaps, unknown
  records or checksum mismatches.
- Keep `schema_migrations` outside the numbered application migration chain so
  it remains available after rolling migration 001 down.
- Run destructive verification only against a disposable database or isolated
  test schema.
