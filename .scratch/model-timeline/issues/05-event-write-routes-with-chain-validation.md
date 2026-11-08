# Ticket 05: change write routes with chain validation

Status: implemented

## Goal

Create, update, move and delete Changes, refusing any write that breaks the chain.

## Implementation

- `POST /lines/{line}/changes`, `PATCH` and `DELETE /changes/{change}` with `expected_version`; `validate_model` with the Model row lock; `422 chain_broken` with change, position, element, cause and hint; `409 branch_point`; Base line writes need Owner or Admin.
- Planned changes allowed in any line; limits `LIMIT_CHANGES_PER_LINE` and `LIMIT_LINES_PER_MODEL` in both env examples.
- Audit actions `change.created`, `change.updated`, `change.deleted` without element names.
- Not done: canvas edit routes (ticket 07), Scenarios (ticket 06).

## Acceptance criteria

- [x] Every cause in the domain model is refused and nothing is saved; a valid correction (date moved, content changed) succeeds and later states update.
- [x] Deleting the branch change of a Scenario is refused and names the Scenario.
- [x] A Member's write to the Base line gets 403; to a Scenario succeeds.
- [x] Two concurrent writes cannot together break the chain.

## Testing

- [x] Backend/API test — each cause, branch point, roles, stale 409, lock behaviour, audit content, limits
- [x] Frontend/UI test — not applicable
- [x] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — `pytest -q`; GDPR note on audit content

## Ajetut tarkistukset

- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_timeline_events.py` — passed, 18 tests.
- [x] Same command without the file argument (full backend suite, includes `test_dbml_model.py`, `test_no_llm_calls.py`) — passed, 257 tests.
- [x] Mutation check: with `lock=True` removed from the three event routes the lock test failed (the write no longer waits for the Model row); restored, passes. The two-writer race test passes either way on this machine (the race window is narrow), so the deterministic lock test is the proof of the lock.
- [x] `npx --yes likec4@1.59.4 validate docs/architecture/c4` (the C4 half of `make models`) — passed, 4 files, including the new Model timeline component and the `eventWrite` view.
- [x] `python3 scripts/check-compose-ports.py` — passed (no Compose file changed; the new variables are not listed in Compose, like the other recent `LIMIT_*` ceilings).
- Not applicable: frontend checks, browser checks, DBML regeneration (no migration, no schema change).

## AI review

- [x] Self-review of the diff against ADR-0049, the domain model and the technical design (no review skill run). Findings: (1) the first duplicate-element hint named the node with the failing add's own name; fixed by leaving the failing change out of the name search (tested). (2) A deleted add event would have lost the node name needed for the refusal of a later event; fixed by searching the pre-write events too (tested). (3) `branch_prefix` compares event ids only, so editing the content of an event inside a Scenario's prefix would not have marked its start as changed; the check now compares the prefix events' changes too, and a title-only edit still does not (tested). (4) `missing_branch_event` cannot be produced through the API because a composite foreign key keeps a branch event in its parent line and deletion is refused first; it is tested as a unit on `describe_break`. Accepted: no cap on changes per event (the body size and the events limit bound a write).

## Documentation effects

- [x] Update architecture or ADR
- [x] Update `docs/operations/` or `docs/runbooks/`
- [x] Update `docs/gdpr/` or `docs/legal/`
- [x] Update `.env.example`

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 03

## Completion record

- Added `POST /lines/{line}/events`, `GET`/`PATCH`/`DELETE /events/{event}` (`backend/app/timeline_event_routes.py`) and `backend/app/timeline/validate.py` (`validate_model`, `describe_break`, `ChainRefused`). Every write locks the Model row, loads the timeline, applies the mutation in memory, replays the changed line and every descendant Scenario, and refuses with 422 `chain_broken` (ids plus a structured `hint`), 409 `branch_point` (checked first on delete), 409 stale with `latest_version`, 403 for a Member on the Base line or a read-only Organization. Scenarios whose starting point changed get `start_changed_at`. Changes are numbered 0..n-1; added nodes get a position row on the line; positions of nodes no event adds any more are dropped. Audit `event.created|updated|deleted` carries ids, date and change counts only. `LIMIT_EVENTS_PER_LINE` (enforced) and `LIMIT_LINES_PER_MODEL` (declared, enforced by ticket 06) in `limits.py` and both env examples.
- All four acceptance criteria met; tests in `backend/tests/test_timeline_events.py`.
- Documentation: `docs/architecture/api.md`, `audit.md`, `operational-limits.md`, `docs/operations/README.md`, `docs/gdpr/README.md`, `.env.example`, `.env.production.example`, C4 (`model.c4`, `views.c4`). No documentation effect: DBML (no schema change), ADRs (decisions unchanged), `docs/user` and `docs/admin` (ticket 11), `docs/runbooks/mcp-interface.md` (ticket 08).
- Notes for later tickets: ticket 06 must enforce `LINES_PER_MODEL` (`app.limits`) when creating Scenarios and may reuse `_may_write`, `_validate` and `_restart` from `timeline_event_routes.py`; ticket 07 can use `validate_model` with a `Mutation`, `compact`, and `_store_changes`; ticket 08 reaches the endpoint functions by route name (`create_event`, `update_event`, `delete_event`, `read_event`) with `request` and `user`.

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
