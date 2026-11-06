# Agent Instructions

Before editing implementation code, read these files in order:

1. `docs/architecture/stack.md`
2. `docs/architecture/project-layout.md`
3. `docs/architecture/docker.md`
4. `CONTEXT.md`
5. The relevant feature material under `.scratch/`

Keep changes scoped to the requested task. Update documentation when a change
affects service boundaries, the data model, environment variables, deployment
behavior, permissions, or an external integration. Keep the C4 model
(`docs/architecture/c4/`) and the generated DBML
(`docs/architecture/dbml/yearclock.dbml`) current in the same change.

## Local commands

- Start the full stack: `make up` (or `docker compose up --build`)
- Stop the local stack: `make down` (or `docker compose down`)
- Other shortcuts: `make help` (logs, tests, port check, Stripe webhook forwarding)
- Frontend only: `cd frontend && npm install && npm run dev`
- Backend only: `cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8100`
- Backend checks: `cd backend && pytest -q`
- Frontend checks: `npm --prefix frontend run typecheck && npm --prefix frontend run build`
- Browser checks: `npm --prefix frontend run test:browser` (with the required local services running)
- Compose port check: `python3 scripts/check-compose-ports.py`
- Architecture models: `make models` (validate), `make c4` (browse views on
  8176), `make dbml` (regenerate the DBML after a migration)

## Conventions

- Keep frontend code under `frontend/src`.
- Keep backend API code under `backend/app`.
- Add shared decisions to `docs/adr`.
- Feature PRDs, technical designs, domain models, and implementation tickets
  belong in `.scratch/`; copy `.scratch/_template/` to start a new feature.
- UI and UX guidance belongs in `docs/design`; user, administrator, operations,
  and privacy guidance belongs in the correspondingly named `docs/` directories.
- Keep secrets out of git. Add new required variables to `.env.example` (local
  development) and, when production needs them, to `.env.production.example`.
- Yearclock owns host ports 8100–8199 on shared development machines. Publish
  a Compose port only as
  `"${YEARCLOCK_BIND_ADDRESS:-127.0.0.1}:${YEARCLOCK_<SERVICE>_PORT:-81NN}:<container port>"`,
  keep the top-level `name: yearclock`, and never set `container_name`. Host
  processes outside Compose (Vite, uvicorn, Playwright) also use this range.
  Record every assigned port in `docs/architecture/docker.md` and run
  `python3 scripts/check-compose-ports.py` after changing a Compose file.

## Agent workflow

Write a PRD in `.scratch/<feature>/PRD.md` before substantial user-facing
feature work. Use a domain model when business terminology, lifecycle,
authorization, or an integration boundary needs settling before technical
design. Split the accepted design into small, verifiable tickets.

For architecture or tooling work that is not a user-facing feature, use
`.scratch/tech-<slug>/technical-design.md` and tickets instead. Implement one
ticket at a time. A ticket is complete only when its documentation impact and
executed checks are recorded; see `docs/agents/definition-of-done.md`.

## Agent skills

### Issue tracker

Work is tracked locally as PRDs, technical designs, and tickets under
`.scratch/`; external pull requests are not a triage request surface. See
`docs/agents/issue-tracker.md`.

### Triage labels

The local status vocabulary and ticket lifecycle are defined in
`docs/agents/triage-labels.md`.

### Domain docs

This repository uses a single-context domain-doc layout. See `docs/agents/domain.md`.

### Architecture and design routing

Select the feature-specific source documents with
`docs/agents/architecture-routing.md` before planning a change.
