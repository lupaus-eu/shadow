# Project layout

| Path | Contents |
| --- | --- |
| `backend/` | FastAPI application (`app/`), tests (`tests/`), migration runner `migrate.py`, `pyproject.toml` and `uv.lock` |
| `backend/app/api/v1/` | One package per domain API (auth, users, organisations, customers, org states, twin structure, predictions, MCP OAuth, AI change sets, AI skills) |
| `backend/app/mcp/` | The MCP server `/api/mcp`, its tools, and the Claude Code plugin and skills (`plugin/`) |
| `backend/app/platform/` | Platform foundation (ADR-016, ADR-019): audit log, background jobs and worker, email delivery, and notifications |
| `backend/app/core/` | Settings, database session, and migration helpers |
| `frontend/` | React SPA (`src/`), Vite and lint configuration, and the production Caddy edge (`Caddyfile`, `caddy-entrypoint.sh`) |
| `frontend/src/` | `App.tsx` routes, `pages/`, `workspace/` tabs, `features/` by area, `components/`, `auth/`, `api/` client, and `styles/` |
| `db/migrations/` | Paired `NNN_name.sql` and `NNN_name.down.sql` migrations (ADR-002) |
| `db/init/` | Reference-data seed and the development-only seed |
| `local/` | Local Caddy HTTPS configuration for `https://app.localhost` |
| `deploy/` | Production host tooling: `bin/` commands, `ops/` scripts, `ofelia/`, `lib/`, and the server `Makefile` |
| `scripts/` | Developer scripts: local TLS, the AI review record validator, and `scratch-status.py` |
| `.github/` | CI (`workflows/ci.yml`), the manual production delivery workflow, and its verification scripts |
| `.claude-plugin/` | The repository plugin marketplace for the Shadow Claude Code plugin |
| `docker-compose.yml`, `docker-compose.production.yml` | Local and production Compose stacks |
| `CONTEXT.md` | Canonical business vocabulary |
| `FEATURE_WORKFLOW.md` | Specification and delivery workflow |
| `.scratch/` | Local, unversioned PRDs, designs, and tickets (README and templates are versioned) |
| `docs/adr/` | Architecture decision records |
| `docs/architecture/` | System documentation: overview, stack, deployment, domains, concepts, data model, and diagrams |
| `docs/design/` | Durable UI and UX guidance |
| `docs/user/`, `docs/admin/` | End-user and administrator guidance |
| `docs/operations/` | Local development, testing, and QA evidence (`qa/`) |
| `docs/runbooks/` | Step-by-step production procedures |
| `docs/gdpr/`, `docs/legal/` | Privacy inventory and legal-document practice |
| `docs/agents/` | Agent workflow guidance |
| `docs/ai-reviews/` | Historical AI review records (validated in CI) |
| `docs/archive/` | Read-only history: the former `tasks/` and process documents |
