# Ticket 07: canvas edit routes and in use

Status: implemented

## Goal

Make node and connection edits changes inside an event, and make `in_use` checks respect events.

## Implementation

- `POST/PATCH/DELETE /events/{event}/nodes` and `/connections` replace the `/nodes` and `/connections` routes; each edit is validated, compacted and written as one change.
- MCP `create_node` and `create_connection` take `event_id`.
- Metamodel deletes (`in_use`) check events and branches.
- Migration 0063 drops the foreign key `metrics.node_id` → `nodes.id` and remaps the values to element ids; `_validate_node` checks the line's current state.
- The old version changes and merge routes (and the MCP tools `get_version_changes`, `merge_version`) are removed (their tests too); a fork no longer copies nodes. Ticket 08 retires the rest of the version routes.
- Interim frontend: the Structure canvas edits the line's last event (creating an "Edits" event when the line has none) and loads the graph from `GET lines/{line}/state`.

## Acceptance criteria

- [x] Adding then removing an element in one event leaves no change; renaming twice leaves one.
- [x] A refusal returns the chain_broken body and leaves the event unchanged.
- [x] A type used by any event cannot be deleted (409 `in_use`).

## Testing

- [x] Backend/API test — edits, compaction, refusal, in_use, MCP tools
- [x] Frontend/UI test — client types updated, typecheck, build and unit tests
- [x] Browser/E2E validation — not applicable (the interim canvas is replaced by ticket 09, which owns the browser test)
- [x] Migration/integration/architecture validation — `pytest -q`

## Ajetut tarkistukset

- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider` — passed, 283 passed (new: `tests/test_timeline_edits.py` 11 tests for the edit routes, `test_metamodel.py` in_use against events and rules, `test_metrics_by_line.py` metric node validation and migration 0063, `test_timeline_engine.py` compaction of connection edits and no-ops, `test_mcp.py` event-based tools; `test_models_graph.py`, `test_model_versions.py`, `test_timeline_migration.py` ported)
- [x] Fresh schema, `Config("alembic.ini")` with `sqlalchemy.url` of an empty database: `command.upgrade(c, "head")`, `command.downgrade(c, "-1")`, `command.upgrade(c, "head")` — passed (0063 down and up); migration 0063 also round-trips in `test_migration_0063_remaps_metric_nodes_to_element_ids_and_drops_the_foreign_key`
- [x] `UPDATE_DBML=1 ../.venv/bin/python -m pytest tests/test_dbml_model.py` in `backend/`, then `make models` — passed (C4 valid; DBML regenerated for revision 0063; dbml2sql generated)
- [x] `npm --prefix frontend run typecheck` — passed
- [x] `npm --prefix frontend run build` — passed (vite chunk-size warning only)
- [x] `npm --prefix frontend run test:unit` — passed, 23 of 23 tests
- [x] Browser/E2E — not run: the interim canvas was only type-checked and built; ticket 09 owns the browser test of the real UI

## AI review

- [x] Review run on the ticket's diff — `/code-review medium` (Claude Code skill). Findings and handling: (1) `_model_response` now replays the Base line per Model, so `GET /models` costs one timeline load per Model: accepted for now, `graph_of` reuses its timeline; ticket 10 measures it. (2) `fork_version` copied metric node ids unfiltered: fixed, a copy keeps only nodes in the base's latest state. (3) Removing a node by event leaves `metrics.node_id` pointing at it (the old foreign key set it NULL): accepted and recorded below, a metric that already has a node can still be saved, a new choice is validated against the current state. (4) Migration name and per-row update: the constraint name is checked by the fresh-schema upgrade, the dev data is small; accepted. (5) A fresh Scenario has no event, so `latest_event` is null: the canvas creates an "Edits" event, the tool text says so. (6) `_drop_noops` replays once more per edit: accepted (graphs are small). (7) `in_use` payload query had no model filter: fixed with a join on `timeline_events.model_id`. (8) Stale MCP docstring: fixed; the removed merge and change-list tools have no replacement until ticket 08 (adoption).

## Documentation effects

- [x] Update architecture or ADR

Updated: `docs/architecture/api.md` (edit routes, removed routes, `latest_event`, `in_use`, metric `node_id`, MCP tools), `docs/architecture/database.md` (0063), `docs/architecture/dbml/shadow.dbml` (regenerated), `docs/architecture/c4/model.c4`, `docs/architecture/c4/views.c4` (the `versionMerge` view became `canvasEdit`), `docs/architecture/c4/README.md`, `.scratch/model-timeline/technical-design.md` (migration numbering, edit semantics) and ticket 08 (migration number 0064, removed routes).

No documentation effect: `docs/architecture/audit.md` (edits use the existing `event.updated` entry, already described as counts without names), `docs/runbooks/mcp-interface.md` (it holds setup and operations only and lists no model tools; the tool list is in `api.md`), `docs/architecture/stack.md`, `.env.example` (no new setting), ADRs (no decision changed: ADR-0049 already says `in_use` is checked against events).

## Blocked by

- 05

## Completion record

- Canvas edits are changes inside the event whose state is shown: `POST/PATCH/DELETE /events/{event}/nodes` and `/connections` (`backend/app/timeline_edit_routes.py`), tidied with `compact` (extended to fold re-routes and type changes and to drop changes that change nothing), validated against the whole chain and every dependent Scenario, answering the `chain_broken` 422 and leaving the event unchanged on refusal; stale handling by the event's `expected_version` (body for create and change, query for delete); a created node answers its element id and gets a position on the line; the audit is `event.updated` with counts only. The old `/nodes` and `/connections` routes, the version changes and merge routes and the MCP tools `get_version_changes` and `merge_version` are removed; MCP `create_node` and `create_connection` take `event_id`. Metamodel deletes check events (payload JSONB for types, replay without the rule for allowed connections) under the Model lock. Migration 0063 drops the `metrics.node_id` foreign key and remaps to element ids; metric node validation uses the line's current state. The interim canvas edits the line's last event.
- All three criteria are met (tests above). Effects are recorded under Documentation effects.
- Deviations: (a) the old version fork route stays but copies no nodes (a fork is a Scenario that shows the base's graph); the old `GET /models/{id}` graph route stays and now returns the replayed graph with `latest_event` (ticket 08 retires it). (b) The old `nodes` and `connections` rows are frozen: types used only by them still block deletes with `in_use` (their foreign keys would otherwise fail with a 500) until ticket 08 drops the tables. (c) A connection re-typed and re-routed in one PATCH is tried in both orders; a pair allowed only together is refused (`connection_not_allowed`). (d) Open for 08/09: removing a node by event leaves `metrics.node_id` dangling (decide whether the metric lists should hide or clear it); `GET /models` costs one timeline replay per Model (ticket 10).

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
