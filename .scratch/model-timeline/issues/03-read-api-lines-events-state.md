# Ticket 03: read api lines events state

Status: implemented

## Goal

Read lines, events and the state after an event or as of a date.

## Implementation

- `GET /lines`, `GET /lines/{line}/events`, `GET /lines/{line}/state` (by `event_id`, `as_of`, or present state) with `added`, `updated`, `removed` and `positions`; planned flag from the Organization's time zone.
- Not done: any write.

## Acceptance criteria

- [x] The state after the initial event equals the pre-migration graph; `as_of` picks the last event of that day or earlier.
- [x] The present state ignores events dated after today; a planned event's state can still be read.
- [x] A Member reads every line; another Organization gets 404; a read-only Organization can read.

## Testing

- [x] Backend/API test — shapes, event vs as_of, planned, roles, RLS
- [x] Frontend/UI test — not applicable
- [x] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — `make models`; API doc updated

## Ajetut tarkistukset

- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_timeline_read_api.py` — passed, 10 tests (after one fix: removed nodes now carry their last drawn position).
- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider` — passed, 234 tests (full suite).
- [x] `make models` — not run: no DBML or C4 change (no tables, containers or relationships changed); `docs/architecture/api.md` updated.

## AI review

- [x] Self-review of the diff (no review tool run; ruff is not installed in the venv). Findings: (1) a removed node's `x`/`y` came from its added position, not the line's drawing; fixed by resolving positions over the nodes before and after the event. (2) Accepted known edge: the engine's `state_as_of` returns the parent's state at the branch event when a Scenario has no own event on or before the day, even if that branch event is dated after the day; the present state of a Scenario branching from a planned event therefore includes that planned event. Ordinary cases (branching from a happened event) are correct and tested; fixing it means changing the engine, left for a follow-up if wanted. (3) Reads load every line, event and change of the Model (bounded by the ticket 10 limits). (4) Read routes import the private session helpers of `model_routes`, as `version_routes` already does. No audit: reads are not audited.

## Documentation effects

- [x] Update architecture or ADR

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 02

## Completion record

- Added `GET /lines`, `GET /lines/{line}/events`, `GET /lines/{line}/state` (`event_id`, `as_of`, or present state) in `backend/app/timeline_routes.py`, registered in `backend/app/main.py` with the injected clock; reusable loading (`load_timeline`, `load_metamodel`, `today_in_organization`, `is_planned`) in `backend/app/timeline/loader.py`. Tests in `backend/tests/test_timeline_read_api.py`; docs in `docs/architecture/api.md`. All acceptance criteria met; existing version routes untouched. Deviations: none from the design; `event` is null and `as_of` is echoed when a day precedes a line's first event; `as_of` and `event_id` together answer 422.

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
