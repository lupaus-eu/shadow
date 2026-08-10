# ADR-003: Coolify Deployment And Release Migrations

Status: Accepted

Date: 2026-08-06

---

# Context

ADR-001 selected Railway for the initial staging deployment and explicitly left
the long-term deployment target open. Schatten now needs the same containerized
release flow for staging and production, including automatic execution of the
repository-owned migration runner introduced by ADR-002.

The deployment must fail closed when a migration fails. At the same time, the
application image and migration command should remain usable if the hosting
provider changes. Coolify supports Git-backed Docker Compose deployments and a
provider-specific `exclude_from_hc` property for completed one-shot services.
Coolify does not guarantee rolling updates for Docker Compose deployments.

# Decision

Coolify supersedes ADR-001's initial Railway deployment choice for the current
staging and production baseline. ADR-001 remains the historical source for the
technology-stack decision.

Schatten uses a Docker Compose deployment on Coolify with these boundaries:

- A production backend image is built from repository-root context and contains
  the backend application, migration runner and repository SQL migrations.
- The image exposes two provider-neutral commands: the default production API
  command and `python migrate.py up` for a one-shot release migration.
- API and migration services use the same immutable image and `DATABASE_URL`.
- The backend starts only after the migration service exits successfully.
- The backend has an image-level HTTP health check. The migration service
  disables that long-running health check and is excluded from Coolify's
  aggregate health checks with `exclude_from_hc: true`.
- Standard production Compose configuration is kept separate from the thin
  Coolify-specific manifest. Application and migration-runner code contain no
  Coolify API, generated variable, resource UUID, host path or networking
  dependency.
- The Coolify manifest uses its predefined resource UUID and source commit only
  to assign both services one collision-resistant, commit-specific image tag.
- The production image runs as an unprivileged numeric user and group.
- PostgreSQL is external to the application Compose stack. Database readiness
  is therefore represented by successful migration-runner connection rather
  than a fictitious local database dependency.

The release migration is forward-only automation:

- migration failure prevents the new backend from starting
- successfully applied migrations remain applied if a later migration or
  application health check fails
- application rollback does not automatically run a down migration
- existing untracked databases require operator verification, backup and an
  explicit `baseline NNN` before automatic deployments are enabled
- schema changes use expand/contract releases so destructive cleanup happens
  only after older application code and its rollback window are gone

Compose deployment can be disruptive. The selected topology does not claim
rolling or zero-downtime deployment.

# Portable Provider Contract

A replacement provider needs to support only these release operations:

1. inject `DATABASE_URL` into the immutable backend image
2. run `python migrate.py up` once per release and propagate a nonzero exit
3. start or promote the image's API command only after migration success
4. evaluate the image's backend health check

The provider may implement this contract with Compose completion dependencies,
a release command, an init container or a deployment job. ADR-002's PostgreSQL
advisory lock remains the concurrency control.

# Options Considered

## Keep Railway

Railway was the initial staging choice, but the approved deployment baseline is
now Coolify for both staging and production.

## Run Migrations In FastAPI Startup

This would couple every application process and restart to schema mutation,
make failure ownership less clear and conflict with ADR-002's explicit runner
model. It was rejected.

## Build A Separate Migration Image

A separate image could drift from the API release's code or migration files.
Using one immutable release artifact provides a stronger version boundary.

## Automatically Roll Back On Deployment Failure

Down migrations can destroy data and an application rollback does not imply
that reverting committed schema is safe. Automated down migration was rejected.

# Consequences

Benefits:

- backend startup is gated by the exact release's pending migrations
- failed migrations fail the deployment visibly
- the image and migration command remain portable outside Coolify
- concurrent deployments remain serialized by PostgreSQL
- provider-specific configuration has a small, documented boundary

Costs and constraints:

- Coolify Compose deployments may have downtime
- staging and production databases need a one-time migration-history preflight
- destructive schema changes require multiple expand/contract releases
- switching away from Compose requires new provider manifests or job wiring
- Coolify manifest validation requires Coolify because `exclude_from_hc` is not
  part of the standard Compose specification

# Implementation Rules

- Do not add provider-specific behavior to application startup.
- Do not put secrets or development database fallbacks in production Compose.
- Do not duplicate `db/migrations/` into another repository source directory.
- Do not automatically execute down migrations or baseline a database.
- Use the same image reference for the migration and API services.
- Derive the Coolify image tag from the resource UUID and source commit; do not
  require an operator to change an image tag for each Git deployment.
- Run the production API and migration command as a non-root user.
- Preserve the local development Compose workflow separately.

# References

- Coolify Docker Compose build pack and `exclude_from_hc`:
  `https://coolify.io/docs/applications/build-packs/docker-compose`
- Coolify rolling-update limitations:
  `https://coolify.io/docs/knowledge-base/rolling-updates`
- Docker Compose dependency completion:
  `https://docs.docker.com/compose/how-tos/startup-order/`
