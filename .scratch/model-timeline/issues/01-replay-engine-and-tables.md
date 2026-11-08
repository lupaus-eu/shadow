# Ticket 01: replay engine and tables

Status: implemented

## Goal

Add the line, Change, Edit and position tables and a pure replay engine that computes a state.

## Implementation

- Alembic migration 0060: `model_lines`, `timeline_changes`, `change_edits`, `node_positions` with RLS and grants.
- `backend/app/timeline/` with `state.py`, `chain.py` and `compact`; SQLAlchemy models; Pydantic edit payloads.
- Not done: data migration, routes, any change to existing tables.

## Acceptance criteria

- [x] Every edit op applies correctly and every invalid case raises `EditInvalid` with its cause.
- [x] A chain of a Scenario replays its ancestors' changes up to the branch change, then its own, ordered by date then entry order.
- [x] Compaction removes add-then-remove pairs and merges repeated updates.
- [x] New tables carry `organization_id`, RLS and are in the DBML (`make dbml`); `make models` passes.

## Testing

- [x] Backend/API test — replay and compaction unit tests, ordering, one-base-line constraint, RLS across Organizations
- [x] Frontend/UI test — not applicable, no UI
- [x] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — `alembic upgrade head` and `downgrade -1`, `make models`

## Ajetut tarkistukset

- [x] `pytest -q tests/test_timeline_engine.py` — passed, 17 tests (changes and causes, ordering, branches, as-of, breakage, compaction, generated sequences)
- [x] `pytest -q tests/test_timeline_tables.py` — passed, 4 tests (one Base line, branch-point protection, positions, row-level security)
- [x] `alembic upgrade head`, `downgrade -1`, `upgrade head` on the test database — passed
- [x] `pytest -q` (backend, whole suite) — passed, 222 tests
- [x] `make models` (LikeC4 and DBML validation, after `UPDATE_DBML=1 pytest tests/test_dbml_model.py`) — passed

## AI review

- [x] Self-review of the diff against the technical design: the engine takes the Metamodel as a value so it stays pure; `compact` verifies every candidate by replay and returns the original when unsure; `replay` no longer takes `line_id` because the failing event already carries it.

## Documentation effects

- [x] Update architecture or ADR — `docs/architecture/database.md` (migration 0060), `docs/architecture/project-layout.md` (timeline package), `docs/architecture/dbml/shadow.dbml` (regenerated, group `model_timeline`); ADR-0048 to ADR-0051 accepted
- [ ] Update `CONTEXT.md` — deferred to ticket 11, which retires and introduces the terms together

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

None.

## Completion record

- Migration 0060, the four SQLAlchemy models and the pure engine (`app/timeline/`: `state`, `chain`, `compact`, `payloads`, `errors`) are done, with all four acceptance criteria met. Nothing reads or writes the tables yet.
- Decisions made on the way: removing a node removes its connections in the same step (domain model, rule 3, updated); the engine returns `State` with each node's initial position, positions per line come with ticket 06; `C4` needed no change because no container or component boundary moved yet (the `timeline` package is a component to add with ticket 05).

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
