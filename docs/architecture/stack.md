# Stack

## Runtime

- Frontend: Vite, React, TypeScript; Tailwind CSS v4, Radix primitives,
  React Router v7, lucide-react, and self-hosted Inter (ADR-0028,
  `docs/design/ui-foundation.md`)
- Structure canvas: `diagram-js` 15.28 (MIT; ADR-0051) with `tiny-svg` for the
  SVG drawing calls. diagram-js brings `didi`, `min-dom`, `min-dash`,
  `inherits-browser`, `object-refs` and `path-intersection` as its own
  dependencies and ships its types (`lib/**/*.d.ts`) and `assets/diagram-js.css`.
  Also `diagram-js-minimap` 5.6 (MIT; the minimap, its code loaded when the minimap is first opened; it ships no
  types, so `canvas/diagram-js-minimap.d.ts` declares it; its stylesheet is imported into `theme.css`) and `elkjs`
  0.12 (automatic layout, the layered algorithm; loaded only when the person asks for a layout, as a chunk of its own
  of about 1.5 MB, 450 kB gzipped). `elkjs` is licensed **EPL-2.0 OR GPL-3.0-or-later**; Shadow takes it under
  EPL-2.0 (ADR-0051), unmodified, from npm, and ships its own licence file with the package. The Structure canvas
  tests run it in Vitest (jsdom), where it works without a worker
- Backend: FastAPI, Python
- Legal texts: Markdown files in `backend/legal/`, served by the backend (ADR-0041); the frontend renders them with `react-markdown` and `remark-gfm` (added with the public pages)
- Reverse proxy: Caddy
- Database: PostgreSQL 18 (`postgres:18-alpine`)
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
- Images: built for `linux/arm64` (ADR-0053)
- CI: GitHub Actions
- Tests: pytest (backend), Node's built-in test runner for pure frontend
  modules, Vitest with jsdom for frontend modules that need a DOM (the
  Structure canvas, `frontend/tests/canvas/`), Playwright with `@axe-core/playwright` (also on the Structure canvas: keyboard path, node list, 375 px) for browser and automated
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
