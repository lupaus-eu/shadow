# Ticket 08: adopt scenario mcp tools and retire versions

Status: implemented

## Goal

Adopt a Scenario into its parent, add the MCP tools, and remove versions and merge.

## Implementation

- `POST /lines/{line}/adopt` per ADR-0050 with chain check and audit `line.adopted`.
- MCP: `list_lines`, `list_changes`, `get_state`, `create_scenario`, `add_change`, `update_change`, `delete_change`, `adopt_scenario`; `create_version`, `merge_version`, `get_version_changes` removed.
- Migration 0064 drops `nodes`, `connections`, `model_versions`; version routes removed; ADR-0045 marked superseded and ADR-0048 to 0050 accepted. (Ticket 07 took the number 0063 for the `metrics.node_id` remap, which is therefore already done; the old version `edits` and `merge` routes and the MCP tools `merge_version` and `get_version_changes` were also removed in ticket 07, so ticket 08 removes only what remains: the version list, create, rename and delete routes, `create_version`, `GET /models/{id}` with `version_id`, and the frozen old tables with the `in_use` checks that still look at them in `metamodel_routes.py`.)

## Acceptance criteria

- [x] Adopt succeeds only when the parent has no changes after the branch point and dates do not precede its last change; otherwise a readable refusal with the suggestion.
- [x] Owners and Admins adopt into the Base line; metrics are not adopted.
- [x] All new MCP tools obey roles, read-only state, chain check and the call log.

## Testing

- [x] Backend/API test — adopt cases, roles, MCP tools, call log
- [ ] Frontend/UI test — not applicable
- [ ] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — upgrade/downgrade, `make models`, `make dbml`

## Ajetut tarkistukset

- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider` — passed, 292 passed (includes `test_no_llm_calls.py`, `test_timeline_adopt.py` 8, `test_model_graph_by_line.py` 2, the new MCP line/event/adopt test, migration 0064 up/down, and the 0061/0062/0063 migration tests reworked to seed the old tables at the old schema)
- [x] `alembic upgrade head`, `downgrade -1`, `upgrade head` on a fresh schema (script with `command.upgrade/downgrade` against the test database) — passed, ends at `0064`
- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build && npm --prefix frontend run test:unit` — passed (typecheck clean, build ok, 23 unit tests passed)
- [x] `UPDATE_DBML=1 ../.venv/bin/python -m pytest tests/test_dbml_model.py` (backend/) then `make models` — passed (LikeC4 valid, DBML test passed, `dbml2sql` generated the PostgreSQL dump)
- [x] Browser/E2E — not applicable (ticket 09 builds the real UI); the interim line picker was only type-checked and built

## AI review

- [x] Review run on the ticket's diff — read by the implementing agent against ADR-0049/0050 (no separate review tool run). Findings: (1) ADR-0050 left the children of a kept Scenario unspecified although their branch events are the Scenario's own events; resolved by re-attaching them to the parent at the adopted copies (states unchanged) and recording it in ADR-0050, the technical design and `api.md`; (2) the `dates_precede` refusal cannot arise from application writes (they keep Scenario events on or after the branch event, which is the parent's last event after a fast-forward), so it is a guard tested by changing the data directly; (3) the 0064 downgrade rebuilds `model_versions` from the lines, not only empty tables, so the older downgrades do not delete every metric; accepted and documented.

## Documentation effects

- [x] Update architecture or ADR
- [x] Update `docs/operations/` or `docs/runbooks/`

Updated: `docs/adr/0045-merge-a-version-by-applying-its-change-list-to-its-base.md` (superseded by ADR-0050), `docs/adr/0050-replace-version-merge-with-fast-forward-adoption.md` (children, positions, closing line), `docs/adr/0046-expose-model-tools-through-mcp-by-calling-the-rest-endpoints.md` (delete tools), `docs/architecture/api.md` (version routes removed, adopt, `GET /models/{id}` by `line_id`, MCP tools), `docs/architecture/database.md` (0064), `docs/architecture/audit.md` (`line.adopted`), `docs/architecture/dbml/shadow.dbml` (regenerated), `docs/architecture/c4/model.c4` and `docs/architecture/c4/README.md` (components without versions, adoption), `docs/runbooks/mcp-interface.md` (tool list and arguments), `.scratch/model-timeline/technical-design.md`. No effect on `docs/user/` and `docs/admin/` (no page mentions model versions or merge; the vocabulary pass is ticket 11), `docs/operations/` (no new variable, port or service) or `.env.example` (no new variable).

## Blocked by

- 06
- 07

## Completion record

- Finished: `POST /lines/{line}/adopt` (fast-forward, structured refusals `parent_moved_on`, `dates_precede`, `nothing_to_adopt`, chain check, roles by the parent's write rule, positions copied, children re-attached, audit `line.adopted`); MCP tools `list_lines`, `list_events`, `get_state`, `create_scenario`, `add_event`, `update_event`, `delete_event`, `adopt_scenario` (`create_version` removed, `get_model` takes `line_id`, `list_models` gives `base_line_id`); migration 0064 drops `nodes`, `connections`, `model_versions`; the version routes, `fork_version`, the baseline version on Model creation, the `in_use` checks against the old tables and the ORM classes are gone; the interim web line picker ("New scenario", delete) works on lines. All three acceptance criteria are met; evidence is in `## Ajetut tarkistukset`, documentation effects above.
- Deviations: the 0064 downgrade refills `model_versions` from the lines (nodes and connections stay empty) instead of rebuilding graphs; children of an adopted Scenario move to the parent (see AI review).

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
