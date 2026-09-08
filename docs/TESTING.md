# Testing

Tämä dokumentti kuvaa projektin testauskäytännön ihmisille ja AI-agenteille.

Status: frontend and backend test tooling configured

Testityökalut on päätetty ADR-001:ssä:

- frontend: Vitest
- frontend linting: ESLint
- backend: pytest
- backend type checking: pyright
- backend linting: Ruff

---

# Principle

Jokaisessa sovelluskoodin muutoksessa pitää tehdä jompikumpi:

1. lisää tai päivitä relevantit testit
2. perustele miksi testejä ei lisätty

AI-agentti ei saa jättää testausta hiljaisesti tekemättä.

---

# What To Test

## Documentation-only Change

Required:

- tarkista Markdown ja linkit kohtuullisesti
- aja saatavilla oleva dokumentti- tai baseline-tarkistus, jos sellainen on olemassa

Tests may be marked not applicable.

## Small UI Or API Change

Expected:

- unit tests for changed logic
- manual verification for visible behavior
- update snapshots or component tests if project uses them

## Domain Logic Change

Expected:

- unit tests for domain rules
- edge cases for validation and lifecycle rules
- tests for failure paths

Also check:

- relevant domain document
- relevant concept document

## Database Or Migration Change

Expected:

- paired up and down scripts in `db/migrations/`
- test or documented verification that migration applies cleanly
- PostgreSQL verification that the down migration reverts cleanly
- data model documentation update when logical model changes
- database documentation update when physical schema changes

Also update when relevant:

- `docs/data/DATA-MODEL.md`
- `docs/data/DATABASE.md`
- `docs/diagrams/db-physical-schema.puml`
- `docs/diagrams/generated/db-physical-schema.svg`

## Migration Runner

Migration runner unit tests cover discovery, filename and pair validation,
ordering, CLI parsing, history prefixes, checksums and latest-only rollback.
PostgreSQL integration tests cover the actual up/down lifecycle, baselining,
transaction failures, concurrency locking and migration-specific rollback
constraints.

Run the integration suite only against a disposable database. The tests create
and remove uniquely named schemas inside that database:

```bash
cd backend
MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten uv run pytest tests/test_migrations_integration.py -v
```

When `MIGRATION_TEST_DATABASE_URL` is absent, the integration module is skipped;
unit tests still run. CI supplies PostgreSQL 18 and always runs the integration
suite.

## Production Image And Release Migration

TASK-038 packages the existing runner into the production backend image and
gates backend startup with a one-shot Compose service. Verify both the portable
artifact and deployment wiring:

```bash
docker build --target production -t schatten-backend:local -f backend/Dockerfile .

env \
  BACKEND_IMAGE=schatten-backend:local \
  FRONTEND_IMAGE=schatten-frontend:local \
  DATABASE_URL=postgresql://user:password@database:5432/schatten \
  OIDC_DISCOVERY_URL=https://login.microsoftonline.com/tenant-id/v2.0/.well-known/openid-configuration \
  OIDC_ISSUER=https://login.microsoftonline.com/tenant-id/v2.0 \
  OIDC_CLIENT_ID=test-client \
  OIDC_CLIENT_SECRET=test-secret \
  PUBLIC_ORIGIN=https://app.example.test \
  TRUSTED_CADDY_PEER_CIDRS=172.30.0.0/24 \
  CADDY_TRUSTED_PROXY_CIDRS=172.29.0.0/24 \
  docker compose -f docker-compose.production.yml config --quiet

docker run --rm \
  --workdir /tmp \
  --entrypoint python \
  schatten-backend:local \
  -c "import os; from app.core.migrations import discover_migrations; assert discover_migrations(); assert os.getuid() == 10001"
```

Against disposable PostgreSQL, verify fresh `up`, repeated no-op `up`, failure
blocking and concurrent-runner serialization before backend startup. Never use
a developer's normal schema or production for destructive tests.

CI runs `.github/scripts/verify-release-compose-failure.sh` against an isolated
PostgreSQL container. The script corrupts disposable migration history, starts
the real production Compose model and requires both a nonzero deployment result
and no running backend service.

## Production Frontend And Authentication Deployment

TASK-039G adds the immutable frontend/Caddy artifact and makes it the only
public release service. Run the production Compose and live ingress regression:

```bash
.github/scripts/verify-production-compose.sh

docker build --target production -t schatten-frontend:local \
  -f frontend/Dockerfile frontend
FRONTEND_IMAGE=schatten-frontend:local \
  .github/scripts/verify-production-frontend.sh
```

The Compose check verifies required settings, migration-only database
configuration, immutable backend/frontend images, internal ports and the
migration -> backend health -> frontend gate. The live Caddy check covers
configuration adaptation/startup, non-canonical, port-bearing, malformed or
wildcard origin rejection, image health, SPA fallback, exact Host rejection,
strict trusted-proxy parsing, forwarded-header replacement, HSTS,
Referrer-Policy, nosniff, frame denial, enforced CSP and selective callback
query redaction while retaining ordinary request metadata.

Automated checks do not replace provider/browser verification. Run the broad
`docs/qa/AUTHENTICATION-QA-CHECKLIST.md` locally with repository-managed
Authentik. Before the first production rollout and for authentication, provider
or OIDC configuration changes, TASK-040 additionally requires a designated-user
local Authentik-to-Entra smoke. That path is supplemental and does not prove the
direct production OIDC client.

The standard production Compose model is validated locally. The thin Coolify
manifest must additionally be parsed by Coolify because `exclude_from_hc` is a
provider-specific field. There is no staging rehearsal. After each
human-approved production deployment, operators run only the limited direct
Entra smoke defined in `docs/DEPLOYMENT.md`; destructive, load, failure
injection and broad automated testing are prohibited against production.

## Integration Change

Expected:

- unit tests around adapter boundaries
- integration tests when a local or test service is available
- mocked failure cases
- documented manual verification if full integration testing is not possible

## Forecasting Snapshot And Detached Calculation Harness

Forecasting snapshot tests use the existing prediction API fixtures for
representative normal and derived targets. Prepare with
`prepare_prediction_snapshot`, close the preparation Session, round-trip with
`PredictionInputSnapshot.model_dump_json` and `model_validate_json`, then call
`calculate_prediction` without a Session. Source rows may be changed or soft-
deleted between preparation and calculation to prove the frozen observation,
formula, short-name and provenance boundary. Publish separately with
`publish_prediction` when transaction-wide persistence behavior is under test.

The PostgreSQL integration test creates and drops a unique schema in the same
disposable database used by migration integration tests. It commits a source
edit between preparation queries and proves that PostgreSQL `REPEATABLE READ`
keeps the full prepared input on one database snapshot:

```bash
cd backend
MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten \
  uv run pytest tests/test_predictions_postgresql_integration.py -v
```

When `MIGRATION_TEST_DATABASE_URL` is absent, this module is skipped. A skipped
run is not evidence for TASK-057B's consistent-preparation acceptance criterion;
run it against a disposable PostgreSQL database before review.

## Security-Sensitive Change

Expected:

- tests for authorization checks
- tests for invalid input
- tests for forbidden access
- regression tests for the security boundary

Examples:

- authentication
- authorization
- permissions
- tenant or organization boundaries
- file upload
- SQL or query construction
- secrets handling

## Authentication Harness

Backend authentication tests run entirely in process. `tests/test_auth_api.py`
uses a fake discovery/token boundary with SQLite persistence to cover browser
binding, one-time callback consumption, identity linking, opaque sessions,
timeouts, CSRF/Origin, Host/proxy trust and rate limits.
`tests/test_auth_provider.py` generates an ephemeral RSA key and signs ID tokens
for Authlib validation tests; it does not use real provider credentials or the
network. Pytest sets `APP_ENV=test` in `tests/conftest.py`; non-test application
startup still requires complete OIDC configuration.

Business API tests use `tests/auth_helpers.py` to create real test-only User and
AuthSession rows and configure the TestClient cookie, Origin and CSRF headers.
Production dependencies remain enabled. `tests/test_api_authorization.py`
covers the anonymous route matrix, Users role matrix, unsafe-request matrix,
session revocation, inactive-session rejection, broad cross-organisation access
and audit actors for every mutation family.

Frontend authentication tests mock Schatten's application-session endpoints:
`GET /api/v1/auth/session` and `POST /api/v1/auth/logout`. They do not mock or
expose Entra, Authentik, OIDC codes, provider tokens or provider claims. The
shared request-helper tests cover same-origin credentials, memory-only CSRF
headers, global `401` invalidation and non-invalidating `403` responses. UI
tests cover restoration loading, protected routes, role-aware Users navigation,
logout and user-session revocation.

Run the focused suite with:

```bash
cd backend
uv run pytest tests/test_auth_api.py tests/test_auth_provider.py -v
```

## Local Authentik Integration

TASK-039E:n Authentik-tarkistukset käyttävät `.env.authentik.local`-tiedostoa,
joka sisältää vain paikallisia salaisuuksia ja salted password hasheja. Luo se
ensin ja validoi renderöity Compose. Tarkistusskripti käyttää samaa kerrostusta
kuin runtime: `.env` ensin ja `.env.authentik.local` sen jälkeen.

```bash
scripts/setup-local-authentik.sh
scripts/verify-local-authentik-config.sh
docker compose --env-file .env --env-file .env.authentik.local config --quiet
```

Fresh-volume bootstrap pitää ajaa eksplisiittisellä disposable project namella.
Pysäytä mahdollinen normaali identity stack ensin, jotta loopback-portti 9443
vapautuu. Seuraava teardown poistaa vain
`schatten-authentik-bootstrap-test`-projektin kontit, networkin ja nimetyt
volumet; se ei kohdista normaaleihin `schatten_*`-volumeihin:

```bash
docker compose --env-file .env --env-file .env.authentik.local stop authentik-tls authentik-worker authentik-server authentik-database
scripts/setup-local-authentik.sh /tmp/schatten-authentik-bootstrap-test.env
docker compose \
  --project-name schatten-authentik-bootstrap-test \
  --env-file .env \
  --env-file /tmp/schatten-authentik-bootstrap-test.env \
  up -d --wait authentik-database authentik-server authentik-worker authentik-tls
scripts/smoke-local-authentik.sh
docker compose \
  --project-name schatten-authentik-bootstrap-test \
  --env-file .env \
  --env-file /tmp/schatten-authentik-bootstrap-test.env \
  down --volumes
rm /tmp/schatten-authentik-bootstrap-test.env
```

Käynnistä tämän jälkeen normaali full stack, aja migraatiot ja dev seed
`docs/LOCAL-DEVELOPMENT.md`:n komennoilla. Manual browser QA:

- avaa `http://app.localhost:5173/api/v1/auth/login` ja kirjaudu
  `schatten-consultant`-tunnuksella
- varmista `/api/v1/auth/session`-vastauksesta consultant-käyttäjä ja
  Schattenin tietokantarooli
- kirjaudu ulos `POST /api/v1/auth/logout` -flow'n kautta ja varmista sekä
  local sessionin että selainevästeen poistuminen
- toista `schatten-admin`-tunnuksella ja varmista admin-rooli
- yritä kirjautua `schatten-unmatched`-tunnuksella; odota geneeristä virhettä ja
  varmista, ettei `users`- tai `user_identities`-riviä luotu
- tarkista selaimen storage/cookie-näkymästä, että `app.localhost` ei lähetä
  Schatten-cookieita `auth.localhost`-hostille eikä päinvastoin

Token-claimien tarkistus tehdään Authentikin provider previewlla tai rajatulla
kertakäyttöisellä testiclientillä: vaadi `sub`, `name`, `email` ja
`email_verified=true`; varmista ettei tokenissa ole `groups`, `roles`, `oid` tai
`tid`. Älä lokita tai tallenna oikean browser-flow'n authorization codea,
tokeneita, cookieita tai salasanoja.

Optional local Entra federation tarkistetaan lisäksi näin:

```bash
scripts/setup-local-entra.sh
scripts/verify-local-entra-config.sh
docker compose \
  --env-file .env \
  --env-file .env.authentik.local \
  --env-file .env.entra.local \
  -f docker-compose.yml \
  -f docker-compose.entra.yml \
  up -d --wait database authentik-database authentik-server authentik-worker authentik-tls
uv run --env-file .env --project backend python backend/migrate.py up
scripts/provision-local-entra-user.sh
docker compose \
  --env-file .env \
  --env-file .env.authentik.local \
  --env-file .env.entra.local \
  -f docker-compose.yml \
  -f docker-compose.entra.yml \
  up -d --wait
scripts/smoke-local-authentik.sh
```

Browser QA:ssa vaadi matching-email login, Schattenin tietokantarooli, logout
ja unmatched Entra emailin geneerinen failure. Tarkista DevToolsista ettei
provider tokenia ole URL-fragmentissa, web storagessa, cookieissa tai Schattenin
API-vastauksissa. Tarkista Caddy-, Authentik- ja backend-lokeista, etteivät
client secret, code, token, cookie, CSRF-arvo tai henkilökohtainen email näy.
Tuloksiin kirjataan vain päivä, commit, testaaja ja pass/fail.

Lopuksi aja backendin auth-harness ja normaalit baseline-tarkistukset. Local
provider tai local federation ei korvaa human-approved limited direct-Entra
production smokea:

```bash
cd backend
uv run pytest tests/test_auth_api.py tests/test_auth_provider.py -v
uv run ruff check .
uv run pytest
uv run pyright
```

---

# Testing Structure Feature

Structure feature changes may touch both backend graph APIs and frontend graph
editing UI. Choose checks based on the changed layer.

Backend Structure API checks:

```bash
cd backend
uv run ruff check .
uv run pytest tests/test_org_twin_structure_api.py -v
uv run pyright
```

Run the full backend pytest suite when shared service behavior, database models
or scenario/org-state interactions change:

```bash
cd backend
uv run pytest
```

Frontend Structure UI checks:

```bash
cd frontend
pnpm lint
pnpm test -- StructureTab GraphViewer
pnpm build
```

Run the full frontend test suite when shared API client, workspace selection or
tab rendering behavior changes:

```bash
cd frontend
pnpm test
```

Manual QA:

- Use `docs/qa/STRUCTURE-QA-CHECKLIST.md` for end-to-end graph, node, edge,
  filtering, zoom and position update verification.
- Record manual QA results in the PR when visual graph behavior or drag
  interactions are changed.

Authorization note:

- Structure authorization and permission enforcement are out of scope for the
  TASK-025A/TASK-025B baseline and should be tested with the dedicated
  authorization follow-up task.

---

# Testing Summary Feature

Summary changes combine graph history, events and timeseries on a shared date
axis, so test the pure timeline model separately from component interactions.

Backend Summary and temporal graph checks:

```bash
cd backend
uv run ruff check .
uv run pytest tests/test_org_twin_structure_api.py -v
uv run pyright
```

Cover organisation/scenario ownership, stable ids, persistence soft-delete
exclusion, inclusive logical lifetime projection, connected-edge end dates and
invalid lifetime rejection.

Frontend Summary checks:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Pure helper tests cover malformed dates, bounds, ordering, filtering, row and
month label formatting, adaptive year-only headers, chart scales and zoom limits. Component tests cover concurrent cancellable loading,
stale response prevention, states and retry, row rendering, hover details,
filters, mutually exclusive popovers, row visibility and collapsing, zoom scale
feedback, zoom-to-fit, scrolling and shared timeseries row resizing.

Manual QA:

- Use `docs/qa/SUMMARY-QA-CHECKLIST.md` for the scenario-scoped timeline,
  Structure lifetime behavior and visual interaction checks.

---

# Predictions Chart Comparison (TASK-055)

Prediction charts retain every displayed point while thinning date labels to
at most 22, at least 36 SVG units apart, including both endpoints. Year guides
remain independent of date labels; colliding year captions are omitted. Each
line hides visible dots at 100 filtered points but retains hover details.
Units appear inside the white graph area above the plot.

Each metric defaults to the earliest start and latest end of its selected
versions in selected scenarios. Plot start/end inputs independently override
these inclusive bounds for both predictions and live Reality. Reality empty
messages appear only after a successful fetch; a matching numeric series with
no displayed observations has a different message from a missing series.

Manual/visual QA at desktop and narrow viewport widths:

- Compare 23, 100 and 365 dates across a year boundary; check date/year labels,
  endpoints, unit placement, complete lines and interval bands.
- Compare sparse and dense prediction/Reality lines together; filter a dense
  line below 100 points and confirm dots return. Hover to inspect dated values,
  units, provenance and available interval bounds.
- Enable Reality with dates before, within and after the forecast period.
  Confirm overlapping values render and outside values do not stretch the
  default range. Expand either plot bound, then toggle Reality off.
- Select overlapping versions, change scenario/metric selections, and verify
  per-metric ranges. Check missing-series, no-observation, loading and failed
  request states without mistaking an empty result for a fetch failure.

Run `pnpm lint`, `pnpm test` and `pnpm build` from `frontend/`.

---

# Test Levels

Use the lightest useful test level.

## Unit Tests

Use for:

- pure logic
- validation
- domain rules
- formatting/parsing
- small service functions

Frontend unit tests use Vitest.

Backend unit tests use pytest.

Frontend linting uses ESLint.

Backend linting uses Ruff.

## Integration Tests

Use for:

- API endpoint behavior
- database reads/writes
- cross-module flows
- adapter boundaries

## End-to-End Tests

Use only for critical user flows.

Examples:

- registration
- login
- document upload
- payment or billing flow
- permission-sensitive workflow

Do not add broad E2E coverage by default. Keep E2E tests focused.

## Manual Verification

Manual verification is acceptable when:

- the project has no test stack yet
- the behavior is visual
- external systems are not available locally
- the change is documentation-only

Manual verification must be described in the PR.

---

# Task Testing Section

Every task should include a `Testing` section.

Use this shape:

````markdown
## Testing

Required:

- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Build
- [ ] Lint

Not applicable:

- [ ] Reason:

Commands:

```bash
# Frontend, if applicable
cd frontend
pnpm lint
pnpm test
pnpm build

# Backend, if applicable
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```
````

If tests are not added, explain why.

---

# AI Agent Instructions

When implementing a task, the AI-agent must:

1. identify what behavior changed
2. decide what test level is appropriate
3. add or update tests when the change touches application code
4. run available test commands
5. report the exact commands and result
6. explain if tests were not added or could not be run

Use this prompt addition:

```text
Lisää tai päivitä testit muutoksen riskin mukaan.
Jos et lisää testejä, perustele miksi.
Aja saatavilla olevat testikomennot ja raportoi tulokset.
```

---

# When Scaffolding Is Missing

ADR-001 has selected the stack, but the repository may not yet have runnable `frontend/` or `backend/` scaffolds.

In that case:

- do not invent scripts outside the task scope
- do not add dependencies without approval
- document what should be tested later
- perform available static or manual checks
- report that automated tests are not yet configured in the affected package

---

# CI Expectations

Current baseline CI checks repository documentation structure.

CI runs the repository baseline checks and backend checks. The backend job also
starts PostgreSQL 18 and supplies `MIGRATION_TEST_DATABASE_URL`, so migration
integration tests cannot be silently skipped. As application coverage grows, CI
should run:

```text
Install
Lint
Tests
Typecheck
Build
```

The exact commands must be documented in:

- `README.md`
- `docs/LOCAL-DEVELOPMENT.md`
- this file
- `.github/workflows/ci.yml`

---

# PR Expectations

Every PR must state:

- what tests were added or updated
- what commands were run
- whether manual verification was done
- why tests were not added, if not applicable

PRs that change application behavior without tests or a clear reason should not be approved.
