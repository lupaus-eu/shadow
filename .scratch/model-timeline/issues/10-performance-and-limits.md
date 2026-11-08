# Ticket 10: performance and limits

Status: implemented

## Goal

Measure the state read, event list and writes at the target size and record the result.

## Implementation

- A script that builds a model with 2000 events and 500 nodes and times `state`, `events` and a validated write on the development stack.
- Not done: caching; added only if the numbers fail.

## Acceptance criteria

- [x] Each of state and event list loads in under two seconds; the numbers are written into the technical design.
- [x] If a number fails, a follow-up ticket for snapshots exists. (No number failed; no follow-up ticket was needed.)

## Testing

- [x] Backend/API test — the script asserts the thresholds
- [ ] Frontend/UI test — not applicable
- [ ] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — script run recorded

## Ajetut tarkistukset

- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider -m perf -s tests/test_timeline_performance.py` — passed (1 passed in 6.2 s); state 0.212/0.174/0.205 s, events 0.218/0.213/0.220 s, validated write 0.359/0.357/0.388 s.
- [x] `... pytest -q -p no:cacheprovider tests/test_timeline_engine.py tests/test_timeline_performance.py` — passed, 18 passed and 1 deselected: the perf test stays out of the normal run.

## AI review

- [x] Self-review of the diff (no separate tool): the data is inserted directly, so the routes are what is timed, and the model is checked (2000 events, 500 nodes) before timing. The first build is not part of the measurement. Accepted limit: the TestClient runs in-process, so network time is excluded; the numbers are for this machine only.

## Documentation effects

- [x] Update architecture or ADR: `.scratch/model-timeline/technical-design.md` (Testing and Performance); `backend/pytest.ini` (marker `perf`). No ADR change: the design is unchanged and no caching was added.

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 05
- 06

## Completion record

- Added `backend/tests/test_timeline_performance.py` (marker `perf`, excluded by default in `backend/pytest.ini`) which builds 2000 events and 500 nodes with Scenarios and asserts state under 2 s, events under 2 s and a validated write under 5 s. All three met with about a tenth of the limit; numbers and machine note are in the technical design. No snapshots follow-up was needed (ticket 12 was not created). The PRD criterion on load times is ticked in ticket 11.

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
