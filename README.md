# Yearclock

A multi-Organization SaaS for visually planning recurring and predictable
organizational work across a calendar year. Each Organization owns circular
Yearclocks in which Lanes form concentric rings and Events mark dated planning
entries. See `CONTEXT.md` for the domain vocabulary and
`.scratch/_PORTFOLIO.md` for feature and ticket status.

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
