# Stack

## Runtime

- Frontend: Vite, React, TypeScript; Tailwind CSS v4, Radix primitives,
  React Router v7, lucide-react, and self-hosted Inter (ADR-0028,
  `docs/design/ui-foundation.md`)
- Structure canvas: `diagram-js` 15.28 (MIT; ADR-0051) with `tiny-svg` for the
  SVG drawing calls. diagram-js brings `didi`, `min-dom`, `min-dash`,
  `inherits-browser`, `object-refs` and `path-intersection` as its own
  dependencies and ships its types (`lib/**/*.d.ts`) and `assets/diagram-js.css`.
  Still to come: `diagram-js-minimap` 5.6 (MIT, a separate package) and `elkjs`
  (lazy loaded) in structure-canvas ticket 07
- Backend: FastAPI, Python
- Legal texts: Markdown files in `backend/legal/`, served by the backend (ADR-0041); the frontend renders them with `react-markdown` and `remark-gfm` (added with the public pages)
- Reverse proxy: Caddy
- Database: PostgreSQL
- Persistence: SQLAlchemy 2 with Psycopg 3
- Migrations: Alembic
- Background jobs: Python workers backed by PostgreSQL
- Identity: self-hosted Authentik
- Agent interface: official Python MCP SDK (`mcp`), a thin adapter over the application (ADR-0037, ADR-0038)
- Forecasting: pure-Python methods (linear, seasonal, Holt) and Prophet 1.5 (ADR-0042)
- Spreadsheet import and export: `openpyxl` (XLSX) and the standard `csv` module
- No LLM calls from the system: agents work through MCP under the user's own subscription (ADR-0047)
- Billing: Stripe Billing
- Transactional email: Scaleway Transactional Email
- Local orchestration: Docker Compose
- CI: GitHub Actions
- Tests: pytest (backend), Node's built-in test runner for pure frontend
  modules, Vitest with jsdom for frontend modules that need a DOM (the
  Structure canvas, `frontend/tests/canvas/`), Playwright with `@axe-core/playwright` for browser and automated
  accessibility checks

## Defaults

- Shadow's compose project keeps host ports 8100–8199; the assignments are in `docker.md`.
- The frontend listens on `8173` and the backend container on `8000`
  (published on host port `8100`).
- Caddy routes `/api/*` on its site address to the backend, keeping the `/api`
  prefix, and all other paths to the frontend. Identity and platform host
  routing are not configured yet; see `deployment.md`.

## Change Policy

When changing a core technology, update this file and add an ADR in `docs/adr`.
