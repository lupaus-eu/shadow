# Ticket 06: scenarios and positions

Status: implemented

## Goal

Create, rename and delete Scenarios from any change, and store node positions per line.

## Implementation

- `POST /lines` (branch from any change of any line; copies parent's metrics and values), `PATCH`, `DELETE` (409 `has_children`, 422 base), `acknowledge-start`; `start_changed_at` set when a prefix change affects a Scenario.
- `PUT /lines/{line}/positions` with fallback to the parent line, then to the added position; no change, no audit.
- Audit `line.created`, `line.renamed`, `line.deleted`.

## Acceptance criteria

- [x] A Scenario shows the parent's state at its branch point and its own changes; later parent changes do not appear, earlier inserted ones do and set `start_changed_at`.
- [x] Scenario of a Scenario works to any depth.
- [x] Creator, Owner or Admin may delete a Scenario without children; the Base line cannot be deleted.

## Testing

- [x] Backend/API test — branching depth, inheritance rules, notice, delete rules, positions fallback, roles
- [x] Frontend/UI test — not applicable
- [x] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — `pytest -q`, `make dbml`

## Ajetut tarkistukset

- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_timeline_lines.py` — passed, 13 tests
- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider` — passed, 270 tests (an earlier full run failed in `test_timeline_migration.py`: metrics of Scenarios made by the new route have no version row and 0062's downgrade drops them, which the shared-database row count saw; the new test file now removes such rows after each test)
- [x] `cd docs/architecture/c4 && npx --yes likec4@1.59.4 validate` — passed (4 files). `make dbml` not run: no table or column changed (the DBML test is part of the full run)

## AI review

- [x] Self-review of the diff against the domain model's authorization matrix and ADR-0048/0049 — findings: (1) the C4 description had an apostrophe that broke LikeC4 validation, fixed; (2) metrics.node_id still has a foreign key to the old `nodes` table, so a copied metric keeps its node only when the node exists at the branch point and still has an old row, otherwise the link is dropped (ticket 08 remaps it); (3) positions take no Model lock, so a concurrent event delete can leave one orphan position row, accepted (harmless, ignored by reads, removed with the line)

## Documentation effects

- [x] Update architecture or ADR: `docs/architecture/api.md` (Scenarios and positions, line fields), `docs/architecture/audit.md` (line actions), `docs/architecture/c4/model.c4` (component technology and description). No DBML change (no schema change); ADR-0048 already states the rules

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 05

## Completion record

- `backend/app/timeline_line_routes.py` (registered in `backend/app/main.py`): `POST /lines`, `PATCH` and `DELETE /lines/{line}`, `POST .../acknowledge-start`, `PUT .../positions`; tests in `backend/tests/test_timeline_lines.py`. All acceptance criteria met; effects recorded in api.md, audit.md and the C4 model.
- Decisions: position writes follow the line write rule (Base line Owner or Admin, Scenario any Member), need the node in the line's state at its latest event (422 `unknown_node`, all or nothing), and write no event, audit or version. Deleting the Base line answers 422 before the role check. `DELETE` takes an optional `expected_version`. Rename and delete also update or remove the old version row of a Scenario that came from a fork (until ticket 08). `GET /lines` and the state already carried `start_changed_at` and `created_by_user_account_id`; nothing was missing.

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
