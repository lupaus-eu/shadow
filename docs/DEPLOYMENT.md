# Deployment

This document describes the staging and production deployment baseline decided
in `docs/decisions/ADR-003-coolify-deployment.md`.

## Release Contract

The production backend image is provider-neutral. It contains the API,
`migrate.py`, its Python implementation and the paired SQL files from
`db/migrations/`.

The image has two commands:

```text
API:       image default command
Migration: python migrate.py up
```

Both commands require the same `DATABASE_URL`. A deployment provider must run
the migration command once and start or promote the API only after exit code
zero. The runner's PostgreSQL advisory lock serializes overlapping attempts.

Application rollback never runs a down migration automatically. Successfully
applied forward migrations remain in place.

## Files

```text
backend/Dockerfile              dev and production image targets
docker-compose.yml              local development
docker-compose.release.yml      shared release-service lifecycle fragment
docker-compose.production.yml   standard production release contract
docker-compose.coolify.yml      thin Coolify adapter
```

`docker-compose.release.yml` owns the shared build, commands, environment,
health and dependency lifecycle. The provider-neutral production file adds the
required `BACKEND_IMAGE`. The Coolify file extends the same lifecycle, derives
one release image name from Coolify's resource UUID and source commit, and adds
`exclude_from_hc: true` to the completed migration job. Provider-specific fields
are not used by application code or the provider-neutral manifest.

## Build And Portable Verification

Build from the repository root. Use a release-specific immutable tag in real
deployments, such as the Git commit SHA:

```bash
docker build \
  --target production \
  --tag schatten-backend:local \
  --file backend/Dockerfile \
  .
```

Verify migration discovery without relying on the image working directory:

```bash
docker run --rm \
  --workdir /tmp \
  --entrypoint python \
  schatten-backend:local \
  -c "from app.core.migrations import discover_migrations; assert discover_migrations()"
```

Run the portable migration command by injecting `DATABASE_URL` through the
runtime environment or provider secret manager. Do not put a real URL in a
Compose file, shell history or committed environment file.

## Coolify Configuration

Configure the Git-backed Docker Compose resource to use:

```text
/docker-compose.coolify.yml
```

Set this environment variable in Coolify:

- `DATABASE_URL`: the staging or production PostgreSQL connection URL, stored
  as a secret

The adapter requires Coolify's predefined `COOLIFY_RESOURCE_UUID` and
`SOURCE_COMMIT` values and assigns both services this image reference:

```text
schatten-backend-${COOLIFY_RESOURCE_UUID}:${SOURCE_COMMIT}
```

This keeps staging and production image names separate and gives every Git
release a commit-specific tag without an operator updating `BACKEND_IMAGE`.

Assign the backend domain to container port `8000`. Do not assign a domain or
public port to `migration`. The backend image checks `/health`; the migration
job disables that long-running health check and Coolify excludes the completed
job from aggregate health checks.

The production image runs both commands as the unprivileged numeric user and
group `10001:10001`.

PostgreSQL is external to this application Compose stack. A connection failure
therefore exits the migration job nonzero and blocks backend startup. Retrying
the deployment is safe after connectivity is restored because `up` validates
history and is a no-op when current.

Coolify Docker Compose deployments are not rolling or zero-downtime. Plan a
maintenance window where availability is required.

## Existing Database Adoption Gate

Complete this once for every existing staging or production database before
enabling automatic deployments:

1. Disable automatic deployment for the target environment.
2. Take and verify a restorable database backup using the environment's backup
   process.
3. Inspect whether `schema_migrations` exists and review its records if it does.
4. Compare the actual schema with the repository migration level. Do not infer
   the level only from the latest filename.
5. If the database is non-empty and untracked, run the exact verified baseline
   command manually from the matching release image:

   ```bash
   python migrate.py baseline NNN
   ```

6. Run `python migrate.py up` from the matching image and require a successful
   no-op before enabling automatic deployment.
7. Record the backup, verified baseline and command outcome in the deployment
   change record without recording credentials.

Never automate `baseline` and never use it on a fresh empty database. The
operator is asserting that the existing schema already matches `NNN`.

## Staging Rehearsal

Before enabling production deployment, rehearse in staging:

1. Deploy against a disposable or backed-up staging database.
2. Confirm migration filenames and success or no-op output are visible without
   credentials.
3. Confirm the backend is not started when the migration job exits nonzero.
4. Redeploy after correcting the failure and confirm `up` resumes safely.
5. Confirm `/health` becomes healthy only for the backend service.
6. Roll the application image back and confirm no down migration runs.

Creating Coolify resources and performing the rehearsal require explicit human
authorization. Record the results in the PR or deployment change record.

## Migration Failure And Rollback

On migration failure:

- keep the failed deployment stopped
- inspect the migration job's credential-safe error
- repair connectivity, history drift or SQL through a reviewed follow-up
- retry the forward deployment
- do not invoke a down migration automatically

If an application health check fails after migrations succeeded, roll back only
the application image. Forward schema must remain compatible with that image.
Use expand/contract releases so destructive cleanup occurs only after the old
application and its rollback window are gone.

## Provider Replacement

A replacement provider needs only `DATABASE_URL`, the immutable image, the
migration command, failure propagation and the API health check. Translate the
Compose migration service to the provider's release job, init container or
pre-deployment command. Backend and migration-runner code do not change.
