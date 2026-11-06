# TASK-059C Shared Reference Data And Production Seed Command

## Source Plan

The approved UpCloud/Caddy/direct-Entra amendment is recorded in
[ADR-013](../../adr/0013-shared-entra-local-https-deployment.md).
The initial host is Ubuntu 26.04 LTS with private Docker PostgreSQL 18 and
required daily encrypted on-server backups in `/opt/postgres-backups` with
7-day retention (G/E/F).
These CLI contracts remain database-only and provider-neutral.

Approved deployment plan and explicit amendment: production receives the same
seed as `db/init/002_seed_development_data.sql`, except all user inserts.
This file specifies future work only.

Dependency: [TASK-059A](TASK-059A-shared-entra-local-https-architecture.md).

## Goal

Provide `python -m app.seed_reference_data` in the immutable backend image,
sharing the development seed's default metamodel data and insertion logic while
guaranteeing that production initialization does not create development users.

## Requirements

- Extract shared metamodel-only SQL from the existing development seed. Preserve
  the exact existing `db/init/metamodel_state_##default##.json` source and all
  mappings, including JSON version, node/edge types, attributes, and allowed
  connections. Maintain one source of truth, not two copied seed implementations.
- Keep the existing idempotent development-user inserts solely in the development
  wrapper, within its transaction. Preserve current local seeding entrypoints.
- Both callers supply JSON through a transaction-local PostgreSQL setting; the
  shared SQL reads that value. Use parameterized input, existing Psycopg, and
  packaged file reads for the Python CLI, without psql or shell file execution.
- Package only the required reference SQL and JSON with the production backend
  image. Resolve paths independently of the invoking working directory; preserve
  non-root execution and exclude dev seed-user execution from the production CLI.
- Run all reference inserts atomically with serialization against concurrent
  reference seed runs, including callers through the development wrapper.
- Insert one complete default metamodel only when no active default exists.
  If an active default exists, succeed without changing its version/content or
  attempting to repair/overwrite it. Preserve current constraints and semantics.
- Require migrations first. Do not run migrations, baseline, seeding, or bootstrap
  implicitly at API/worker startup. The CLI needs only DATABASE_URL and must not
  initialize FastAPI/OIDC or depend on public-origin/session settings.
- Insert no users, identities, sessions, organisations, scenarios, or sample
  business records. Preserve existing nullable reference-data audit fields.
- Exit nonzero on failure, roll back partial seed data, and emit credential-safe
  success/no-op/failure output without DATABASE_URL or source payload dumps.

## Acceptance Criteria

- [ ] Production and development metamodel datasets match semantically, including
      relationships and all mapped fields, ignoring generated IDs/timestamps.
- [ ] A fresh migrated production-style database receives the reference data
      while its users and other business tables remain empty.
- [ ] Local development seeding still creates its two existing development users.
- [ ] Repeated/concurrent reference seed calls create no duplicates; an existing
      active default is unchanged and failure leaves no partial new default.
- [ ] The command runs as the production image user with database settings alone,
      including invocation from a different working directory.
- [ ] Production artifact verification and local Make/psql seeding still work.
- [ ] No schema migration or production database operation is performed by this task.

## Out Of Scope

- Updating the default JSON content, metamodel merge/repair/version upgrades,
  deleting reference data, creating users, or implementing admin bootstrap.
- Public API changes, schema changes, new dependencies, automatic deploy seeding,
  production seed execution, or production database restoration.

## Implementation Notes

Read `AGENTS.md`, `docs/architecture/overview.md`, A's amendment, ADR-002/003,
`docs/architecture/domains/ORG_TWIN_STRUCTURE.md`, `docs/architecture/concepts/METAMODEL.md`,
`docs/architecture/data/DATA-MODEL.md`, `docs/architecture/data/DATABASE.md`, `db/init/README.md`,
`db/migrations/README.md`, and `docs/operations/testing.md`. Reuse database-only patterns
from the migration runner without altering its migration-history contract.
Account for local Compose's init-directory mount and Makefile's stdin-based
psql invocation when locating the extracted shared SQL.

## Testing

Required: disposable PostgreSQL integration tests for parity, untouched users,
idempotency, concurrency, existing-default preservation, and rollback after an
injected failure; CLI failure/redaction tests; production image packaging checks.
Use the existing MIGRATION_TEST_DATABASE_URL harness and CI PostgreSQL service.

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
cd ..
docker build --target production -t shadow-backend:local -f backend/Dockerfile .
```

Run the CLI from that image against a migrated disposable database with only
DATABASE_URL supplied. Verify the local development wrapper separately.
Frontend tests are not applicable: no frontend behavior changes.

## Documentation

Update `db/init/README.md`, `docs/architecture/data/DATABASE.md`, `backend/README.md`,
`docs/architecture/deployment.md`, `docs/operations/local-development.md`, and `docs/operations/testing.md` as relevant.
Clearly distinguish approved production reference data from local development
users. Document explicit ordering and no-op behavior; do not claim rollout occurred.

## Notes For AI Agent

- Implement only when requested and use disposable data for verification.
- Preserve the approved shared SQL/JSON source and do not add schema changes.
- Record eventual Step 13 reviews under `docs/ai-reviews/TASK-059C/` and report checks.
