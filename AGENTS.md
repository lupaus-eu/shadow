# Agent Instructions

Shadow models organisations as digital twins: a graph of the organisation
over time, metrics as timeseries, events, scenarios, and forecasts, with AI
clients connected through MCP. It runs in production at
`https://shadow.lupaus.eu` and is being turned into a multi-tenant SaaS
service on the same platform model as Yearclock (`../yearclock`); that plan is
in `.scratch/saas-platform/PLAN.md` on the developer's machine.

Before editing implementation code, read these files in order:

1. `docs/architecture/stack.md`
2. `docs/architecture/project-layout.md`
3. `docs/architecture/overview.md` (the parts that concern the change)
4. `CONTEXT.md`
5. The relevant feature material under `.scratch/`

Keep changes scoped to the requested ticket. Update documentation when a
change affects service boundaries, the data model, environment variables,
deployment behavior, permissions, or an external integration. Keep the
diagrams in `docs/architecture/diagrams/` (PlantUML by default, LikeC4 for the
MCP model) and their generated SVGs current in the same change.

## Local commands

- Overview of shortcuts: `make help`
- Install dependencies: `make install`
- Start the local stack (Caddy HTTPS at `https://app.localhost`, API, worker,
  Vite, database, migrations, and the development seed): `make dev-up`;
  stop it with `make dev-down`
- All checks: `make check`
- Backend checks: `make backend-check` (`cd backend && uv run ruff check . && uv run pytest && uv run pyright`)
- Frontend checks: `make frontend-check` (Prettier check, ESLint, Vitest, and build with pnpm)
- Migrations: `uv run --env-file .env --project backend python backend/migrate.py up`
  (see `db/migrations/README.md`)
- Diagrams: `make diagrams`
- Ticket portfolio: `python3 scripts/scratch-status.py > .scratch/_PORTFOLIO.md`

Local setup details are in `docs/operations/local-development.md` and test
harnesses in `docs/operations/testing.md`.

## Conventions

- Keep frontend code under `frontend/src` and backend API code under
  `backend/app`.
- Add durable decisions to `docs/adr/` (new ADRs from 0016, format in
  `docs/adr/README.md`). Create an ADR before choosing a new technology or
  changing the architecture, the database strategy, the deployment model, or a
  significant external integration.
- Feature PRDs, technical designs, domain models, and implementation tickets
  belong in `.scratch/`; copy `.scratch/_template/` to start a new feature.
  `.scratch/` stays local and is never pushed to GitHub.
- System documentation belongs in `docs/architecture/` (overview, stack,
  deployment, domains, concepts, data model, diagrams). UI and UX guidance
  belongs in `docs/design`; user, administrator, operations, runbook, privacy,
  and legal guidance belongs in the correspondingly named `docs/` directories.
- `docs/archive/` is read-only history (the former `tasks/` and process
  documents); do not add to it.
- Keep secrets out of git. Add new required variables to `.env.example` and,
  when production needs them, to the production configuration contract in
  `docs/architecture/deployment.md`.

## Rules

Always:

- Implement only the ticket's scope; prefer small changes and existing
  abstractions.
- Add or update tests with application code changes, or justify in the ticket
  why none are needed.
- Validate input, check authentication, and enforce authorization in the
  backend; use parameterized SQL or the ORM's safe queries.
- Change the schema only with a migration pair in `db/migrations/`
  (`NNN_name.sql` and `NNN_name.down.sql`), run with `backend/migrate.py`
  (ADR-002).

Never, without explicit human approval:

- add a dependency, delete a test, or change the architecture without an ADR;
- push to GitHub (the human pushes `main`);
- release to production, change the production database by hand, or run any
  production, backup, restore, or identity-provider operation.

Never at all:

- commit secrets or API keys, or hardcode them;
- use test or development data in production;
- log sensitive data.

Humans own the product direction, architecture, security, production
releases, and final approvals. AI writes code, tests, and documentation, does
scoped refactoring, and proposes architecture decisions.

## Agent workflow

Write a PRD in `.scratch/<feature>/PRD.md` before substantial user-facing
feature work, and settle its open decisions with the user (for example with
`/grilling`). Use a domain model when business terminology, lifecycle,
authorization, or an integration boundary needs settling before technical
design. Split the accepted design into small, verifiable tickets. The full
process is in `FEATURE_WORKFLOW.md`.

For architecture or tooling work that is not a user-facing feature, use
`.scratch/tech-<slug>/technical-design.md` and tickets instead. Implement one
ticket at a time. A ticket is complete only when its documentation impact,
executed checks, and AI review are recorded; see
`docs/agents/definition-of-done.md`.

When the ticket's checks pass, **start the AI review yourself without being
asked**: run the `code-review` skill on the diff, or start a fresh-context
subagent given only the ticket and the diff, at the effort the definition of
done sets by risk. Fix, recheck, and repeat for at most three rounds, then
record the result in the ticket and summarize it in one line of the commit
message.

## Branches and releases

`main` is the only branch pushed to GitHub (`lupaus-eu/shadow`), and only the
human pushes it. Agents never push.

1. Work directly on the local `main`; do not create branches.
2. Commit only when the ticket is done: its checks pass and its AI review is
   recorded. Keep unfinished work uncommitted, and never commit work whose
   checks fail. One ticket normally becomes one commit.
3. The human reviews the unpushed commits (`git log origin/main..main`) and
   pushes `main`. Pushing `main` runs CI. Container images are built only from
   a `v*` release tag, which the human creates and pushes.

Production releases need separate human approval.

If you are unsure, do not guess: check the ticket, the architecture, the
ADRs, and `CONTEXT.md`, and ask the human when they do not answer it.

## Agent skills

### Issue tracker

Work is tracked locally as PRDs, technical designs, and tickets under
`.scratch/`; GitHub Issues and pull requests are not a triage request surface.
See `docs/agents/issue-tracker.md`.

### Triage labels

The local status vocabulary and ticket lifecycle are defined in
`docs/agents/triage-labels.md`.

### Domain docs

This repository uses a single-context domain-doc layout with per-domain and
per-concept documents. See `docs/agents/domain.md`.

### Architecture and design routing

Select the feature-specific source documents with
`docs/agents/architecture-routing.md` before planning a change.
