# Testing guidance for agent work

Choose checks according to risk and service boundary. A small ticket does not
require every check, but every omitted relevant check needs a reason in the
ticket.

| Change surface | Minimum evidence | Typical check |
| --- | --- | --- |
| Domain rule, API, authorization, or worker | Focused backend test for success and failure paths | `cd backend && pytest -q` |
| React component, view, or client state | Type check and focused browser evidence where it changes user behavior | `npm --prefix frontend run typecheck && npm --prefix frontend run build` |
| End-to-end user workflow | Browser validation of the important path | Start required services, then `npm --prefix frontend run test:browser` |
| Pure frontend logic (geometry, formatting) | Unit test | `npm --prefix frontend run test:unit` |
| Frontend code that needs a DOM (the diagram-js canvas) | Vitest with jsdom in `frontend/tests/canvas/`; part of `test:unit` | `npm --prefix frontend run test:unit` |
| New or changed UI surface | Automated accessibility scan in the browser test | `AxeBuilder` from `@axe-core/playwright`, as in `yearclock-accessibility.spec.ts` |
| Change to a key view's look (overview, planner, Event drawer, People page, planner on a phone) | Visual baseline reviewed in the diff | `cd frontend && npx playwright test visual --update-snapshots`; baselines are per platform in `tests/browser/visual.spec.ts-snapshots/`, and a platform without them skips |
| Layout on phones | Phone checks: no horizontal scroll, 44 px touch targets | `tests/browser/mobile.spec.ts` (390 × 844, touch) |
| Alembic migration or PostgreSQL constraint/RLS | Migration against the integration-test database and focused database test | `docker compose up --build` plus the relevant backend test suite |
| External integration | Adapter/contract test with failure and idempotency path | Targeted backend tests; record unavailable external environments explicitly |
| Compose file, published port, or container naming | Port range and naming check | `python3 scripts/check-compose-ports.py` |
| Architecture documentation only | Links and references checked | `git diff --check` plus targeted link/reference review |

Integration tests must use the isolated test database configured by the
repository. Never point destructive migration or RLS tests at a development or
production database. If a browser, integration, or external test environment is
unavailable, record the limitation in `## Ajetut tarkistukset` and leave the
necessary follow-up ticket open.
