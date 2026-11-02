# TASK-059F Authorized UpCloud Setup And First Production Rollout

## Source Plan And Dependencies

Approved [ADR-013](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md)
amendment and completed
[TASK-059E](TASK-059E-upcloud-docker-runbook-qa.md), integrating B/C/D/G after A,
and the source-delivery amendment
[TASK-059H](TASK-059H-github-source-delivery-architecture.md) implemented by
H1-H3 (manifest-verified receive, upload gate and "Deploy to production"
workflow, server Makefile and runbook).
Every provider mutation and production operation requires explicit operational
approval. This specification and documentation amendment grant no such approval.
The earlier Coolify/federation setup is superseded. Backup identifiers and
restore-rehearsal gates are retained with daily encrypted on-server backups
and **7-day retention**, replacing the intervening no-backup exception.

## Goal

Perform the first approved release on an UpCloud **Ubuntu 26.04 LTS** host using
Docker Engine/Compose, direct Caddy TLS, private Docker PostgreSQL 18 and the
existing shared Entra registration with direct OIDC in both environments.

## Existing Host Baseline

The operator has already provisioned the host with cloud-init: `deploy` key
access and passwordless sudo, Docker Engine/Compose/Buildx, UFW, fail2ban,
unattended-upgrades, Helsinki timezone, 2 GiB swap/sysctls and the `/opt`
directories described in the
[deployment baseline](../docs/DEPLOYMENT.md#existing-cloud-init-baseline-operator-reported).
This is operator-reported setup, not completed F verification. Application
deployment, DNS/TLS, Entra setup and database initialization remain pending.

## Requirements

- Confirm the existing approved host and inspect cloud-init completion/errors,
  actual Ubuntu version and installed Docker/Compose/Buildx versions using E's
  verification procedure. Do not rerun cloud-init, reinstall Docker, recreate
  swap or overwrite existing files/directories as a deployment prerequisite.
- Verify fresh `deploy` key access and effective password/keyboard-interactive,
  root and default-user SSH policy. The supplied `disable_root: false` is not
  evidence that root SSH is disabled. Check UFW and any provider firewall for
  IPv4/IPv6 exposure. Under the source-delivery and
  [TASK-059J](TASK-059J-deploy-ssh-from-any-address.md) amendments TCP 22 stays
  open from anywhere and `AllowUsers deploy root schatten-upload` admits
  `deploy` and key-only root from any address. Before opening TCP 22 to
  anywhere, confirm with `sshd -T` (and `sshd -T -C user=root,...`) that
  `PasswordAuthentication no`, `KbdInteractiveAuthentication no`,
  `PermitRootLogin prohibit-password` and the `AllowUsers` line are effective
  and that password/keyboard-interactive logins as `deploy` and root are
  refused in a fresh session; any missing setting blocks opening the port. A
  root key login is optional, not required evidence: the root key holder (the
  product owner) does not take part. Record the `deploy` and root key counts,
  the role holding each root key and the recovery access holder (UpCloud
  account, initially the product owner) by role. After rebasing onto J, align
  section 2.1 of the rollout record `docs/qa/FIRST-PRODUCTION-ROLLOUT.md` with
  the amended runbook 2.1 before recording any result: `sshd -T` expecting
  `permitrootlogin prohibit-password` and `allowusers` `deploy`, `root` and
  `schatten-upload`; root checked with `sshd -T -C user=root,...` and a
  refused root password login; an optional root key login row that may stay
  "not performed"; the `audit-host` lines `root SSH is key-only` and
  `AllowUsers admits deploy/root from any address`; the key counts and root
  key holder role; and a recovery row for the UpCloud account access holder
  (role, authentication set up, acknowledged by role/date) replacing the old
  console-only recovery note. Apply only
  necessary authorized
  access/firewall changes, validating SSH config with `sshd -t` and keeping a
  working session. Preserve public TCP 80/443 and check Docker
  publication separately; UFW alone does not protect published container ports.
- Verify existing swap/sysctls, free resources, timezone, fail2ban SSH jail and
  unattended-update/reboot policy. Do not infer sufficient build resources from
  swap alone. Record sanitized outcomes without keys, user-data or raw auth logs.
- Under authorization, create the `schatten-upload` account (locked password,
  no sudo, `docker` or `adm`, member of none of `deploy`'s groups; key
  restricted by `restrict` and the `upload-gate` forced command),
  `/opt/apps/schatten-upload` (group: the upload account's primary group, with
  `deploy` as supplementary member) and `/opt/apps/schatten-sources`. Before the
  first upload, install the root-owned `upload-gate` and `schatten-receive` from
  the approved `main` commit on an operator workstation, as `deploy`; after
  the first receive, confirm their hashes equal the
  manifest entries. Verify `main` protection and create the GitHub `production`
  environment limited to `main` with secrets `SSH_HOST`, `SSH_USER`, `SSH_KEY`,
  `SSH_PORT` and `SSH_FINGERPRINT`. No GitHub deploy key, host checkout or Git
  use is configured for deployment; Git's presence on the host is only
  recorded. The first real "Deploy to production" run, confirming its workflow,
  event, branch and commit, and receiving its digest are F work.
- Configure protected environment files and persistent storage
  mappings/permissions.
  Inspect `/opt/apps` and `/opt/caddy` before use; do not assume creation set
  appropriate ownership. Reuse cloud-init-created `/opt/postgres-backups` as the
  backup destination, verifying permissions and the job mount while preserving
  existing contents. Directory creation alone does not establish backups.
- With authorization, configure DNS for `schatten.lupaus.eu` to this host and
  Caddy's public TLS/certificate storage. No `auth.lupaus.eu`, Authentik,
  Traefik, Coolify or forward-auth configuration is needed.
- Configure the existing single-tenant confidential Web registration with:

  | Purpose | Development | Production |
  | --- | --- | --- |
  | Public origin | `https://app.localhost` | `https://schatten.lupaus.eu` |
  | Entra Web callback | `https://app.localhost/api/v1/auth/callback` | `https://schatten.lupaus.eu/api/v1/auth/callback` |
  | Post-logout return | `https://app.localhost/login` | `https://schatten.lupaus.eu/login` |

- Use separate private environment secrets and independent databases. Confirm
  exact tenant issuer, `openid profile email`, no Graph calls and no
  `email_verified` claim requirement. Record shared consent/permissions/
  assignments/callback coupling without secret values. Confirm designated testers
  and production users have the required enterprise-app assignments.
- Check remaining consumers before removing obsolete Authentik callbacks and
  its Graph `User.Read` grant; coordinate with B cutover. Remove only unused
  configuration under explicit tenant authorization, preserving required OIDC
  scopes and unrelated consumers. Do not rewrite old application identity rows.
- Complete separately recorded real local direct-Entra browser checks on B's
  HTTPS environment before production rollout, including explicit local admin
  provisioning on existing seeded data if applicable. Simulated tests and old
  federation results are not substitutes for this evidence.
- Initialize fresh private PostgreSQL 18 with persistent Docker storage and
  no published port. Record the chosen image/version and volume mapping safely.
  Volumes are not backups. Do not apply fresh-install commands to an existing
  production database.
- Before enabling Ofelia schedules, verify the deployed scheduler and runners
  against [ADR-013's hardening contract](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md#operational-scheduler-and-docker-control-boundary)
  and E's evidence. Record pinned image references and sanitized verification of
  socket exposure, network/ports, fixed job configuration, privileges and mounts.
  Missing controls block activation; a read-only socket mount does not limit
  Docker API authority. Confirm weekly cleanup exclusions and non-overlap locks.
- Under explicit operational approval, configure G's daily encrypted on-server
  PostgreSQL backup jobs in `/opt/postgres-backups` and **7-day retention**. Protect
  encryption keys separately from backup files and document recovery access.
  Verify schedule, file-write/integrity, retention and failure reporting; record
  safe identifiers and the accepted same-host/disk-loss limitation. No off-server
  upload or replication is required for initial release.
  Existing cloud-init directories do not satisfy this requirement.
- Before changes, capture a completed pre-migration baseline backup and record
  successful isolated restore evidence. After first migrations -> reference seed
  -> admin bootstrap, also back up the initialized database and retrieve/decrypt/
  restore that completed on-server backup to an isolated target, checking schema/data before
  release acceptance. Protect rehearsal data and record sanitized evidence, not
  row contents. Missing/failed backup or restore evidence blocks release.
  Subsequent releases require a completed pre-change backup identifier and latest
  successful restore evidence. Never overwrite production as a rehearsal.
- Build initially on UpCloud from the manifest-verified source of the approved
  exact `main` commit using G's reproducible process as amended by H1. If resources are inadequate, stop and arrange reviewed off-server
  builds using the same immutable image contract. Freeze matching frontend/
  backend refs and check evidence before deployment approval. Deploy without
  rebuilding; API/migration/worker share the backend artifact.
- Record explicit release approval and the absence of a previous stable release
  for first rollout. Execute **migrations -> reference seed -> administrator
  bootstrap** with private operator input and the approved image. No development
  User inserts, manual production SQL, automatic startup seed or identity creation.
  Keep migration-success gates and readiness checks; run exactly one worker.
- Pre-provision subsequent designated users through normal admin functionality.
  Run only E's narrow production smoke with designated accounts and isolated
  records: login/callback/session/roles/logout, applicable unmatched-user denial
  and one prediction flow. Do not run broad destructive/security/load suites.
- On failure, stop and assess. Later application rollback requires previously
  frozen matching images compatible with the current migrated schema. No
  automatic down migrations, volume deletion, database reset or restoration;
  application rollback cannot recover lost database contents. First rollout
  has no earlier stable image and requires an approved fix/escalation path.
- Record sanitized commit/images, tool versions, CI/local checks, authorization,
  operator/tester/time, DNS/TLS/service readiness, initialization and smoke result.
  Record stable release refs only after acceptance under the approved process.
  Initial acceptance requires completed backup identifiers, active daily jobs
  with 7-day retention and successful initialized-database restore-rehearsal
  evidence. Production restoration always needs separate authorization/impact review.
- Record the future separate UpCloud Managed PostgreSQL migration entry covering
  data transfer, connection/TLS/advisory locks, cutover/rollback, backup capabilities,
  7-day retention and restore verification. Managed migration remains deferred;
  initial backup activation and isolated restore verification are part of F.

## Acceptance Criteria

- [ ] Deployed Ofelia and job-runner hardening is verified against ADR-013 before
      schedules are enabled; sanitized evidence includes weekly cleanup safeguards.
- [ ] Existing cloud-init baseline and effective access/firewall/service settings
      are verified and recorded; only necessary authorized changes occurred,
      with no bootstrap rerun, swap recreation or implicit host reprovisioning.
- [ ] E's integrated prerequisites and real local direct-Entra verification are
      complete; provider/host/tenant changes have recorded operational approval.
- [ ] Source reaches the host only through the "Deploy to production" Action and
      the upload-only account, is accepted by `schatten-receive` with the digest
      from the run summary; no deploy key or checkout is on the host and Git
      is not used for deployment.
- [ ] Ubuntu 26.04 LTS UpCloud host, direct Caddy TLS and private Docker
      PostgreSQL 18 are verified without public backend/database exposure.
- [ ] Shared registration callbacks, separate secrets, issuer/claims and consumer-
      checked cleanup are verified without recording secrets or personal emails.
- [ ] Frozen approved artifacts deploy without rebuild; migrations -> reference
      seed -> empty-users-table admin bootstrap succeeds, with one healthy worker.
- [ ] Explicit release approval and narrow production smoke are recorded; failure
      handling is schema-aware and first-release limitations are explicit.
- [ ] Daily encrypted on-server backup jobs and 7-day retention are active;
      pre-change/initialized-database backup identifiers and successful isolated
      restore-rehearsal evidence are recorded. Missing evidence blocks acceptance.
- [ ] Future managed-service migration planning remains a separate follow-up;
      no prohibited automatic database recovery/destruction occurred.

## Execution And Evidence

Follow the runbook as updated by H3 and `docs/AI-DEVELOPMENT-WORKFLOW.md` approval boundaries.
Do not execute this task merely because its specification exists. Record only
operations/checks actually performed; leave blocked/unperformed checks pending.
Keep evidence in the F record
[FIRST-PRODUCTION-ROLLOUT.md](../docs/qa/FIRST-PRODUCTION-ROLLOUT.md) without
identity or credential payloads. Any eventual Step 13 review follows `docs/AI-REVIEW-RECORDS.md` under
`docs/ai-reviews/TASK-059F/`.
