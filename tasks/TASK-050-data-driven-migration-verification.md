# TASK-050 Data-Driven Migration Verification

## Source Plan

Approved plan: "Make Migration Verification Data-Driven". Replace the stale
hard-coded production-image migration count with a comparison against the
repository migration set, and make repository-tip expectations in migration
integration tests derive from discovered migrations.

## Goal

Keep migration packaging and integration checks accurate when a new paired
migration is added. CI must verify that the immutable production backend image
contains precisely the repository migrations without requiring a manual count
update.

## Requirements

- Update the `Verify packaged migrations` step in `.github/workflows/ci.yml`.
  Derive the ordered up-migration filenames from `db/migrations/`, pass the
  expected sequence into the production-image container, and compare it with
  `discover_migrations()` output.
- Preserve the existing image checks: migration discovery must work from
  `/tmp`, `pytest` must not be installed in the runtime image, and the process
  UID and GID must both be `10001`.
- The CI comparison must fail if the image omits a checked-in migration,
  includes an unexpected up migration, or contains invalid migration pairs.
- In `backend/tests/test_migrations_integration.py`, derive the repository's
  current latest migration version and count from `discover_migrations()`
  instead of hard-coding the current terminal version (`013`).
- Keep the existing explicit-baseline scenario, but baseline to the discovered
  latest version and assert that the recorded history contains the discovered
  migration count.
- Keep the version-eight compatibility fixture and version-nine test scenarios.
  After upgrading the fixture, assert the latest discovered version; in the
  down-scope scenario, roll migrations back dynamically from the latest version
  through `009` so the test remains valid when later migrations are added.
- Preserve fixed historical versions `008` and `009`, because they define the
  compatibility scenario rather than the changing repository-tip state.
- Add no dependency, migration SQL, Dockerfile, application behavior, or
  documentation change.

## Acceptance Criteria

- [ ] The production image built in CI passes packaged-migration verification
      with the current migration chain `001` through `013`.
- [ ] Packaged-migration verification automatically covers a subsequently
      added paired migration without editing an expected numeric count.
- [ ] The check fails when the built image's ordered up-migration filenames do
      not match the repository's ordered up-migration filenames.
- [ ] The runtime image remains free of `pytest`, runs as UID/GID `10001`, and
      discovers migrations when invoked from `/tmp`.
- [ ] The explicit-baseline integration test uses the discovered latest
      migration version and migration count.
- [ ] The version-eight upgrade integration test reaches the discovered latest
      migration version, and the version-nine down-scope test rolls back to the
      version-eight boundary without listing each newer migration by filename.
- [ ] Relevant backend tests and CI checks pass.

## Out Of Scope

- Changes to migration SQL, migration discovery rules, checksums, transactions,
  advisory locking, baseline semantics, or down-migration policy.
- Dockerfile, dependency, runtime-user, backend API, database schema, domain,
  architecture, deployment, or documentation changes.
- Replacing fixed versions that intentionally define the historical
  version-eight/version-nine migration-compatibility scenario.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
tasks/TASK-050-data-driven-migration-verification.md
tasks/TASK-038-automatic-deployment-migrations.md
docs/decisions/ADR-002-database-migrations.md
docs/decisions/ADR-005-production-only-environments.md
db/migrations/README.md
docs/TESTING.md
```

- The source migration list is the repository-root `db/migrations/` directory;
  do not duplicate it or make migration discovery depend on an operator-provided
  path.
- Compare ordered filenames, not merely a derived count. `discover_migrations()`
  remains responsible for validating paired filenames and contiguity inside the
  container.
- Derive the latest integration-test version from the final element of
  `discover_migrations()` and the expected history count from its length.
- Retain the existing test names unless a small rename materially improves
  their accuracy after removing the repository-tip assumption.

Suggested branch:

```text
fix/TASK-050-data-driven-migration-verification
```

## Testing

Required:

- [ ] Backend unit tests
- [ ] PostgreSQL migration integration tests
- [ ] Production backend image build
- [ ] Packaged-migration Docker verification
- [ ] CI workflow/job verification

Not applicable:

- [x] Frontend tests, lint and build: no frontend change.
- [x] Backend lint and typecheck: no production Python source or type surface
      changes; run only if the test-only change warrants the full backend gate.
- [x] Manual UI verification: no user-visible behavior changes.
- [x] Documentation verification: no documentation changes are in scope.

Commands:

```bash
# Disposable PostgreSQL configuration is required; see docs/TESTING.md.
cd backend
uv run pytest tests/test_migrations.py tests/test_migrations_integration.py

# From repository root, build and execute the same verification command used
# by the CI workflow.
docker build --target production -t schatten-backend:local -f backend/Dockerfile .
```

## Documentation

No documentation update is expected. Update documentation only if the
implementation changes the recorded production-image or migration-runner
contract, which is out of scope for this task.

## Notes For AI Agent

- Implement only this task's CI and test-verification scope.
- Do not add dependencies or alter production application code.
- Do not modify existing migration SQL files.
- Keep the production image and migration runner portable and working-directory
  independent.
- Report the exact checks run and whether disposable PostgreSQL integration
  coverage was available.
