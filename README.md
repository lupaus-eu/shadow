# Shadow

Shadow models organisations as digital twins: a graph of the organisation over time,
metrics as timeseries, events, scenarios, and forecasts, with AI clients connected
through MCP. It is built on the Yearclock platform base: Organizations, memberships and
roles, invitations, Authentik sign-in, row-level security, audit, queues and the worker,
notifications, billing, legal documents, the platform console and the MCP interface.

**Status:** the platform base runs (`docker compose up`); the Shadow features are being
ported one at a time from the previous implementation in `legacy/` (tag
`pre-yearclock-base` holds the last state before the switch). Some documents under
`docs/` and `CONTEXT.md` still describe the Yearclock product and are being replaced
feature by feature.

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Frontend: http://localhost:8173
- Backend health: http://localhost:8100/health
- PostgreSQL-backed status: http://localhost:8100/api/v1/system/status
- Authentik: http://localhost:8190

Yearclock uses host ports 8100–8199 so it can run beside other projects; see
`docs/architecture/docker.md` for the assignments and overrides.

On the first run, finish Authentik initialization at
`http://localhost:8190/if/flow/initial-setup/`. Docker Compose automatically
applies verified enrollment, passkey, mandatory second-factor, and recovery
policy. Follow `docs/runbooks/authentik-local.md` for configuration and
acceptance checks.

Paid Organization activation additionally requires Stripe test-mode values in
`.env`. Ticket 03 of the end-user tutorial explains how to create the EUR 30
monthly Price and forward signed webhooks locally.

For human, ticket-by-ticket product testing, follow the
[Yearclock V1 end-user testing tutorial](docs/end-user-tutorial/yearclock-v1-testing.md).

## Checks

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
docker compose up -d db
cd backend && pytest
cd ../frontend && npm install && npm run typecheck && npm run build
npx playwright install chromium
npm run test:browser
```

## Structure

- `frontend/` - Vite React TypeScript app
- `backend/` - FastAPI app
- `backend/migrations/` - Alembic migrations
- `backend/tests/` - PostgreSQL integration tests
- `authentik/` - identity-provider blueprints
- `docker/` - local service initialization
- `caddy/` - reverse proxy config
- `docs/` - architecture, ADRs, agent guidance, runbooks, and audience documentation

Read `AGENTS.md` before making agent-driven changes.
