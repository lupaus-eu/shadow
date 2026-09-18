# TASK-059G UpCloud Docker Runtime And Build/Release Tooling

## Source Plan And Dependencies

Approved [ADR-013](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md)
amendment; depends on
[TASK-059A](TASK-059A-shared-entra-local-https-architecture.md).
C/D commands are integrated with B/G by E; G does not depend on their execution.
This specification authorizes no production operation.

## Goal

Provide portable production Docker Engine/Compose runtime, build/release and
backup tooling for an UpCloud host running **Ubuntu 26.04 LTS**, with direct Caddy TLS
and private Docker PostgreSQL 18. Use a dedicated Ofelia container as the
Compose-native scheduler for operational jobs, including backups and Docker
maintenance. Retire the active Coolify adapter.

## Requirements

- Target the already-provisioned host described in the
  [cloud-init baseline](../docs/DEPLOYMENT.md#existing-cloud-init-baseline-operator-reported).
  Use installed Docker Engine/Compose/Buildx; tooling must check prerequisites
  and report missing/incompatible tools rather than rerun host bootstrap,
  reinstall Docker or recreate swap. E/F owns live host verification/remediation.
- Keep application container privileges separate from the privileged `deploy`
  operator. Document storage mappings and required ownership for existing
  `/opt/apps` and `/opt/caddy` without overwriting their contents or assuming
  directories are already mounted volumes. Do not overwrite or delete the
  existing contents of cloud-init-created `/opt/postgres-backups`. Reuse it as
  the selected backup destination with explicit permissions and a mount into the
  backup job if containerized. Its existence is not evidence of a working backup job.
- Implement the mandatory [ADR-013 scheduler hardening](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md#operational-scheduler-and-docker-control-boundary).
  Pin Ofelia and job images by digest; use an operator-owned read-only job file
  with explicit targets and no label auto-discovery. Ofelia has no published ports,
  `network_mode: none`, a read-only root filesystem, `cap_drop: [ALL]`,
  `no-new-privileges` and a non-root user with only the required socket group.
  No privileged mode or host namespaces; declare bounded writable scratch mounts.
  Keep the local Unix socket confined to Ofelia and any documented cleanup runner,
  never application or database-backup containers. No Docker TCP listener or
  widened socket permissions. A `:ro` socket mount does not restrict API writes:
  treat every Docker API client as host-administrator-equivalent.
- Apply the same hardening to operational runners, including those created by
  Ofelia through the API; verify their effective settings, not just Compose.
  Among scheduled jobs, only the backup runner gets private database connectivity,
  required database/encryption credentials and writable `/opt/postgres-backups`; config/scripts/keys
  are read-only, with keys outside backup output. Ofelia itself needs no secret
  or backup-output mounts. No host-root, database-data or Caddy-storage mounts.
  Document that Docker API access can still reach other containers and secrets.
  Preload job images during release. If image/job-mode limitations prevent these
  controls, stop for review; do not silently weaken them. Keep Ofelia operational
  only and preserve the single application prediction worker.
- Production Caddy serves the built React SPA with history fallback, routes
  `/api` and `/api/*` to FastAPI, and owns HTTPS for `schatten.lupaus.eu` directly.
  Persist certificate/account storage across replacements and restarts. Resolve
  port/storage permissions while retaining least-privilege container execution.
- Expose only Caddy's public HTTP/HTTPS 80/443; redirect HTTP appropriately for
  certificate issuance and HTTPS use. Preserve exact Host, security headers/CSP,
  sanitized forwarding and callback-log redaction. Remove the upstream
  Traefik trust assumption; FastAPI trusts only actual Caddy peers.
- Add PostgreSQL 18 with a pinned version/image policy, private Compose networking,
  persistent database storage, secret-safe configuration and no published port.
  Keep API, migration and worker private. Document that volumes survive
  replacement but are not backups; initial backups are required as specified below.
- Define health checks, restart and host-reboot behavior for long-running services.
  Preserve migration-success gating of API and single prediction worker, and
  backend health gating frontend readiness. Verify cold-start certificate
  issuance does not create a circular readiness dependency. Failed migration
  must not start a new application/worker or be treated as a healthy release.
- Preserve one worker, its database-only config, graceful shutdown, advisory-lock
  ownership/recovery and existing queue/health contract. Migration/API/worker use
  the same immutable backend image and database. No Authentik or forward-auth.
- Remove the active Coolify adapter and replace platform-specific validation
  with equivalent standard Compose/CI coverage. Preserve provider-neutral image
  commands and historical ADR/task records. Do not remove security or migration
  coverage merely because the platform changes.
- Implement reproducible server-side builds from an approved exact commit with
  locked dependency inputs. Record commit, tool versions and matching immutable
  frontend/backend image IDs/digests; do not deploy mutable `latest` references.
  Build and freeze artifacts before release approval, then deploy without
  rebuilding. Verify target images resolve to the recorded artifacts.
- Preserve previous matched image artifacts and release metadata for coordinated
  application rollback only when compatible with the migrated schema. First
  rollout has no previous stable target; stop/escalate if it fails.
- Provide secret-safe manual build/release commands with migration gating and
  explicit operator-controlled C/D initialization interfaces. No automatic
  seeding/bootstrap on app startup and no unattended deployment.
- Document build relocation triggers: OOM/failures, sustained CPU/swap/memory
  contention with running services or unacceptable build duration. A later
  GitHub Actions/GHCR pipeline must deliver the same immutable image contract;
  do not implement automatic deployment or that fallback pipeline in this task.
- Keep database configuration portable for a separately planned managed-service
  migration, including TLS/connection and session-level advisory-lock needs.
  Do not implement managed-service data transfer or migration here.
- Implement daily encrypted on-server PostgreSQL backup jobs writing to
  `/opt/postgres-backups` with **7-day retention**, an explicit on-demand pre-release
  backup command, and isolated
  restore tooling. Use a consistent database backup format suitable for
  PostgreSQL 18; include the database objects/configuration needed for recovery
  or document their secure reconstruction. Schedule the daily backup through the
  Ofelia container, while keeping the explicit on-demand pre-release command
  available. Do not treat a live volume copy as a verified database backup. Keep
  backup work separate from application startup.
- Make the selected host directory, schedule and protected key locations explicit
  operator configuration; F activates real settings. Protect stored backups and
  keep keys separately from backup files with documented recovery access. Never
  bake credentials into images or print data/key material in logs. No remote
  upload destination/credentials are required initially; document that host/disk
  loss may destroy both data and backups.
- Emit safe backup identifiers, completion times and file-write/integrity status.
  Publish only complete encrypted backups; report failures such as disk full or
  denied permissions without claiming success. Apply 7-day retention to backup
  files under `/opt/postgres-backups`; limit pruning to job-owned files and preserve
  unrelated contents. Define retry/failure visibility, avoid overlapping jobs and
  document temporary-file cleanup and disk/resource use on the small build host.
- Schedule a weekly Ofelia Docker maintenance job for safe disk cleanup. It may
  remove stopped containers, dangling/expired build artifacts and other
  explicitly job-owned unused resources, but must not use `docker system prune
  --volumes` or otherwise remove PostgreSQL data, Caddy certificate storage,
  `/opt/postgres-backups`, the current release images or the retained previous
  stable release artifacts needed for rollback. Avoid a broad `docker system
  prune -a` unless an equivalent release-aware protection mechanism is proven.
  Make the cleanup scope, retention window, timezone, lock/non-overlap behavior,
  dry-run or inspection path, and failure reporting explicit. The weekly cleanup
  must not run concurrently with a release, build, restore or backup job.
- Verify retrieval, decryption and restoration into an isolated disposable
  PostgreSQL target, including schema/data checks. Release procedures require
  completed backup identifiers and successful restore evidence. No automatic
  production restoration; actual destination provisioning/activation belongs to F.

## Acceptance Criteria

- [ ] Runtime/build tooling accepts the existing host baseline, checks tool and
      storage prerequisites and performs no implicit host bootstrap; production
      backup activation requires F configuration and operational approval.
- [ ] Compose runs the direct-Caddy production topology with private PostgreSQL 18,
      persistent certificate/database volumes, a dedicated Ofelia scheduler for
      operational jobs, and no active Coolify dependency.
- [ ] Health/restart/reboot behavior, cold-start HTTPS, migration failure gates,
      frontend readiness and exactly one worker are verified locally.
- [ ] ADR-013 scheduler and runner hardening is verified against rendered Compose
      and effective disposable container settings: immutable image refs, no public
      ports, isolated networking, confined socket/secret/mount access, fixed job
      configuration and least-privilege execution. Failure blocks activation.
- [ ] Existing proxy/security/redaction guarantees and equivalent Compose/CI
      coverage remain effective with no upstream Traefik assumption.
- [ ] Approved-commit server builds produce frozen matched artifacts and release
      startup uses them without rebuilding; no secrets enter build layers/logs.
- [ ] Application rollback is coordinated and schema-compatible, with no down
      migrations, volume deletion, database reset or restoration.
- [ ] Daily encrypted on-server backups, on-demand backups and 7-day retention
      in `/opt/postgres-backups` work through Ofelia and with safe identifiers/
      failure reporting; retrieval/decryption/restore succeeds against disposable
      data. Production activation is pending F.
- [ ] The weekly Ofelia Docker cleanup is tested with fixture resources and
      timestamps, preserves persistent volumes, backup files and current/previous
      rollback images, and reports failures without claiming cleanup success.
- [ ] Off-server build triggers and later managed-database planning are documented
      without implementing either or claiming a production rollout.

## Testing

Read `docs/TESTING.md`, ADR-002/003/012/013 and deployment docs. Use disposable
local data and simulated OIDC to exercise production images/Compose, private
ports, TLS and persistence across container replacement, health/reboot behavior,
failed migration blocking, worker ownership/shutdown and image-only deployment.
Run affected image, Compose and CI-script checks plus application checks where
code changes require them. Never inject failures into production or delete
existing development volumes. Test backup encryption/write failure, disk-full/
permission errors, safe backup retention pruning and Ofelia scheduling with
fixture timestamps, missing key/database credential failures, protected Docker
resources and end-to-end isolated restore with schema/data checks. Use temporary
test directories and synthetic data, not production storage or records. Record
tools/images and results.

Check scheduler and runner image digests, network/port bindings, socket ownership,
mount access modes, user/groups, capabilities and security options. Include runners
created dynamically by the selected Ofelia job mode. Test that missing socket
access fails visibly without permission widening, undeclared label jobs are not
discovered, and backup/cleanup still work with the required restrictions. Perform
Docker-control tests only on an isolated disposable daemon without developer or
production workloads; never demonstrate host takeover against a shared daemon.

## Documentation And Scope Limits

Update image/Compose/build documentation and remove current-platform Coolify
instructions. E supplies the integrated operator runbook and F performs approved
host/DNS/tenant and backup setup. Backup implementation and disposable QA are
in scope; real provider provisioning, production backup activation/restoration,
managed PostgreSQL migration and new staging are not. New dependencies still
require separate approval. Eventual Step 13 reviews: `docs/ai-reviews/TASK-059G/`.
