# TASK-038 Automatic Deployment Migrations

## Source Plan

Approved plan: make staging and production schema migration execution automatic
and deployment-safe while keeping the backend release artifact and migration
command portable across hosting providers.

The backend release image will contain the migration runner and paired SQL
migrations. A one-shot migration job will run `python migrate.py up` before the
new backend starts. Coolify is the initial deployment target, but its
health-check exclusion and other provider-specific behavior must remain outside
application and migration-runner code.

## Goal

Provide a repeatable deployment flow in which every backend release applies all
pending migrations before the corresponding backend starts. A migration failure
must fail the new deployment visibly instead of allowing the backend to run
against an unprepared database.

Keep the release image and runtime commands provider-neutral. Replacing Coolify
or Docker Compose later may require new deployment manifests, but must not
require changes to the migration runner, SQL migrations or backend application
code.

## Requirements

- As the first implementation step, add a deployment ADR that:
  - supersedes only ADR-001's initial Railway deployment choice with Coolify for
    the current staging and production baseline, without rewriting ADR-001's
    historical decision
  - records Docker Compose as the initial Coolify deployment topology
  - records that Coolify does not guarantee rolling updates for Docker
    Compose deployments
  - defines the portable release-image and migration-command contract
  - identifies every Coolify-specific Compose property and the intended
    provider-switch boundary
  - defines migration failure, application rollback and database rollback
    behavior
- Keep the current local development workflow separate from production/Coolify
  deployment configuration. Do not add production-only lifecycle behavior to
  normal `docker compose up backend` development startup.
- Build the production backend image from a context that can access both
  `backend/` and `db/migrations/` without copying or duplicating migration SQL
  into another source directory.
- Add a production backend image target that:
  - installs only runtime dependencies
  - contains `backend/migrate.py`, `backend/app/` and all paired files from
    `db/migrations/`
  - uses a deterministic internal filesystem layout in which migration
    discovery is independent of the process working directory
  - provides a production API command instead of the development server
  - provides a portable backend health check without adding a project
    dependency
- Use the same immutable backend release artifact for the API service and the
  migration job. They may use different commands but must not be built from
  different application or migration contents.
- Add provider-neutral production Compose wiring that defines:
  - a one-shot migration service with command `python migrate.py up`
  - the backend dependency on successful migration completion using
    `condition: service_completed_successfully`
  - a required `DATABASE_URL` without a development or production fallback
  - no bind mounts for backend code or migration SQL
  - no automatic execution of down migrations
- If PostgreSQL is part of the production Compose stack, give it a readiness
  health check and require `service_healthy` before migration execution. If the
  production database is external, do not add a fictitious Compose database
  dependency; connection failure must fail the migration job and deployment.
- Add the thinnest practical Coolify-specific Compose layer or manifest:
  - set `exclude_from_hc: true` only on the completed migration job
  - keep Coolify-specific keys out of provider-neutral Compose configuration
    when the supported Compose/Coolify file composition mechanism permits it
  - document any unavoidable non-standard property clearly
- Do not embed Coolify-generated environment variable names, resource UUIDs,
  host filesystem paths, deployment API calls or Coolify networking assumptions
  in backend or migration-runner code.
- Preserve the migration runner's existing PostgreSQL advisory lock as the
  concurrency control. Do not add a provider-specific distributed lock.
- Define and document an expand/contract deployment policy:
  - schema expansion and required backfill happen before code depends on the
    new shape
  - application code remains compatible with the transitional schema
  - destructive cleanup is deferred to a later release after old code and its
    rollback window are gone
- Do not automatically run a down migration when a migration, backend health
  check, deployment or application rollback fails. Application rollback leaves
  successfully applied forward migrations in place.
- Add a one-time adoption procedure for each existing target database:
  - inspect migration history before enabling automatic execution
  - take a backup appropriate to the environment
  - verify the database schema level
  - manually run the existing explicit `baseline NNN` command only when the
    non-empty database has no tracked migration history
  - never infer or automatically baseline an existing database
- Ensure deployment logs expose migration filenames, success/no-op outcomes and
  failures without exposing `DATABASE_URL` or database credentials.
- Do not add a new Python, system or deployment-tool dependency.

## Acceptance Criteria

- [ ] A deployment ADR supersedes ADR-001's Railway deployment choice before
      deployment implementation and records Coolify as the current provider
      without making it an application runtime dependency.
- [ ] Local development Compose behavior remains available without running
      migrations automatically as part of backend startup.
- [ ] The production backend image builds from repository-tracked sources and
      contains the runner module, entry point and every paired SQL migration.
- [ ] Running `python migrate.py up` in the built production image discovers
      migrations without bind mounts and without depending on the invocation
      directory.
- [ ] The production API and migration services use the same release artifact
      and receive the same required `DATABASE_URL` contract.
- [ ] A successful migration job allows the backend to start.
- [ ] A failed migration job exits nonzero, prevents the new backend from
      starting and remains visible as a failed deployment.
- [ ] An already-current database produces a successful no-op migration job and
      allows the backend to start.
- [ ] Concurrent migration jobs remain safe through the existing PostgreSQL
      advisory lock.
- [ ] Coolify excludes only the one-shot migration job from aggregate health
      checks, while the backend has a functioning health check.
- [ ] Provider-specific fields are isolated and documented; the built image can
      run its API and migration commands using plain Docker without Coolify.
- [ ] No automatic down migration is configured for any failure or rollback
      path.
- [ ] Existing untracked staging or production databases have a documented,
      manual verification and baseline gate before automation is enabled.
- [ ] Deployment and migration logs do not expose database credentials.
- [ ] No new dependency is added.
- [ ] Architecture, deployment, migration and operator documentation agree with
      the implemented flow and do not claim rolling or zero-downtime behavior
      for Coolify Docker Compose deployments.

## Out Of Scope

- Changing migration SQL or the logical/physical application data model.
- Changing migration history validation, checksum handling, transactions,
  advisory locking, baselining rules or latest-only down behavior.
- Automatically selecting or inferring a baseline version.
- Automatically rolling back database migrations.
- Claiming or implementing zero-downtime or rolling deployment for the Coolify
  Docker Compose topology.
- Deploying, modifying or baselining a real staging or production database as
  part of repository implementation or automated tests.
- Creating Coolify resources, secrets, domains or production releases through
  the Coolify UI or API.
- Migrating to a second provider in this task.
- Adding Kubernetes, ECS or another provider's deployment manifests.
- Frontend application behavior or domain/API behavior changes.
- Adding new schema migrations or seed data.

## Implementation Notes

- Read these sources before implementation:
  - `AGENTS.md`
  - `docs/architecture/overview.md`
  - `docs/archive/process/AI-DEVELOPMENT-WORKFLOW.md`
  - `docs/adr/0001-tech-stack.md`
  - `docs/adr/0002-database-migrations.md`
  - `docs/architecture/data/DATABASE.md`
  - `db/migrations/README.md`
  - `docs/operations/local-development.md`
  - `docs/operations/testing.md`
  - this task
- The current backend build context is `./backend`, but migration SQL is under
  repository-root `db/migrations/`. Change the production build context and
  Dockerfile copy paths together; do not create a second migration directory.
- The current migration path is derived from the source-file location. Preserve
  a repository-like image layout or replace that derivation with an equally
  deterministic packaged-runtime path. Do not make arbitrary operator-provided
  SQL paths executable.
- Keep the local development image target and bind-mount workflow functional
  when adding a production target.
- Use only standard Docker/Compose behavior in the portable contract:
  image, command, environment, health check and dependency completion.
- Coolify's `exclude_from_hc` field is provider-specific. Validate the actual
  manifest through Coolify in addition to validating its standard Compose
  portions locally.
- Treat Compose deployment as potentially disruptive. Backward-compatible
  migrations are still mandatory for safe rollback and future deployment
  topologies, not because Coolify promises overlapping Compose containers.
- A provider replacement should need only an equivalent pre-release job or
  init-step that executes `python migrate.py up`, propagates failure, injects
  `DATABASE_URL` and starts/promotes the API after success.

## Testing

Required:

- [ ] Backend unit tests
- [ ] PostgreSQL migration integration tests
- [ ] Container image build
- [ ] Compose configuration verification
- [ ] Disposable end-to-end migration/startup verification
- [ ] Coolify staging deployment rehearsal
- [ ] Manual portability verification with plain Docker
- [ ] Documentation verification
- [ ] Backend lint
- [ ] Backend typecheck

Not applicable:

- [ ] Frontend tests: no frontend behavior changes.
- [ ] Frontend lint: no frontend source changes.
- [ ] Frontend build: frontend packaging is outside this task unless required
      by the selected whole-stack deployment manifest.
- [ ] Production deployment: human approval is required and this task does not
      authorize a production release.
- [ ] Schema migration SQL verification: no migration SQL changes are allowed.

Verify at least these scenarios against disposable PostgreSQL:

- fresh database applies the complete chain before backend startup
- already-current database succeeds as a no-op before backend startup
- invalid migration history or checksum drift fails the job and blocks backend
- failing migration SQL leaves the failing migration atomic and blocks backend
- two concurrent migration jobs serialize through the advisory lock
- image invocation from a working directory other than the backend directory
  still discovers only packaged repository migrations
- plain Docker can run both the production API command and migration command
  without Coolify or bind mounts

Commands should include the existing backend checks and the final commands
selected for the production image and Compose manifests:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright

# From the repository root; use the filenames established by this task.
docker build --target <production-target> -f backend/Dockerfile .
docker compose -f <production-compose-file> config
```

Do not point destructive or baseline verification at a developer's normal
database or any staging/production database.

## Documentation

Update:

- a new deployment ADR under `docs/adr/`
- `docs/architecture/overview.md` with the accepted deployment topology and explicit
  migration job
- `README.md` where it identifies Railway as the initial staging target
- `docs/operations/local-development.md` if Dockerfile/build-context changes affect local
  commands or mounts
- `docs/operations/testing.md` with production image, Compose and deployment-migration
  verification
- `docs/architecture/data/DATABASE.md` with automatic-up deployment behavior, manual
  baseline gate and no-automatic-down policy
- `db/migrations/README.md` with expand/contract and deployment rollback rules
- deployment/operator documentation for Coolify configuration, staging
  rehearsal, migration failure diagnosis and provider portability
- relevant PlantUML sources and generated SVGs if the deployment or workflow
  topology is represented in `docs/architecture/diagrams/`

No domain, concept, logical data-model or physical schema diagram update is
required because this task does not change application data or schema.

## Notes For AI Agent

- Lue `AGENTS.md` ja `docs/architecture/overview.md` ennen toteutusta.
- Lue relevantit ADR:t sekä deployment-, database- ja testing-dokumentaatio
  ennen muutoksia.
- Luo deployment-ADR ennen Dockerfile- tai Compose-toteutusta; älä kirjoita
  ADR-001:n historiallista päätöstä uudelleen.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Älä muuta olemassa olevien migraatioiden sisältöä.
- Älä aja komentoja staging- tai production-tietokantaa vasten.
- Älä luo tai muuta ulkoisia Coolify-resursseja ilman erillistä ihmisen
  valtuutusta.
- Älä tee production deploymentia.
- Lisää tai päivitä testit, kun muutos koskee sovelluskoodia tai
  migraatiopolun käyttäytymistä.
- Jos et lisää testejä sovelluskoodin muutokselle, perustele miksi.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
