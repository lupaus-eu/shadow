# Ticket 02: migrate versions to lines

Status: implemented

## Goal

Convert existing versions, graphs, metrics and simulations to lines and changes.

## Implementation

- Migration 0061: baseline version to Base line with one "Initial situation" change (dated the Model's creation day in the Organization's time zone); each fork to a Scenario with one difference change (dated the fork's creation day, never before its branch change; none when there is no difference); positions to `node_positions`; a Base line for every Model, also one with no baseline version.
- `line_id` is ADDED to `metrics`, `metric_values` and `simulations` (nullable, backfilled from `version_id`, indexed, foreign keys to `model_lines`). `version_id` is NOT dropped here: existing routes still use it and the whole backend suite stays green; ticket 04 makes `line_id` required and drops `version_id`.
- A line takes its version's id. Element ids are preserved: baseline nodes and connections keep theirs, fork nodes and connections that exist in the base reuse the base's element id, so replayed states can be compared with the old graphs. `metrics.node_id` is untouched (ticket 08 remaps it before dropping `nodes`).
- New Models: model creation (`backend/app/model_routes.py`) creates a Base line (same id as the baseline version) with an empty "Initial situation" change dated today in the Organization's time zone, next to the old baseline version, so rule 1 holds from now on.
- Not done: other routes and frontend; `nodes`, `connections`, `model_versions` stay until ticket 08.
- Downgrade drops the `line_id` columns and the generated lines, changes and positions (the old tables are intact, so nothing needs rebuilding).

## Acceptance criteria

- [x] A database with versions, forks, graphs, metrics and simulations upgrades with nothing lost: replayed states equal the old graphs.
- [x] Fork of a fork branches from its base fork's last change.
- [x] Downgrade drops the `line_id` columns and the generated lines, changes and positions; `model_versions`, `nodes` and `connections` are intact (they are not dropped until ticket 08).
- [x] A new Model gets a Base line with an empty "Initial situation" change at creation.

## Testing

- [x] Backend/API test — `backend/tests/test_timeline_migration.py`: seeded database (baseline, forks, fork of fork, unchanged forks, pruned fork, a baseline that moved on, metrics, a simulation), downgrade to 0060 and upgrade, replayed state equals old graphs, ids/positions/metric values preserved, branch rules, new-Model Base line
- [x] Frontend/UI test — not applicable
- [x] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — `alembic upgrade head`, `downgrade -1`, `upgrade head`; DBML regenerated; `make models`

## Ajetut tarkistukset

- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_timeline_migration.py` — passed (2 tests)
- [x] `cd backend && TEST_DATABASE_URL=... ../.venv/bin/python -m pytest -q -p no:cacheprovider` — passed, 224 tests (the four tests of `test_timeline_tables.py` now delete the Base line a new Model comes with)
- [x] On the test database after `DROP SCHEMA public CASCADE; CREATE SCHEMA public`: `DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head`, `alembic current` — passed, ends at `0061 (head)`
- [x] `UPDATE_DBML=1 ../.venv/bin/python -m pytest tests/test_dbml_model.py` (backend/) then `make models` (repo root) — passed; DBML regenerated

## AI review

- [x] Self-review of the diff (no external tool) — findings: (1) a fork with no difference would need an empty event, but a Scenario can only branch from an event of its parent; resolved by creating no event and letting a fork of it branch where its base does. (2) The old diff matches connections by (type, origin source, origin target), so the migration reuses that rule for connection element ids; a re-route therefore appears as remove plus add. (3) Two type changes on neighbouring nodes in one fork could pass through an intermediate state the metamodel forbids when replayed; accepted as unlikely, the migration does not validate by replay (the old routes enforced the metamodel; the replay engine proves equality in the test). (4) Dates use the Organization's time zone; fork event dates are raised to the branch event's date. (5) `line_id` stays nullable and rows written by old routes after 0061 have none; recorded in ticket 04.

## Documentation effects

- [x] Update architecture or ADR — `docs/architecture/database.md` (0061 entry), `docs/architecture/dbml/shadow.dbml` (regenerated), `.scratch/model-timeline/technical-design.md` (database section, migration numbers), tickets 04 and 08. C4: no new component or boundary, so no change. ADRs: ADR-0048's migration text still holds; no change.

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 01

## Completion record

- Migration 0061 and the new-Model Base line are done; all acceptance criteria are met except that downgrade does not rebuild the old tables because they are still there (scope adjusted in this ticket and in tickets 04 and 08). Effects recorded in the documentation list above; checks listed under `## Ajetut tarkistukset`.

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
