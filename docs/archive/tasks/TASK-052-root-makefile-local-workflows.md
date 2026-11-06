# TASK-052 Root Makefile for Local Workflows

## Source Plan

Developer-approved plan: add one repository-root Makefile as a safe, local
developer convenience interface over the existing Docker Compose, uv, pnpm and
project-script workflows. The Makefile must preserve the documented underlying
commands as the source of truth, avoid new dependencies, and keep production
and destructive operations out of its interface.

## Goal

Provide a discoverable, consistent `make <target>` interface from the
repository root for common dependency installation, frontend/backend checks,
and safe local runtime workflows. Developers must be able to find the supported
commands through `make` or `make help` without changing application behavior,
CI contracts, deployment behavior or local data unexpectedly.

## Requirements

- Add one root-level `Makefile`; do not add component-specific Makefiles.
- Make `help` the default target and group its output by installation,
  validation, local runtime and local verification. Each state-changing target
  must make its local-only behavior or prerequisite clear.
- Add explicit installation targets that delegate to the existing tools:
  - `backend-install` runs `uv sync` in `backend/`;
  - `frontend-install` runs lockfile-respecting `pnpm install` in `frontend/`;
  - `install` runs both installation targets.
- Add validation targets preserving the current canonical commands:
  - backend: `backend-lint`, `backend-test`, `backend-typecheck`, and
    `backend-check`;
  - frontend: `frontend-lint`, `frontend-test`, `frontend-build`, and
    `frontend-check`;
  - `check` runs both component check targets.
- Do not make validation targets install dependencies implicitly. Missing host
  prerequisites or dependencies must fail through the underlying tool command.
- Add focused safe local-runtime targets:
  - `dev-init` copies `.env.example` to `.env` only when `.env` is absent, then
    invokes the existing non-overwriting local Authentik setup script;
  - `db-up` starts the application database;
  - `migrate` runs the existing migration runner with the local `.env` file;
  - `seed` applies the documented idempotent development seed after migrations;
  - `dev-up` executes the documented full local bootstrap in order: initialize
    local configuration, start database and Authentik prerequisites, migrate,
    seed, then start the complete stack detached;
  - `dev-down` stops the local Compose stack while retaining volumes;
  - `preview-up`, `diagrams`, `auth-smoke`, and `auth-verify` wrap the existing
    documented local preview, diagram rendering, Authentik smoke and Authentik
    configuration-verification commands.
- Mark operational targets phony. Ensure `dev-up` cannot race dependent
  startup, migrations or seeding when Make is invoked with parallel execution.
- Keep the Compose environment-file order compatible with the local Authentik
  documentation: `.env` first, then `.env.authentik.local`.
- Preserve existing direct Docker Compose, uv, pnpm and script commands in
  documentation as the source of truth. Make targets are an optional
  convenience layer.
- Do not add dependencies, alter Docker Compose files, application code,
  database schema, migrations, frontend/backend package configuration, or CI
  workflow behavior.

## Acceptance Criteria

- [ ] A root `Makefile` exists and `make` and `make help` list all supported
      targets with concise grouping and safety/prerequisite guidance.
- [ ] Explicit installation targets invoke `uv sync` and lockfile-respecting
      `pnpm install` in their respective project directories; checks do not
      install dependencies automatically.
- [ ] Each backend and frontend validation target delegates to its current
      documented command, and `make check` executes both component check
      groups.
- [ ] `dev-init` never overwrites an existing `.env` or
      `.env.authentik.local` file.
- [ ] `dev-up` follows the documented local bootstrap order and can be invoked
      safely with parallel Make execution; it starts no production resources.
- [ ] `migrate` uses the repository migration runner and `seed` uses only the
      documented local development seed after migration completion.
- [ ] `dev-down` retains local volumes, and no target exposes database reset,
      migration rollback/baseline, production deployment, Entra provisioning,
      release checks or destructive cleanup.
- [ ] Preview, diagram and Authentik verification targets use the existing
      documented local commands.
- [ ] README and contributor/local-development documentation explain the
      optional Make interface and retain direct commands as canonical.
- [ ] No application API, schema, dependency, Docker Compose definition,
      production deployment behavior or CI behavior changes.

## Out Of Scope

- Production deployment, production Compose validation, image release checks,
  Coolify operations, Entra provisioning or production smoke tests.
- Database volume removal, reset targets, migration rollback, migration
  baseline, or any other potentially destructive data operation.
- Adding GNU Make, Docker, uv, pnpm or any other tool as a managed project
  dependency.
- Replacing the existing direct commands in CI or changing CI job behavior.
- Frontend/backend application code, tests, API contracts, database schema,
  migrations, authentication behavior or architecture changes.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/archive/tasks/TASK-052-root-makefile-local-workflows.md
docs/operations/local-development.md
docs/operations/testing.md
README.md
docs/archive/process/CONTRIBUTING.md
db/init/README.md
db/migrations/README.md
```

- This is local developer tooling and documentation only; no ADR is required
  because it does not change the technology stack, architecture, runtime or
  deployment model.
- Keep target recipes thin: delegate to the exact existing commands rather
  than reproducing their logic in Make syntax.
- The local development seed is intentionally development-only and idempotent;
  do not expose it through any production-oriented target.
- Do not add a target that installs the local Authentik CA into the operating
  system trust store. That remains an explicit human-controlled step.
- Preserve command exit statuses, avoid masking failures, and do not use a
  target name that shadows a file target unintentionally.
- Document any host prerequisites such as GNU Make, Docker Compose, uv and
  pnpm without adding automated system-level installation behavior.

Suggested branch:

```text
chore/TASK-052-root-makefile-local-workflows
```

## Testing

Required:

- [ ] `make` and `make help` manual output review
- [ ] `make -n` dry-run verification of each installation, validation and
      runtime target, including `dev-up` command order
- [ ] `make install` in a prepared local development environment
- [ ] `make backend-check`, `make frontend-check`, and `make check`
- [ ] Disposable local environment verification of `make dev-up`, health
      endpoint availability, development seed availability, and `make dev-down`
- [ ] `make diagrams`, `make auth-smoke`, and `make auth-verify` where their
      documented local prerequisites are available
- [ ] Documentation review to confirm Make is optional and direct commands
      remain canonical

Not applicable:

- [x] New frontend or backend application tests: the task changes local
      developer tooling and documentation only.
- [x] Database migration verification: no schema or migration change.
- [x] Production/deployment verification: explicitly out of scope.
- [x] CI workflow execution or modification: CI behavior is unchanged.

Commands:

```bash
# Inspect supported targets and command expansion without changing state.
make
make help
make -n install backend-check frontend-check check
make -n dev-init db-up migrate seed dev-up dev-down preview-up diagrams auth-smoke auth-verify

# Run only when the corresponding local prerequisites are prepared.
make install
make check
make dev-up
curl --header 'Host: app.localhost:5173' http://localhost:8000/health
make dev-down
```

## Documentation

Update:

- `README.md`
- `docs/archive/process/CONTRIBUTING.md`
- `docs/operations/local-development.md`
- `docs/operations/testing.md` only if its command guidance needs an explicit Make
  convenience reference; do not duplicate or replace canonical direct commands.

No updates are expected for architecture, ADR, domain, concept, data-model,
database, diagram, deployment or CI documentation.

## Notes For AI Agent

- Implement only the root Makefile and the scoped local-developer documentation
  updates.
- Do not add dependencies or alter application, Docker Compose, CI,
  authentication, database, migration, deployment or external-integration
  behavior.
- Keep production, Entra, release, baseline, rollback, reset and destructive
  operations out of the Make interface.
- Keep `dev-up` ordered and failure-transparent; it must not continue to later
  bootstrap steps after an earlier one fails.
- Preserve local Authentik environment-file ordering and never overwrite local
  environment or secret files.
- Report the exact Make dry-run, validation, local-runtime and documentation
  checks run, including any unavailable local prerequisites.
