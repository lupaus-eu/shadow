# Testing guidance for agent work

Choose checks according to risk and service boundary. A small ticket does not
require every check, but every omitted relevant check needs a reason in the
ticket. The detailed test harnesses, fixtures, and QA procedures are in
[`docs/operations/testing.md`](../operations/testing.md).

| Change surface | Minimum evidence | Typical check |
| --- | --- | --- |
| Domain rule, API, authorization, or worker | Focused backend test for success and failure paths | `make backend-check` (`cd backend && uv run ruff check . && uv run pytest && uv run pyright`) |
| React component, view, or client state | Focused Vitest/Testing Library test, lint, format, and build | `make frontend-check` (`pnpm --dir frontend format:check`, `lint`, `test`, `build`) |
| End-to-end user workflow | Browser validation of the important path | Start the local stack (`make dev-up`) and check the path at `https://app.localhost` |
| Migration, PostgreSQL constraint, or row-level security | Up/down migration against a disposable database and a focused PostgreSQL test | `MIGRATION_TEST_DATABASE_URL=… uv run pytest tests/test_migrations_integration.py` plus the relevant `*_postgresql_integration.py` suite |
| External integration | Adapter/contract test with failure and idempotency path | Targeted backend tests; record unavailable external environments explicitly |
| Compose file, image, or production runtime | The production compose and runtime verifications | The `.github/scripts/verify-production-*.sh` scripts that CI runs |
| Diagram source | Rendered output in the diff | `make diagrams` |
| Documentation only | Links and references checked | `git diff --check` plus targeted link/reference review |

Integration tests must use the isolated test database configured by the
repository. Never point destructive migration or row-level-security tests at a
development or production database. If a browser, integration, or external
test environment is unavailable, record the limitation in
`## Ajetut tarkistukset` and leave the necessary follow-up ticket open.
