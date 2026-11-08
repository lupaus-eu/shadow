# Ticket 04: metrics simulations analysis by line

Status: implemented

## Goal

Make metric, simulation and analysis routes, the MCP read tools and the analysis page work on a line.

## Implementation

- Migration 0062: `line_id` on `metrics`, `metric_values` and `simulations` (added nullable by 0061) becomes required and `version_id` is dropped. Rows left without a `line_id` (versions forked by the old routes after 0061, which have no line) are removed with their version's data; development databases only, nothing is released.
- New Models already get a Base line with the same id as their baseline version (ticket 02), so existing metric and simulation rows map to the Base line by id.
- Routes take `line_id` where they took `version_id`; graph reads inside them use the state function.
- MCP read tools and `run_simulation`, `generate_analysis` take `line_id`.
- Not done: scenario creation (ticket 06), frontend (ticket 09).

## Acceptance criteria

- [x] Every existing metric, simulation and analysis test passes with the Base line in place of the baseline version.
- [x] Formulas and derived metrics are scoped to a line.
- [x] The MCP call log still records the calls.

## Testing

- [x] Backend/API test — existing suites ported to lines
- [x] Frontend/UI test — client types updated, typecheck
- [x] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — `pytest -q`, `test_no_llm_calls.py`

## Ajetut tarkistukset

- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider` — passed, 239 tests (includes the ported metric, import/export, simulation, analysis, version, MCP and timeline-migration suites, `test_no_llm_calls.py`, and the new `tests/test_metrics_by_line.py`: fork creates the Scenario line and copies metrics line-wise, base line without event gets "Initial situation", 404 for unknown or other-Model lines, node_id validation, migration 0062 with legacy rows and downgrade).
- [x] `UPDATE_DBML=1 ../.venv/bin/python -m pytest tests/test_dbml_model.py` then `make models` — passed (DBML regenerated, LikeC4 valid).
- [x] Alembic on a fresh schema (drop and recreate `public`): `upgrade head`, `downgrade -1`, `upgrade head` — passed, head `0062`.
- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build && npm --prefix frontend run test:unit` — passed (23 unit tests).
- Browser/E2E: not run (not applicable; the tabs only changed the URL and the `line_id` field).

## AI review

- [x] Self-review of the diff by the implementing agent (no separate review tool run). Findings: (1) 0061 left rows written by the old routes after it without `line_id`, so dropping them wholesale would also lose baseline metrics created after 0061; 0062 first sets `line_id = version_id` where a line of that id exists and deletes only the rest (resolved, tested). (2) Versions forked after 0061 have no line and would stay as dead versions; 0062 deletes those non-baseline versions with their graphs (resolved, tested). (3) `metrics.node_id` still has its FK to `nodes`; node validation therefore checks the old table (accepted until ticket 08, recorded below). (4) Audit entity type of metric value import changed from `model_version` to `model_line`, and the `simulation.created` summary key `version` became `line` (accepted; same name content as before).

## Documentation effects

- [x] Update architecture or ADR

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 03

## Completion record

- Migration `0062_metrics_by_line.py`: `line_id` required and `version_id` dropped on `metrics`, `metric_values`, `simulations` (rows kept by id when a line exists; orphan rows and non-baseline versions without a line deleted). Metric, metric import/export and simulation routes moved from `.../versions/{version_id}/...` to `.../lines/{line_id}/...` (`Simulation` response field `line_id`); `series_of_version` became `series_of_line`; `line_of()` in `model_routes.py`; analysis routes only needed the formulas query by `line_id` (they are keyed by simulation id). MCP tools `list_metrics`, `get_metric_series`, `create_metric`, `set_metric_values`, `list_simulations`, `get_simulation`, `run_simulation` take `line_id` (`get_analysis`, `generate_analysis`, `set_analysis_summary`, `add_proposal` take a simulation id and were unchanged); the call log is untouched.
- Interim rules: the old fork route creates a Scenario line with the new version's id (branch event = parent line's last event; an empty "Initial situation" event is created first if the parent has none), copies metrics line-wise; renaming a version renames the line; deleting a version deletes the line. The old node routes still write only the old tables, so a line's replayed state does not yet include nodes added through them.
- Frontend: `frontend/src/models/client.ts` sends the selected version id as `line_id` in the new URLs; no UI change.
- For ticket 08: `metrics.node_id` still references `nodes.id`; remap it to element ids (a Scenario fork node may carry its origin's element id, so the old id and element id can differ) before dropping `nodes`, then validate `node_id` against the line state (`_validate_node` in `metric_routes.py` currently checks the old table, with `Node.version_id == line_id`). Remove `fork_version`'s line creation and `copy_metrics`' node mapping when the old fork route goes (ticket 06 provides the Scenario creation).
- Documentation: `docs/architecture/api.md`, `docs/architecture/database.md`, `docs/architecture/dbml/shadow.dbml`, `docs/architecture/c4/model.c4`. No documentation effect for `docs/runbooks/mcp-interface.md` (it lists no tool arguments) and the MCP tool docstrings carry the `line_id` argument; ADRs unchanged (ADR-0048 already decides lines carry metrics).

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
