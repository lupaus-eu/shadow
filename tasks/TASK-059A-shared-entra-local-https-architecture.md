# TASK-059A Shared Entra And UpCloud Deployment Architecture

## Source Plan

Approved amendment: "Amend TASK-059 for UpCloud, Caddy and direct Entra".
Amend this documentation branch only; preserve previous work and historical
records. No runtime changes, credential changes or resource provisioning.

The amended [ADR-013](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md)
is the accepted source of truth. Earlier Coolify/Authentik decisions are
superseded. Initial backup requirements are retained with 7-day retention;
the intervening no-backup exception is superseded, not implementation evidence.

| Task | Deliverable | Dependency |
| --- | --- | --- |
| TASK-059A | Architecture and policy amendment | None |
| [TASK-059B](TASK-059B-local-https-direct-entra.md) | Local HTTPS and direct Entra | A |
| [TASK-059C](TASK-059C-production-reference-data-seed.md) | Shared reference-data seed and production CLI | A |
| [TASK-059D](TASK-059D-production-admin-bootstrap.md) | First-administrator CLI | A; C for final sequence verification |
| [TASK-059G](TASK-059G-upcloud-docker-runtime.md) | Production runtime, build/release and backup tooling | A |
| [TASK-059E](TASK-059E-upcloud-docker-runbook-qa.md) | Integrated QA and UpCloud/Compose runbook | B/C/D/G |
| [TASK-059F](TASK-059F-first-production-rollout.md) | Human-authorized setup, rollout and acceptance | E and explicit operational approval |

## Goal

Record the accepted target before implementation: direct Entra in development
and production, Caddy TLS, and Docker Engine/Compose on an UpCloud host running
Ubuntu 26.04 LTS. Distinguish that target from the still-implemented local
Authentik and Coolify adapter.

## Requirements

- Amend the unmerged ADR-013 in place and supersession notes in earlier ADRs.
  Update architecture, agent guidance, deployment/local-development docs,
  authentication-domain references and both authentication diagrams/SVGs.
- Record local `https://app.localhost` and production `https://schatten.lupaus.eu`;
  each Entra Web callback is its origin plus `/api/v1/auth/callback`, and each
  post-logout return is its origin plus `/login`.
- Use the existing single-tenant confidential Web registration, distinct
  environment secrets and independent databases. Explain shared permissions,
  consent, assignments, callbacks and application identity despite separate secrets.
- Require exact tenant-specific issuer, `openid profile email`, no Graph calls
  and no `email_verified` claim requirement. Preserve pre-provisioning, guarded
  first linking, permanent `(issuer, subject)`, database roles, sessions, CSRF
  and audit rules. Old identities are preserved without issuer rewrites.
- Remove Authentik callbacks and its Graph permission from target configuration;
  actual tenant cleanup belongs to authorized F setup after consumer checks.
- Development uses local Caddy -> Vite/FastAPI; production uses Caddy serving
  React and proxying FastAPI, owning TLS and persistent certificates directly.
  Exclude Authentik in both environments, Traefik, Coolify, forward-auth, staging
  and `auth.lupaus.eu`. Preserve release/migration/worker/readiness contracts.
- Initially use private PostgreSQL 18 in Docker with persistent storage.
  Require daily encrypted on-server backups in `/opt/postgres-backups` with
  7-day retention, backup
  identifiers and successful restore-rehearsal evidence from initial release.
  Volumes are not backups. G owns tooling, E procedure/QA and F activation/evidence.
  A future managed migration must explicitly maintain or revise this policy.
- Specify Ubuntu 26.04 LTS and initial UpCloud builds from an approved commit,
  immutable images and deployment without rebuilding. Document conditions for
  later GitHub Actions/GHCR builds without implementing that fallback.
- Preserve reference-data-only production seed and explicit migrations ->
  reference seed -> empty-users-table administrator bootstrap. Production
  development-user inserts remain prohibited. B owns separate local provisioning
  for already-seeded development databases.
- Rename B/E, add G, and do not create H. Leave future acceptance criteria
  unchecked. Preserve historical verification without claiming it verifies this
  amendment; require fresh documentation checks.

## Acceptance Criteria

- [x] ADR and active docs consistently record the amended topology, registration,
      Ubuntu 26.04 LTS, private Docker PostgreSQL and required initial backups
      with 7-day retention.
- [x] Target and currently implemented runtime are explicitly distinguished;
      superseded decisions and historical QA retain clear labels.
- [x] Active release gates require backup completion/identifiers and successful
      restore evidence; application rollback does not recover database contents.
- [x] B/E task names, all links and A->B/C/D/G->E->F dependencies are correct;
      D also uses C for sequence verification; no H task is created.
- [x] Updated diagram sources and generated SVGs render and pass visual inspection.
- [x] Markdown/link checks and `git diff --check` pass; only documentation changes.

## Out Of Scope

Runtime, Compose, credentials, dependencies, databases or provider changes;
implementation of B-G; production rollout, backup automation or managed-database
migration. Do not perform tenant cleanup as part of this documentation amendment.

## Implementation And Verification Requirements

Read `AGENTS.md`, `ARCHITECTURE.md`, relevant ADRs, Users/USER references and
`docs/diagrams/README.md`. Verify renamed links, dependencies, active policy
consistency, Markdown and both rendered diagrams. Application tests/builds are
not applicable to documentation-only changes. Record only checks performed.
After review, implement B on its own task branch; do not silently include it here.
Any eventual Step 13 review follows `docs/AI-REVIEW-RECORDS.md`.

## Historical Implementation And Verification (2026-09-11; Superseded Design)

The following record is preserved for the earlier Coolify/Authentik version.
Its completed checks do not verify the 2026-09-17 amendment or any future runtime.


Implemented on `docs/TASK-059A-shared-entra-local-https-architecture`, based on
the fetched `origin/main`, on 2026-09-11. Added
[ADR-013](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md),
supersession/cross-references in ADR-003 through ADR-006, and updated
`AGENTS.md`, `ARCHITECTURE.md`, deployment/local-development documentation,
authentication topology and login sequence. Added a supersession note to the
authentication QA checklist while preserving historical results. Existing HTTP instructions are
explicitly current until B; runtime and operations under B-F remain pending.

Verification:

- Changed Markdown local link targets, balanced code fences and whitespace checked.
- Both changed PlantUML sources rendered to SVG using the existing Compose
  `diagram-renderer`; SVG XML/content checked and PNG previews visually inspected.
- Documentation consistency and `git diff --check` passed; diff scope contains
  no runtime/Compose changes or changes to historical completed task records.
- No application tests/builds: this task changes only documentation and diagrams.

The changes remain for local human review. No commit, PR, Step 13 review,
merge, provider change, database operation or production deployment was performed.

## Historical Amendment Verification (2026-09-17; Backup Policy Superseded)

The following checks describe the earlier no-backup amendment. Its backup-policy
conclusions are superseded by the restored requirements; preserve the record
without treating it as verification of backup implementation.

Amended this existing documentation branch for the approved UpCloud/Caddy/direct-
Entra target. Updated ADR-013 and supersession notes, architecture/agent/README
and local/deployment guidance, Users domain references and QA policy. Renamed B
and E, retained C/D contracts, rewrote F, and added G. No H task was created.
The historical implementation record above and completed QA results remain
preserved; B/C/D/G/E/F acceptance criteria remain unchecked.

Checks actually performed:

- Checked 20 changed Markdown files for balanced code fences, heading spacing,
  trailing whitespace and final newline, plus 62 relative link/anchor targets.
- Searched repository Markdown for both retired task filenames: none remain.
  Reviewed A -> B/C/D/G -> E -> F dependencies, with C used by D's final sequence
  verification and explicit operational approval required for F.
- Reviewed active origin/callback, direct-Entra, UpCloud, Ubuntu 26.04 LTS,
  private PostgreSQL 18 and no-initial-backup specifications. Remaining older
  platform/backup requirements are labelled historical or current legacy runtime;
  no active initial-release gate requires backup completion or restore evidence.
- Rendered both authentication PlantUML sources to SVG with the existing Compose
  diagram renderer. Parsed both SVGs as XML, checked provider/origin content and
  visually inspected PNG renders of the same sources. No rendering errors.
- Compared earlier ADR-003 through ADR-006 bodies and completed authentication
  QA items against their historical content; preserved them. Verified the previous
  A implementation/verification record remains intact.
- Compared file hashes with the starting workspace: changes are limited to 24
  documentation/diagram files and the two planned task renames. Runtime, Compose,
  configuration, dependencies and historical completed task files are unchanged.
- `git diff --check` passed. No application tests/builds were run because this
  amendment changes no application behavior.

No credentials, databases, tenant/DNS/provider settings or production resources
were changed. No commit, PR, formal Step 13 review or deployment was performed.
The amendment remains for human review; implement B afterward on its own task
branch. Authentication migration and deployment are not implemented by this work.

## Historical Backup Reinstatement Verification (2026-09-17; Destination Superseded)

This record verified the earlier off-server requirement. The subsequent accepted
destination is on-server `/opt/postgres-backups`; encryption, retention and evidence
gates remain active. This historical record does not verify backup implementation.

Restored initial daily encrypted off-server PostgreSQL backup jobs with 7-day
retention, completed backup identifiers and successful restore-rehearsal release
gates. Updated active architecture/ADR/agent guidance, deployment/local docs,
QA and C/D/E/F/G specifications. G owns backup tooling, E procedure/QA and F
approved activation and evidence. The prior no-backup verification above remains
historical; it no longer defines the accepted policy. The cloud-init directory
is only a possible working area, not evidence of configured off-server backups.

Verification performed: Markdown structure/whitespace and 59 local links/anchors
checked; active backup-policy consistency reviewed; topology PlantUML rendered
to SVG, XML/labels checked and PNG preview visually inspected. `git diff --check`
passed. File-hash comparison confirms this amendment changes only 17 documentation/
diagram files. Future task criteria remain unchecked; runtime, Compose and other
configuration files are unchanged. No application tests are needed for these
text/diagram changes. No host action, backup activation, real backup/restore,
provider mutation, commit or deployment was performed.

## Initial On-Server Backup Destination Amendment (2026-09-17)

The accepted initial destination is `/opt/postgres-backups` on the existing host,
matching the cloud-init-created directory. Daily encryption, 7-day retention,
completed backup identifiers and isolated restore-rehearsal release gates remain
required. Off-server replication is deferred; the same-host/disk-loss limitation
is explicit. G/E/F verifies permissions, mounts, completed files and restoration
while preserving existing directory contents. Earlier off-server verification
above is historical and does not define the current destination.

Checked Markdown structure/whitespace and 59 relative links/anchors, destination
and policy consistency, and unchecked future-task criteria. Regenerated the
changed topology SVG and inspected its rendered preview. `git diff --check`
passed. Hash comparison shows only 17 documentation/diagram files changed;
runtime/configuration is unchanged. No server action, backup/restore execution,
provider change or deployment occurred. Application tests are not applicable.
