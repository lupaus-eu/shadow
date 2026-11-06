# Technology stack and status

This page records the decided technology stack and the implementation status
of the platform. It was moved here from `AGENTS.md` in November 2026. The
stack was decided in [ADR-001](../adr/0001-tech-stack.md); later ADRs amend
it. The full architecture description is in [overview.md](overview.md).

## Stack

Päätetty teknologiapino:

- frontend: React, TypeScript, Vite, pnpm, Vitest, ESLint, Prettier hakemistossa `frontend/`
- backend: Python, FastAPI, Pydantic, uv, pytest, pyright, Ruff hakemistossa `backend/`
- MCP: `fastmcp` 4 (ADR-015) for the MCP endpoint `/api/mcp` in the backend
- database: PostgreSQL
- ORM: SQLAlchemy
- migrations: repository-owned Python/Psycopg runner and paired SQL migrations
- authentication: provider-neutral backend OIDC against Shadow's own
  self-hosted Authentik (ADR-017); local Caddy HTTPS and local Authentik are
  implemented, production Authentik arrives with SaaS plan steps 086A to 087B
- local target: loopback Caddy HTTPS at `https://app.localhost`, routing Vite and
  FastAPI, plus a separate prediction worker and application database
- production target: Docker Engine/Compose on an UpCloud Ubuntu 26.04 LTS host;
  Caddy directly terminates TLS at `https://shadow.lupaus.eu`, serves React and
  proxies FastAPI; initially private PostgreSQL 18 in Docker with persistent storage
- release contracts: immutable matching frontend/backend artifacts, one-shot
  migration-success gates, backend health gating frontend, and one prediction worker

## Platform status

Identity: ADR-017 selects Shadow's own self-hosted Authentik (pinned 2026.8.5, own
logical database `authentik` in the application's PostgreSQL, closed enrollment by
invitation, mandatory second factor). The backend accepts only an Authentik
per-provider issuer, requires a verified email (`OIDC_REQUIRE_VERIFIED_EMAIL`
defaults to true) and uses scopes `openid profile email`. Local development runs it
at `https://id.app.localhost`; the production host is planned as
`https://id.shadow.lupaus.eu`, and production still runs the last release with the
previous provider until steps 086A to 087B. Guarded pre-provisioned User linking,
permanent identity ownership, sessions, CSRF and database roles remain unchanged.

ADR-013 supersedes Coolify/Traefik and local Authentik/federation choices for
deployment, with its identity parts amended by ADR-017. Builds initially run on UpCloud.
Source delivery is amended by TASK-059H: a manual, `main`-only "Deploy to
production" GitHub Action copies the exact commit and a source manifest to a
dedicated upload-only account; builds run on UpCloud from the manifest-verified
source. Git is not used on the server and there is no GitHub deploy key; H1-H3
implement this and F performed the GitHub/host setup.
GitHub Actions/GHCR is a possible later build location with the same image contract.

Initial release requires daily encrypted on-server PostgreSQL backups in
`/opt/postgres-backups` with 7-day retention, recorded backup identifiers and
successful restore-rehearsal evidence. Persistent volumes survive container
replacement but are not backups.
Ofelia schedules backups and weekly Docker maintenance under ADR-013's mandatory
hardening; G implements it, E/F verify and activate it. Docker socket access grants host-level
authority even when mounted `:ro`; verify scheduler and runner restrictions before
activation. Ofelia never replaces the single application prediction worker.
G delivers backup tooling, E the runbook/QA, and F authorized activation and
verification. Missing backup or restore evidence blocks release. A later move
to UpCloud Managed PostgreSQL must preserve or explicitly revise this policy;
application rollback never automatically restores the database. These initial
same-host backups do not protect against loss of the host or its disk; that
limitation is accepted until a separately planned off-server/managed solution.

TASK-059A changes documentation only. The shared reference-data seed CLI is
implemented by TASK-059C, and the empty-users-table administrator bootstrap is
implemented by TASK-059D. TASK-059G implements the production runtime,
build/release, backup and scheduler tooling (`docker-compose.production.yml`,
`deploy/`) and removes the Coolify adapter. TASK-059E adds the integrated
operator runbook `docs/runbooks/production.md` and disposable QA. TASK-059H
records the Git-free source delivery in ADR-013; TASK-059H1-H3 implement the
manifest/receiver/build, the upload gate and workflow, and the server
`deploy/Makefile`, `deploy/bin/service` and runbook update (all implemented).
TASK-059J amends ADR-013 to admit `deploy` and key-only root over SSH from any
address (`AllowUsers deploy root shadow-upload`, `PermitRootLogin
prohibit-password`) with UpCloud disk-move recovery, and updates `audit-host`.
TASK-059F performed the authorized setup and the first production rollout:
release `20261002T085353Z-0db661289165`, accepted and tagged `v0.1.0` on
2026-11-02, with its evidence, accepted deviations and follow-ups in
`docs/operations/qa/FIRST-PRODUCTION-ROLLOUT.md`.
The non-user metamodel seed is approved production reference data; development
Users and example business data remain forbidden in production. First setup is
migrations -> reference seed -> empty-users-table administrator bootstrap.

AI via MCP is an accepted design in `docs/adr/0015-ai-via-mcp.md`
(TASK-069A). TASK-069B's flush-only domain service transaction cores,
TASK-069C's deterministic timeseries generator, TASK-069D's MCP OAuth schema
(migration 017, `mcp_oauth_*`), TASK-069E's OAuth discovery, registration,
authorization request and consent API, TASK-069F's token, refresh and revoke
endpoints, token verification and connections API and TASK-069G's `fastmcp`
read and write endpoints with `McpBearerAuth`, resource protection and the
first read tools (`backend/app/mcp/`), TASK-069H's remaining read tools and
generator preview, TASK-069I's change-set schema (migration 018,
`ai_change_sets`, `ai_change_set_operations`) and engine
(`backend/app/api/v1/ai_change_sets/`) and TASK-069J's change-set staging
write tools and change-set read tools, TASK-069K's always-registered
cookie-session change-set review API (list, detail, apply, reject) and
TASK-069L's SPA consent page `/ai/authorize`, reusable `ConnectionsList` and
admin "Revoke AI connections" action (`frontend/src/features/ai/`) and
TASK-069M's Metrics tab AI panel (connect instructions, connections and
change-set review with apply and reject, `frontend/src/features/ai/AiPanel.tsx`)
and TASK-069N's Shadow skills, Claude Code plugin and repository marketplace
(`backend/app/mcp/plugin/`, `.claude-plugin/marketplace.json`), MCP
prompts and skill zip download and TASK-069O's MCP change-set review
(ADR-015 amendment of 2026-10-29: the read tool `get_change_set_review`, the
write tools `apply_change_set` and `reject_change_set` behind
`MCP_CHANGE_SET_REVIEW_ENABLED`, off by default, and the review channel of
migration 019) are implemented; the MCP and public OAuth endpoints and the
skill zip download are registered only with `MCP_ENABLED=true`, off by
default. TASK-069P's local end-to-end QA (`docs/operations/qa/AI-MCP-QA-CHECKLIST.md`),
trimmed redirect URI allowlist, runbook (`docs/runbooks/production.md`
section 14) and env-file MCP switches (production reads `MCP_ENABLED`,
`MCP_CHANGE_SET_REVIEW_ENABLED` and `MCP_OAUTH_MAX_CLIENTS` from
`production.env`; `deploy-release --mcp-approval` is required to turn MCP on)
complete the implementation. TASK-069P's separately approved production
enablement deployed release `20261103T090415Z-df98a2e7c05a` with both switches
on, accepted and tagged `v0.2.0` on 2026-11-03; its record, covering Claude Code and the claude.ai and Claude
Desktop read connectors, is in `docs/operations/qa/AI-MCP-QA-CHECKLIST.md`. TASK-074
implements ADR-015's amendment of 2026-11-03: one MCP endpoint `/api/mcp`
(FastMCP server "Shadow", one OAuth resource, one grant with `shadow.read`
and `shadow.write`) replaces `/api/mcp/read` and `/api/mcp/write`, which
answer 404; every tool and prompt checks its own scope (`requires_scope`), so
`ROLE_SCOPES` alone can later limit a role to read-only; migration 020
(`020_alter_mcp_oauth_single_resource`) deletes the old grants; the plugin is
0.3.0 with one server `shadow`. Its production deployment needs a separate
approval (`deploy-release --mcp-approval`). Users chat in their own MCP client on
their own AI subscription; Shadow never calls an LLM or stores LLM keys.
FastAPI hosts `/api/mcp` (read tools and prompts need `shadow.read`, write
tools `shadow.write`) and acts as OAuth 2.1 authorization server over the
Authentik login (ADR-015). ADR-0023 decides that AI clients will instead authenticate
with a dedicated Authentik provider "Shadow MCP", which the backend does not use yet.
The write tools stage
AI change sets. **A human decides every apply and reject**: in the Metrics tab,
or, with `MCP_CHANGE_SET_REVIEW_ENABLED=true`, by approving the MCP client's
`apply_change_set` or `reject_change_set` call; no other MCP tool may apply
changes, and every review records its channel (`web` or `mcp`). No worker,
scheduler or container is added. ADR-015 approved the `fastmcp` backend dependency, which TASK-069G added
(`fastmcp>=4.1.4,<5`). The feature's C4 model uses LikeC4
(`docs/architecture/diagrams/likec4/`); PlantUML remains the default elsewhere.

