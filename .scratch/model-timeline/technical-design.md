# Technical design: Model timeline

Status: accepted

## Current and target state

- **Current state:** a Model has `model_versions` (the baseline and forks), each holding a complete graph in
  `nodes` and `connections` keyed by `version_id`; `metrics`, `metric_values` and `simulations` also carry
  `version_id`. A change list is computed by comparing a version with its base; merge applies it
  (ADR-0045). Nothing records when a change happens.
- **Target state:** lines (one Base line and any number of Scenarios) hold dated changes; the graph is
  computed by replaying a chain of changes (ADR-0048); every change write is validated by replaying the
  affected chain (ADR-0049); a Scenario can be adopted fast-forward (ADR-0050). `version_id` becomes
  `line_id` on metrics, metric values and simulations. `nodes`, `connections` and `model_versions` are
  retired.

## Domain

Vocabulary and rules are in `domain-model.md`. The Models domain gains lines, Changes and Edits; the
Metamodel is unchanged. The replay engine is a pure module with no database access so it can be tested
alone.

## Database

Alembic migrations 0060 onward; every table has `organization_id`, row-level security and grants for
`shadow_app` like the existing model tables; `implicit_returning` off where the policy needs it (as
`AuditEvent`).

| Table | Columns | Notes |
| --- | --- | --- |
| `model_lines` | `id`, `organization_id`, `model_id`, `name`, `description`, `kind` (`base` or `scenario`), `parent_line_id`, `branch_change_id`, `start_changed_at`, `created_by_user_account_id`, `version`, `created_at` | partial unique index: one `base` line per model; scenario requires parent and branch change; unique lower(name) per model |
| `timeline_changes` | `id`, `organization_id`, `model_id`, `line_id`, `occurred_on` (date), `seq` (bigint identity), `title`, `note`, `version`, `created_by_user_account_id`, `created_at`, `updated_at` | order is (`occurred_on`, `seq`); index (`line_id`, `occurred_on`, `seq`) |
| `change_edits` | `id`, `organization_id`, `change_id`, `position`, `op`, `element_id`, `payload` (JSONB) | unique (`change_id`, `position`); `op` in `add_node`, `remove_node`, `update_node`, `add_connection`, `remove_connection`, `reroute_connection`, `change_connection_type` |
| `node_positions` | `organization_id`, `model_id`, `line_id`, `node_id`, `x`, `y` | primary key (`line_id`, `node_id`) |

- `branch_change_id` references `timeline_changes`; deleting such a change is refused by the application
  (ADR-0049) and by a foreign key without cascade.
- Payloads (validated by Pydantic discriminated unions; stored as JSON): `add_node` (`node_type_id`, `name`,
  `description`, `x`, `y`), `remove_node` (none), `update_node` (any of `name`, `description`,
  `node_type_id`), `add_connection` (`connection_type_id`, `source_node_id`, `target_node_id`),
  `remove_connection` (none), `reroute_connection` (`source_node_id` and/or `target_node_id`),
  `change_connection_type` (`connection_type_id`). `element_id` is the node or connection id.
- `metrics`, `metric_values` and `simulations`: 0061 adds a nullable `line_id` (backfilled from `version_id`, indexed, foreign keys to `model_lines`); the version routes still write `version_id`, so ticket 04 makes `line_id` required and drops `version_id`.
- Migration of data (0061): per model, the baseline version becomes the Base line; its graph becomes one
  change "Initial situation" (add edits) dated the Model's creation day, with positions copied into
  `node_positions`; each fork becomes a Scenario branching from that change, with one Change holding the
  difference to its base (add, remove, update, re-route), dated the fork's creation day; element ids are
  kept so metrics' `node_id` still match. A fork of a fork branches from its base fork's last change; a fork with no difference gets no change, and a fork of it branches where it does. A line takes the id of its version, and a new Model gets a Base line (with an empty "Initial situation" change) when it is created, in the same request as the baseline version, until ticket 04.
- Ticket 04's migration (0062) sets `line_id` required and drops `version_id`; ticket 07's migration (0063) drops the foreign key `metrics.node_id` → `nodes.id` and remaps the column to element ids (the 0061 rules); retirement (0064, ticket 08) drops `nodes`, `connections` and `model_versions` (no other table references them; their
  `version_id` and `origin_node_id` columns go with them). Downgrade recreates the three tables with their old structure and
  policies and refills `model_versions` from the lines (one version per line, same id, so the older migrations keep every
  metric and simulation), but leaves `nodes` and `connections` empty: the timeline is the source, so no graph is rebuilt, and
  planned-change dates and history are not in the old tables. (The first draft rebuilt the graphs from the latest state; an
  empty graph is enough for the CI upgrade/downgrade check and the migration tests that need the old tables write them directly.)
- DBML (`make dbml`) and the C4 model are regenerated in the same tickets.

### Replay engine (`backend/app/timeline/`)

- `state.py`: `State` (nodes and connections by id), `apply_edit(state, edit)` raising `EditInvalid(cause, element)`
  with causes `missing_element`, `duplicate_element`, `missing_type`, `connection_not_allowed`,
  `missing_endpoint`, `self_connection`, `duplicate_connection`. Pure functions.
- `chain.py`: `chain_changes(lines, line, until_change)` yields Changes in order: ancestors up to their branch
  change, then the line's own changes up to `until_change`; `replay(...)` returns a `State` or raises
  `ChainBroken(line, change, edit_position, cause, element)`.
- `validate.py`: `validate_model(session, model_id, mutation)` loads all lines, Changes and Edits of the
  model (limits below keep this small), applies the mutation in memory, replays the changed line and every
  descendant line to their last changes, checks the dated-order rule for Scenario changes and branch
  changes, and returns the list of Scenarios whose branch prefix changed (to set `start_changed_at`).
- Tidying (`compact`): within one change, `add_node` followed by `remove_node` of the same element removes both
  and any edits in between on that element; repeated `update_node` of one element merges.
- Planned: `is_planned(change, today)` with `today` from the Organization's time zone (an injected clock in tests).

## API

All under `/api/v1/organizations/{org}/models/{model}`; errors are `{detail: {reason, ...}}`.

- `GET /lines` lists lines (kind, parent, branch change, change count, latest date).
- `POST /lines` creates a Scenario (`name`, `description`, `branch_change_id`); copies the parent's metrics and values.
- `PATCH /lines/{line}` renames (`expected_version`); `DELETE /lines/{line}` (409 `has_children`, 422 base);
  `POST /lines/{line}/acknowledge-start` clears `start_changed_at`.
- `GET /lines/{line}/changes` lists changes (id, date, title, note, planned flag, edit counts, whether another
  line branches from it).
- `POST /lines/{line}/changes` (`occurred_on`, `title`, `note`, `edits[]`); `GET`, `PATCH`, `DELETE
  /changes/{change}` (`expected_version`; `PATCH` may replace `edits`). 422 `chain_broken` with `change`, `position`,
  `element`, `cause`, `hint`; 409 for a stale version or when the change is a branch point (`reason: "branch_point"`,
  with the Scenario name).
- `GET /lines/{line}/state?change_id=` or `?as_of=YYYY-MM-DD`; default is the present state. Returns the graph in
  today's shape (`nodes`, `connections`, `node_types`, `connection_types`, `allowed_connections`) plus `line`,
  `change`, `planned`, `positions`, and for the shown change `added`, `updated` and `removed` element lists (removed
  ones with their data) so the canvas can mark what it changed.
- `POST /changes/{change}/nodes`, `PATCH /changes/{change}/nodes/{id}`, `DELETE ...`, and the same for
  `/connections`: canvas edits as edits inside the change, validated and compacted (`expected_version` of the change in
  the body, or the query for a delete; a create may omit it). They replace today's `/nodes` and `/connections` routes.
  Compaction also folds re-routes and type changes of a connection into its add or an earlier edit, and drops an edit
  that leaves the state as it was. A connection re-typed and re-routed together is tried in both orders and refused if
  only the pair is allowed.
- `PUT /lines/{line}/positions` (`[{node_id, x, y}]`): writes positions only, no change, no audit.
- `POST /lines/{line}/adopt` (Scenario into parent; ADR-0050): optional `expected_version`; refusals are structured
  (409 `parent_moved_on` with the later changes and a `create_scenario` suggestion, 422 `dates_precede`, 422
  `nothing_to_adopt`, 422 `chain_broken`). The Scenario's changes are created again in the parent (new ids and entry
  numbers), positions drawn for its added nodes are copied to the parent, metrics are not adopted. A Scenario without
  children is deleted; one with children stays without changes at the last adopted change, and its children are
  re-attached to the parent line at the adopted copies of the changes they branched from (their states do not change).
- `GET /models/{id}` stays: the model, `line` and `lines`, the metamodel and the graph after a line's last change
  (`?line_id=`, Base line by default); the `version_id` parameter and the version list are gone.
- Metric, simulation and analysis routes take `line_id` in place of `version_id`.
- Audit actions: `line.created`, `line.renamed`, `line.deleted`, `line.adopted`, `change.created`, `change.updated`,
  `change.deleted`. Summaries carry model, line, change, date, op counts; never element names or note text.

### MCP tools

Reads `list_lines`, `list_changes`, `get_state` (and `get_model` with `line_id`, `list_models` with `base_line_id`); writes `create_scenario`, `add_change`, `update_change`,
`delete_change`, `adopt_scenario`. `create_node` and `create_connection` take `change_id`; the metric, simulation and
analysis tools take `line_id`. `create_version`, `merge_version` and `get_version_changes` are removed. Tools
call the same endpoint functions (ADR-0046).

## Frontend

- `ModelShell`: the version select and fork/merge/delete buttons become a line picker (Base line first, Scenarios
  by branch), "New scenario from here", rename/delete/adopt, and the change list panel (see the Structure canvas
  design for the canvas side). Planned changes use a colour and a "Planned" label; the "Now" divider sits between
  the last happened and the first planned change.
- The change editor: title, date, note, ordered edits with the element names resolved for reading; refusal
  messages built from `chain_broken` causes in Finnish and English; the form keeps input on failure.
- The scenario notice ("its start changed") from `start_changed_at`, with an acknowledge button.
- All other tabs (Types, Metrics, Simulations, Analysis) follow the selected line; the Types tab is shared by
  all lines and says so.

### Interim state

Between tickets 04 and 09 the backend moves ahead of the web UI. Tickets 04 and 07 update the frontend client minimally so
that the existing Structure, Metrics, Simulations and Analysis tabs keep working on the Base line; Scenarios and changes
appear in the UI only with ticket 09. The product is not released during this time (the product owner tests locally).

## Authentication and authorization

Per `domain-model.md`: Owners and Admins write the Base line; Members write Scenarios; reading needs membership;
a read-only Organization cannot write; Scenario rename and delete: creator, Owner or Admin. Agents use the person's
rights. Support Access still opens no model route.

## Testing

- Backend unit: replay engine (each change and cause), compaction, ordering by date then entry order, planned
  computation with a fixed clock, a generated-sequences test (random valid changes replay to a model equal to
  a straightforward reference).
- Backend API (PostgreSQL): lines, changes, state by change and by date, every refusal cause and message fields, branch
  point protection, delete with children, concurrent stale writes (409), the model lock, roles and read-only
  Organization, audit entries without names, row-level security across Organizations (as `test_models_graph.py`).
- Migration: upgrade of a database with versions, graphs, metrics and simulations to lines; element ids, positions
  and metric values preserved; downgrade works; CI upgrade/downgrade passes.
- MCP: each tool with roles and the call log; `test_no_llm_calls.py` still passes.
- Frontend unit: refusal message builder, change list grouping and Planned/Now marks. Browser: create a Scenario
  from a past change, plan a change, break and fix a chain.
- Performance: `backend/tests/test_timeline_performance.py` (marker `perf`, excluded from the normal run by
  `addopts = -m "not perf"`; run it with `pytest -m perf -s`) builds a model with 2000 changes and 500 nodes directly
  in the database and times the HTTP routes with the FastAPI TestClient against the PostgreSQL test database.

### Performance (ticket 10)

Model: 2000 changes on the Base line (560 adds with 217 connections, then renames, re-routes and 60 removals, leaving
500 nodes), plus five Scenarios (three and a late one branching from the Base line, one branching from another
Scenario; 20 to 30 changes each). Three runs each, worst value compared with the limit. Machine: Apple M4, 10 cores,
16 GB, PostgreSQL 16 in Docker (compose service `db`, port 55432), TestClient in the same process (no network).

| Measurement | Runs (s) | Limit (s) | Result |
| --- | --- | --- | --- |
| `GET .../lines/{line}/state` (500 nodes, 217 connections) | 0.212, 0.174, 0.205 | 2 | met |
| `GET .../lines/{line}/changes` (2000 changes) | 0.218, 0.213, 0.220 | 2 | met |
| `PATCH` of a change at position ~1000 with four Scenarios branching from it (validated write) | 0.359, 0.357, 0.388 | 5 | met |

No caching or snapshots were added. The canvas (diagram-js) is not performance-gated by the product owner; these are
backend timings only.

Select checks using [`docs/agents/testing.md`](../../docs/agents/testing.md).

## Configuration

New: `LIMIT_CHANGES_PER_LINE` (default 5000) and `LIMIT_LINES_PER_MODEL` (default 200), in `.env.example` and
`.env.production.example`. Refused writes beyond a limit give 409 `limit_reached`.

## Architecture effects

No new service or port. The backend gains the `timeline` package; the C4 model gets the new components; the DBML gets
the new tables in the models group. The worker is not involved (planned changes are computed on read).

## Documentation effects

- [ ] Update `docs/user/` and `docs/admin/` (ticket 11)
- [ ] Update `docs/operations/` (limits; ticket 05) and [x] `docs/runbooks/mcp-interface.md` (ticket 08)
- [ ] Update `docs/gdpr/` (audit carries no names; evaluated in ticket 05)
- [ ] Update `docs/architecture/` (database, api, audit, stack, C4, DBML; per ticket)
- [ ] Update `docs/design/` (ticket 09)
- [x] Accept ADR-0048, ADR-0049 and ADR-0050 and supersede ADR-0045 (ticket 08)
- [ ] Update `CONTEXT.md` (ticket 11)
- [ ] Update `.env.example` and `.env.production.example` (ticket 05)

## Options and decision

1. **Change replay with validation on write** (chosen): history is the data; any state is derived; corrections are possible
   while the chain stays valid. Cost: replay on every write and read.
2. A full graph snapshot per change: reads are trivial, but every change copies the graph, a correction must rewrite all
   later snapshots, and validity is implicit. Rejected.
3. Valid-from/valid-to dates on elements (temporal columns): fits one linear history, but branching Scenarios and
   re-routing do not fit, and "state after change E" is awkward. Rejected.
4. Keep versions and add dates to them: does not give branching from a past state or an editable history. Rejected.
5. Cache states: not in the first version; added only if the performance criterion fails.
