# TASK-059H GitHub Source Delivery Architecture

## Source Plan

Developer-approved plan "Manual GitHub source delivery without git on the
server" (2026-09-29), requested by the product owner: a manually started
GitHub Action ("Deploy to production") copies the approved source to the
UpCloud host with an SCP action using GitHub secrets; an operator then builds
and deploys on the host with `make` commands. Building on GitHub and GHCR image
delivery are a later phase, not part of 059H.

Decisions recorded with the plan:

- Follow the product owner's example workflow (`workflow_dispatch`, checkout,
  SCP action with `overwrite: true`, secrets `SSH_HOST`, `SSH_USER`, `SSH_KEY`,
  `SSH_PORT`), adding a host-key fingerprint secret `SSH_FINGERPRINT` and one
  preparation step that exports the exact commit and writes a source manifest.
- **Git is not used on the server.** Git runs only on the GitHub runner and in
  local QA. The server verifies the delivered files against a source manifest
  whose SHA-256 the operator takes from the GitHub run summary.
- The upload key belongs to a dedicated, unprivileged upload account whose key
  can only write files; it is never the `deploy` key.
- SSH port 22 is reachable from GitHub-hosted runners; `deploy` stays limited
  to operator networks with `AllowUsers`.
- Upload target `/opt/apps/schatten-upload/<commit>/`; verified sources in
  `/opt/apps/schatten-sources/<commit>/`.

This task is documentation only, on its own `docs/` branch after TASK-059E is
merged. Merging it is the human approval of the architecture change.

| Task | Deliverable | Dependency |
| --- | --- | --- |
| TASK-059H | ADR-013 amendment, task specs, decision-level docs | TASK-059E merged |
| [TASK-059H1](TASK-059H1-source-manifest-git-free-build.md) | Source manifest, verified receive, `build-release --source`, no server git | H |
| [TASK-059H2](TASK-059H2-upload-account-deploy-action.md) | Upload account gate and the "Deploy to production" workflow | H1 |
| [TASK-059H3](TASK-059H3-server-makefile-runbook.md) | Server Makefile, `service` command, runbook and deployment docs | H1, H2 |
| [TASK-059F](TASK-059F-first-production-rollout.md) | Authorized setup and first rollout | H3 and explicit operational approval |

## Goal

Record the accepted source-delivery model before implementation so H1-H3 have
an approved architecture: how source reaches the host, what the server trusts,
the upload account's boundary, the SSH exposure and the absence of git on the
server. Replace the currently documented GitHub read-only deploy key and host
checkout.

## Requirements

- Amend [ADR-013](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md)
  with a dated amendment section covering:
  - manual source delivery by a `workflow_dispatch` GitHub Action restricted
    to `main`; builds still run on the host from delivered source; no automatic
    deployment or build on GitHub (GHCR remains a later option with the same
    image contract);
  - no git on the server, replacing git-based exact-commit verification with a
    source manifest (commit, ref, `SOURCE_DATE_EPOCH`, run ID, per-file mode,
    SHA-256 and path) verified by a root-owned receiver against the manifest
    digest the operator copies from the GitHub run summary;
  - the explicit trust consequence: the server can no longer verify files
    against a commit hash; integrity rests on GitHub, the run summary shown
    over HTTPS and the operator-entered digest; the upload key alone cannot
    inject accepted source;
  - the upload account boundary: no sudo, no `docker` group, locked password,
    writable only in its upload folder and `/tmp`, key restricted by
    `restrict` and a forced command allowing only the SCP action's upload
    commands; `deploy` never executes or runs tools inside the upload folder;
  - SSH exposure: UFW allows 22 from anywhere for GitHub-hosted runners;
    `AllowUsers deploy@<operator-cidr> schatten-upload` keeps `deploy`
    source-restricted; the internet-reachable account can only upload; SSH is
    public-key only (`PasswordAuthentication no`,
    `KbdInteractiveAuthentication no`, `PermitRootLogin no`), verified before
    22 is opened to anywhere;
  - GitHub-side controls: `production` environment limited to `main`, secrets
    `SSH_HOST`, `SSH_USER`, `SSH_KEY`, `SSH_PORT`, `SSH_FINGERPRINT`,
    `contents: read`, `persist-credentials: false`, third-party action pinned
    by full commit SHA, one run at a time;
  - status and task table: add H/H1/H2/H3 between E and F; replace the
    "TASK-059H is not created" wording (production Authentik remains excluded).
- Update decision-level summaries that must agree with the ADR: the
  ARCHITECTURE deployment section, the AGENTS.md tech-stack/status lines
  (builds on UpCloud from delivered source, no git on the server), the
  DEPLOYMENT.md delivery sequence and "task H" wording, and the
  [TASK-059F](TASK-059F-first-production-rollout.md) requirements (upload
  account, secrets and receiver instead of least-privilege GitHub source access;
  the first real Action run is F work).
- Add the H1-H3 task files to the branch. Detailed runbook, command and testing
  documentation stays in H1-H3.

## Acceptance Criteria

- [ ] ADR-013 records the source-delivery model, no git on the server, the
      manifest-digest trust and its weaker guarantee, the upload account
      boundary, SSH exposure and GitHub-side controls.
- [ ] ARCHITECTURE, AGENTS, DEPLOYMENT (sequence) and TASK-059F agree with the
      amendment; no document still requires a GitHub deploy key or Git on the
      host as the target design.
- [ ] H1-H3 specs are present, linked and consistent with this task.
- [ ] No code, workflow, host, GitHub setting, secret or provider change.

## Out Of Scope

- Any implementation (H1-H3), GitHub environment/secret creation, host account
  creation or SSH/UFW change (F).
- Building on GitHub, GHCR, image transfer or automatic deployment.
- Rewriting historical QA records (TASK-059E/G evidence stays as recorded).

## Implementation Notes

Branch: `docs/TASK-059H-github-source-delivery` from `main` after 059E merges.
Keep the amendment additive: earlier ADR-013 decisions on runtime, backups,
scheduler hardening, release gates and rollback are unchanged.

## Testing

Required:

- [ ] Manual verification: relative links and anchors in changed documents resolve.

Not applicable:

- [x] Reason: documentation only; no application code, scripts or tests change.

## Documentation

- `docs/decisions/ADR-013-shared-entra-local-https-deployment.md`
- `ARCHITECTURE.md`, `AGENTS.md`, `docs/DEPLOYMENT.md` (delivery sequence)
- `tasks/TASK-059F-first-production-rollout.md`
- `tasks/TASK-059H1-*.md`, `TASK-059H2-*.md`, `TASK-059H3-*.md`

Record eventual Step 13 reviews under `docs/ai-reviews/TASK-059H/`.
