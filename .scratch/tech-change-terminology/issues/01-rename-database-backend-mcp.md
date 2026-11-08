# Ticket 01: rename database backend mcp

Status: implemented

## Goal

Rename event to Change and change to Edit in the database, backend, API, MCP, audit and limits.

## Implementation

- Two passes: first the inner "change" becomes "edit", then "event" becomes "change", following the rename map in `../technical-design.md` (code, tests, routes, JSON fields, MCP tools and arguments, audit actions, `LIMIT_CHANGES_PER_LINE`, hint codes).
- Migration 0065 renames `timeline_events` to `timeline_changes`, `event_changes` to `change_edits`, their columns, constraints, indexes, RLS policies, identity sequence and foreign keys; downgrade renames back; earlier migrations unchanged.
- Activity reads both `event.*` (old rows) and `change.*` audit actions.
- Not done: frontend (ticket 02), documents (ticket 03).

## Acceptance criteria

- [x] No stale use of the old words remains in `backend/` except the allowed list: Audit Event, Stripe events, migrations 0060 to 0064, legacy audit action names.
- [x] The migration upgrades a seeded 0064 database to 0065 and downgrades back with all rows intact.
- [x] The whole backend suite passes with the new names; the MCP call log, `test_no_llm_calls.py` and the performance test (`-m perf`) still pass.
- [x] DBML regenerated; `make models` valid; both env examples use `LIMIT_CHANGES_PER_LINE`.

## Testing

- [x] Backend/API test — full suite renamed; migration test with data; a guard test for allowed leftovers
- [ ] Frontend/UI test — not applicable (ticket 02)
- [ ] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — alembic up/down/up on a fresh schema, `make models`

## Ajetut tarkistukset

- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider` — passed: 296 passed, 1 deselected (perf).
- [x] `... -m pytest -q -p no:cacheprovider -m perf` — passed: 1 passed.
- [x] `tests/test_timeline_rename_migration.py` (in the full run) — passed: seeded 0064 schema upgraded to 0065 and back, rows identical, no object of the timeline tables keeps `event`; guard tests for stale tokens passed.
- [x] alembic upgrade head on a dropped and recreated `public` schema, `downgrade -1`, `upgrade head` — passed; catalog listing of constraints, indexes, policies and sequences identical before and after a 0064 -> 0065 -> 0064 round trip.
- [x] `UPDATE_DBML=1 ../.venv/bin/python -m pytest tests/test_dbml_model.py`, then `make models` — passed (DBML and LikeC4 valid).
- [x] `python3 scripts/check-compose-ports.py` — passed.
- [x] `grep -rniE event backend/app backend/tests` filtered by the allow-list — only Audit Event (`AuditEvent*`, `audit_events`, `record_audit_event`, `/audit-events`), Stripe/subscription/seat events, the Stripe tests' `evt_*`, migration tests that work at 0061/0062 (old table names), and the new rename test remain.

## AI review

- [x] Self-review of the diff (no separate tool): the word-level rename was scripted (`event` -> `change`, `change` -> `edit` only as whole words so `changed`, `unchanged`, `exchange`, `prevent` are untouched); `change_connection_type`, `change_summary`, `change_pct` and the audit-diff `changes` dicts were kept on purpose. Findings fixed by hand: name collision of the new `Edit` with the canvas planner (renamed `CanvasEdit`, `CanvasEditResponse`, MCP closure `canvas`), verbs that became `edits` in comments, articles (`a edit`), migration tests that run at 0060-0062 and keep the old table names, a missed constraint name (`uq_..._event_position`) found by the catalog round-trip.

## Documentation effects

- [x] Update architecture or ADR
- [x] Update `.env.example`

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

None.

## Completion record

- Done: Alembic 0065 (tables, columns, constraints, indexes, policies, identity sequence discovered from the catalog and renamed by one mapping; downgrade reverses it), ORM, replay engine (`ChangeRecord`, `Edit`, `EditInvalid`, `apply_edit(s)`), routes (`timeline_change_routes.py`, `/lines/{line}/changes`, `/changes/{change}`, `/changes/{change}/nodes|connections`), JSON (`change_id`, `branch_change_id`, `change_count`, `latest_change`, `latest_change_date`, `edits[]`, `edit_count`, `edit_counts`), MCP tools (`list_changes`, `add_change`, `update_change`, `delete_change`, argument `change_id`, `edits`), audit actions `change.created|updated|deleted` with target type `change`, hint codes `missing_branch_change`, `before_branch_change`, `LIMIT_CHANGES_PER_LINE` (limit key `changes_per_line`), tests renamed, `test_timeline_rename_migration.py` (migration with data and two guard tests), DBML regenerated. All four acceptance criteria met.
- Allowed leftovers of "event" in `backend/`: Audit Event names, Stripe/subscription/seat events, migrations 0060-0064 (unchanged), `test_timeline_migration.py` and `test_metrics_by_line.py` SQL at revisions 0061/0062, the legacy `event.*` audit actions (Activity filters by prefix or action, so both vocabularies work; the labels are the frontend's, ticket 02, which must label `event.*` and `change.*`), `LIMIT_EVENTS_PER_SHADOW`/`LIMIT_LABELS_PER_EVENT`/`LIMIT_BULK_EVENTS`/`LIMIT_REVISIONS_PER_EVENT` (legacy Yearclock variables, not this rename).
- Not done by design: `frontend/` is broken until ticket 02; `docs/architecture/api.md` still shows `limit: "events_per_line"` and the old routes, and the MCP runbook, database.md and audit.md still use the old words (ticket 03). Only the env variable name was updated in `docs/admin/README.md`, `docs/operations/README.md` and `docs/architecture/operational-limits.md`.
- Documentation effects: `.env.example`, `.env.production.example`, `docs/architecture/operational-limits.md`, `docs/architecture/dbml/shadow.dbml`; no ADR change needed (ADR-0052 describes this).

## Comments

- Design: `../technical-design.md`; decision: ADR-0052.
