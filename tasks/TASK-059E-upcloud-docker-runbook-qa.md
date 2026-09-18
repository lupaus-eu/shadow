# TASK-059E UpCloud Docker Runbook And Integrated QA

## Source Plan And Dependencies

Approved [ADR-013](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md)
amendment. Integrates completed implementation from
[B](TASK-059B-local-https-direct-entra.md),
[C](TASK-059C-production-reference-data-seed.md),
[D](TASK-059D-production-admin-bootstrap.md) and
[G](TASK-059G-upcloud-docker-runtime.md), after A.
Replaces the earlier Coolify/Traefik runbook specification. Initial daily
encrypted on-server backup jobs, backup identifiers and restore-rehearsal
requirements are retained with **7-day retention**; the no-backup exception
is superseded.

## Goal

Deliver a concrete, checked runbook for manual UpCloud/Compose releases on
Ubuntu 26.04 LTS and direct-Entra QA, keeping implementation evidence separate
from provider setup and authorized production verification.

## Requirements

- Start from the operator-reported completed cloud-init baseline in
  [deployment documentation](../docs/DEPLOYMENT.md#existing-cloud-init-baseline-operator-reported).
  Document verification and remaining setup on the existing host, not host
  provisioning or routine reruns of cloud-init, Docker installation or swap
  creation. Keep reported setup separate from live verification evidence.
- Replace active Coolify/Traefik/federation procedures with UpCloud Ubuntu 26.04
  LTS, Docker Engine/Compose, direct Caddy TLS and PostgreSQL 18 in Docker.
  Verify installed tool versions and compatibility when writing executable steps;
  do not silently substitute another OS version or provision a new host.
- Document SSH key access and password-login restriction, restricted SSH and
  public 80/443 firewall rules, Docker port exposure, DNS and Caddy certificate
  persistence/permissions. Keep API/worker/migration/database ports private.
  Use a least-privilege GitHub read-only deployment key/access method and private
  production environment storage; never print secrets into evidence.
- Add concrete host verification for cloud-init completion/errors, fresh `deploy`
  key login, effective password/keyboard-interactive and root/default-user SSH
  settings, Docker/Compose/Buildx, UFW/provider rules and published ports. The
  supplied `disable_root: false` and unrestricted OpenSSH allow rule do not
  demonstrate disabled root SSH or source-restricted SSH. Preserve working access
  while documenting any necessary authorized changes; do not apply them in E.
- Check the existing 2 GiB swap, sysctls, timezone, fail2ban SSH jail and unattended
  update/reboot policy. Treat `deploy` as a privileged operator with passwordless
  sudo and Docker access. Verify source-checkout tooling and directory ownership;
  do not assume `/opt/apps` or `/opt/caddy` is writable by application containers.
  Reuse cloud-init-created `/opt/postgres-backups` with verified ownership,
  permissions and backup-job mounts; preserve existing contents. Its existence
  alone is not evidence of completed backups.
- State no Authentik, Traefik, forward-auth, Coolify or `auth.lupaus.eu` is required.
  Record both exact Entra callbacks and logout returns, shared-registration
  coupling, separate secrets, exact issuer, scopes `openid profile email`, no
  Graph calls and no `email_verified` requirement. Tenant cleanup is authorized
  F setup only after confirming no remaining consumers need old entries/grants.
- Specify on-server build from an approved commit, CI/local checks, immutable
  matching image references, freeze and human approval, then deployment without
  rebuild. Include resource-pressure triggers for later Actions/GHCR builds;
  no automatic deployment or fallback pipeline is added.
- Give tested first-initialization commands: **migrations -> reference seed ->
  administrator bootstrap** using the release backend artifact. Verify empty
  users before bootstrap, non-user seed parity, private input and no implicit
  startup seed. Never run the full development seed in production.
- Retain migration-success gates, frontend readiness and the single worker.
  Explain service health, restart/reboot, certificate and database persistence
  and secret-safe failure diagnosis. Repeated releases skip first-admin bootstrap.
- Document and test G's daily encrypted on-server PostgreSQL backup jobs in
  `/opt/postgres-backups` with **7-day retention**, on-demand pre-release backup,
  safe failure reporting, identifiers, directory permissions/key access and isolated
  restore procedure. Protect keys separately from backup files. State the accepted
  host/disk-loss limitation: these backups share the database host; off-server
  replication is deferred. Do not log data or secrets.
- Document and test [ADR-013's Ofelia hardening](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md#operational-scheduler-and-docker-control-boundary)
  using G's disposable runtime: verify pinned images, no scheduler network/ports,
  fixed job configuration, confined socket access and effective runner privileges,
  networks, mounts and credentials. Explain host-equivalent Docker API authority
  and why `:ro` socket mounts are not API authorization. Include weekly cleanup
  exclusions/locking and schedule failure diagnosis; unmet controls block activation.
- Require a completed pre-change backup identifier and latest successful restore-
  rehearsal evidence before each release; missing/failed evidence blocks release.
  For first installation, enable jobs and capture a pre-migration baseline,
  then back up the initialized database after migrations -> seed -> bootstrap
  and verify an isolated restore before acceptance. Rehearsal retrieves and
  decrypts a completed on-server backup and checks schema/data without touching production.
  No automatic production restoration or application rollback as data recovery.
- Run broad automated/disposable QA using simulated OIDC with no tenant secrets.
  Integrate local HTTPS/HMR/admin provisioning, shared reference seed, empty-table
  bootstrap and production-style Compose/ingress tests. Preserve old historical
  QA results separately without counting them as direct-Entra/Caddy evidence.
- Record real local Entra browser verification separately after authorized
  setup, or explicitly pending for F before rollout. Use designated accounts;
  verify login, first-link, role, session, logout and unmatched-user rejection.
  Local success does not establish production DNS/TLS/client-secret correctness.
- Define narrow production smoke: pre-provisioned designated admin/consultant,
  login/callback/session/logout, database-role enforcement, first-release or
  changed-auth unmatched-account refusal and one isolated prediction flow.
  No broad automated, destructive, load, spoofing or failure-injection tests.
- Define release metadata: approved commit, image references, CI/local evidence,
  approval, tester/time, initialization and smoke outcomes, prior stable artifact
  refs or explicit first-release absence, completed backup identifiers and
  successful restore-rehearsal evidence location/time/result. Keep identity,
  credential and restored data out of records.
- Describe coordinated application rollback only if older matched images remain
  compatible with the migrated schema. Never automatically run down migrations,
  delete volumes, reset or restore the database. With no compatible stable target,
  stop/escalate for an approved forward fix; no first-release rollback promise.
- Include a future managed-PostgreSQL planning entry: data transfer, connection/TLS
  and session advisory locks, cutover/rollback and continuity of encryption,
  7-day retention and restore verification, including evaluation of off-server
  protection. Only the managed
  migration is deferred; initial backup implementation and evidence are required.

## Acceptance Criteria

- [ ] Ofelia and job-runner hardening passes disposable QA against ADR-013;
      runbook activation checks cover effective settings and privileged API access.
- [ ] Runbook starts from the reported existing host baseline, distinguishes
      unverified facts from checks performed, and avoids destructive bootstrap
      repetition; remaining SSH/firewall/storage checks are explicit.
- [ ] Runbook commands match B/C/D/G and Ubuntu 26.04 LTS; renamed task links and
      dependencies resolve, and active platform/identity requirements agree.
- [ ] Disposable integrated initialization proves migrations -> seed -> bootstrap
      without development Users; repeat/refusal behavior is documented.
- [ ] Local simulated-OIDC, HTTPS, production Compose and ingress/worker checks
      pass with exact evidence; historical tests are not claimed as new results.
- [ ] Live local Entra evidence is separately recorded or explicitly pending for
      authorized F setup before rollout; production smoke remains pending F.
- [ ] Manual approval/frozen artifacts, narrow smoke and schema-compatible
      application rollback are clear; missing backup or restore evidence blocks release.
- [ ] Daily encrypted on-server backups and 7-day retention are tested with
      disposable data; isolated restore evidence is recorded separately from
      pending production activation/verification under F.
- [ ] Future managed-service planning preserves or explicitly revises backup
      policy. No provider or production action occurred.

## Implementation, Testing And Documentation

Read architecture, ADR-002/004/012/013 and `docs/TESTING.md`. Update
`docs/DEPLOYMENT.md`, `docs/LOCAL-DEVELOPMENT.md`, authentication and relevant
prediction QA checklists and command documentation. Execute documented commands
against disposable local infrastructure, run relevant checks for changed scripts
and validate links/diagrams. Do not mark live checks complete unless performed.

Provider setup and actual rollout belong to F under explicit approval. No
production backup activation/restoration, managed migration or unattended deployment. Record eventual
Step 13 reviews under `docs/ai-reviews/TASK-059E/`.
