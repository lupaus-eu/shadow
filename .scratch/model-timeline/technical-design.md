# Technical design: Model timeline

Status: accepted

## Current and target state

- **Current state:** a Model has `model_versions` (the baseline and forks), each holding a complete graph in
  `nodes` and `connections` keyed by `version_id`; `metrics`, `metric_values` and `simulations` also carry
  `version_id`. A change list is computed by comparing a version with its base; merge applies it
  (ADR-0045). Nothing records when a change happens.
- **Target state:** lines (one Base line and any number of Scenarios) hold dated events; the graph is
  computed by replaying a chain of events (ADR-0048); every event write is validated by replaying the
  affected chain (ADR-0049); a Scenario can be adopted fast-forward (ADR-0050). `version_id` becomes
  `line_id` on metrics, metric values and simulations. `nodes`, `connections` and `model_versions` are
  retired.

## Domain

Vocabulary and rules are in `domain-model.md`. The Models domain gains lines, events and changes; the
Metamodel is unchanged. The replay engine is a pure module with no database access so it can be tested
alone.

## Database

Alembic migrations 0060 onward; every table has `organization_id`, row-level security and grants for
`shadow_app` like the existing model tables; `implicit_returning` off where the policy needs it (as
`AuditEvent`).

| Table | Columns | Notes |
| --- | --- | --- |
| `model_lines` | `id`, `organization_id`, `model_id`, `name`, `description`, `kind` (`base` or `scenario`), `parent_line_id`, `branch_event_id`, `start_changed_at`, `created_by_user_account_id`, `version`, `created_at` | partial unique index: one `base` line per model; scenario requires parent and branch event; unique lower(name) per model |
| `timeline_events` | `id`, `organization_id`, `model_id`, `line_id`, `occurred_on` (date), `seq` (bigint identity), `title`, `note`, `version`, `created_by_user_account_id`, `created_at`, `updated_at` | order is (`occurred_on`, `seq`); index (`line_id`, `occurred_on`, `seq`) |
| `event_changes` | `id`, `organization_id`, `event_id`, `position`, `op`, `element_id`, `payload` (JSONB) | unique (`event_id`, `position`); `op` in `add_node`, `remove_node`, `update_node`, `add_connection`, `remove_connection`, `reroute_connection`, `change_connection_type` |
| `node_positions` | `organization_id`, `model_id`, `line_id`, `node_id`, `x`, `y` | primary key (`line_id`, `node_id`) |

- `branch_event_id` references `timeline_events`; deleting such an event is refused by the application
  (ADR-0049) and by a foreign key without cascade.
- Payloads (validated by Pydantic discriminated unions; stored as JSON): `add_node` (`node_type_id`, `name`,
  `description`, `x`, `y`), `remove_node` (none), `update_node` (any of `name`, `description`,
  `node_type_id`), `add_connection` (`connection_type_id`, `source_node_id`, `target_node_id`),
  `remove_connection` (none), `reroute_connection` (`source_node_id` and/or `target_node_id`),
  `change_connection_type` (`connection_type_id`). `element_id` is the node or connection id.
- `metrics`, `metric_values` and `simulations`: 0061 adds a nullable `line_id` (backfilled from `version_id`, indexed, foreign keys to `model_lines`); the version routes still write `version_id`, so ticket 04 makes `line_id` required and drops `version_id`.
- Migration of data (0061): per model, the baseline version becomes the Base line; its graph becomes one
  event "Initial situation" (add changes) dated the Model's creation day, with positions copied into
  `node_positions`; each fork becomes a Scenario branching from that event, with one event holding the
  difference to its base (add, remove, update, re-route), dated the fork's creation day; element ids are
  kept so metrics' `node_id` still match. A fork of a fork branches from its base fork's last event; a fork with no difference gets no event, and a fork of it branches where it does. A line takes the id of its version, and a new Model gets a Base line (with an empty "Initial situation" event) when it is created, in the same request as the baseline version, until ticket 04.
- Ticket 04's migration (0062) sets `line_id` required and drops `version_id`; retirement (0063, in ticket 08): drop `nodes`, `connections`, `model_versions` after the code no longer
  reads them. Downgrade rebuilds them from the present state of each line (the latest state, including
  planned events) so the CI upgrade/downgrade check passes; planned-event dates and history are lost on
  downgrade, which the migration docstring states.
- DBML (`make dbml`) and the C4 model are regenerated in the same tickets.

### Replay engine (`backend/app/timeline/`)

- `state.py`: `State` (nodes and connections by id), `apply(state, change)` raising `ChangeInvalid(cause, element)`
  with causes `missing_element`, `duplicate_element`, `missing_type`, `connection_not_allowed`,
  `missing_endpoint`, `self_connection`, `duplicate_connection`. Pure functions.
- `chain.py`: `chain_events(lines, line, until_event)` yields events in order: ancestors up to their branch
  event, then the line's own events up to `until_event`; `replay(...)` returns a `State` or raises
  `ChainBroken(line, event, change_position, cause, element)`.
- `validate.py`: `validate_model(session, model_id, mutation)` loads all lines, events and changes of the
  model (limits below keep this small), applies the mutation in memory, replays the changed line and every
  descendant line to their last events, checks the dated-order rule for Scenario events and branch
  events, and returns the list of Scenarios whose branch prefix changed (to set `start_changed_at`).
- Tidying (`compact`): within one event, `add_node` followed by `remove_node` of the same element removes both
  and any changes in between on that element; repeated `update_node` of one element merges.
- Planned: `is_planned(event, today)` with `today` from the Organization's time zone (an injected clock in tests).

## API

All under `/api/v1/organizations/{org}/models/{model}`; errors are `{detail: {reason, ...}}`.

- `GET /lines` lists lines (kind, parent, branch event, event count, latest date).
- `POST /lines` creates a Scenario (`name`, `description`, `branch_event_id`); copies the parent's metrics and values.
- `PATCH /lines/{line}` renames (`expected_version`); `DELETE /lines/{line}` (409 `has_children`, 422 base);
  `POST /lines/{line}/acknowledge-start` clears `start_changed_at`.
- `GET /lines/{line}/events` lists events (id, date, title, note, planned flag, change counts, whether another
  line branches from it).
- `POST /lines/{line}/events` (`occurred_on`, `title`, `note`, `changes[]`); `GET`, `PATCH`, `DELETE
  /events/{event}` (`expected_version`; `PATCH` may replace `changes`). 422 `chain_broken` with `event`, `position`,
  `element`, `cause`, `hint`; 409 for a stale version or when the event is a branch point (`reason: "branch_point"`,
  with the Scenario name).
- `GET /lines/{line}/state?event_id=` or `?as_of=YYYY-MM-DD`; default is the present state. Returns the graph in
  today's shape (`nodes`, `connections`, `node_types`, `connection_types`, `allowed_connections`) plus `line`,
  `event`, `planned`, `positions`, and for the shown event `added`, `updated` and `removed` element lists (removed
  ones with their data) so the canvas can mark what it changed.
- `POST /events/{event}/nodes`, `PATCH /events/{event}/nodes/{id}`, `DELETE ...`, and the same for
  `/connections`: canvas edits as changes inside the event, validated and compacted. They replace today's
  `/nodes` and `/connections` routes.
- `PUT /lines/{line}/positions` (`[{node_id, x, y}]`): writes positions only, no event, no audit.
- `POST /lines/{line}/adopt` (Scenario into parent; ADR-0050).
- Metric, simulation and analysis routes take `line_id` in place of `version_id`.
- Audit actions: `line.created`, `line.renamed`, `line.deleted`, `line.adopted`, `event.created`, `event.updated`,
  `event.deleted`. Summaries carry model, line, event, date, op counts; never element names or note text.

### MCP tools

Reads `list_lines`, `list_events`, `get_state`; writes `create_scenario`, `add_event`, `update_event`,
`delete_event`, `adopt_scenario`. `create_node` and `create_connection` take `event_id`; the metric, simulation and
analysis tools take `line_id`. `create_version`, `merge_version` and `get_version_changes` are removed. Tools
call the same endpoint functions (ADR-0046).

## Frontend

- `ModelShell`: the version select and fork/merge/delete buttons become a line picker (Base line first, Scenarios
  by branch), "New scenario from here", rename/delete/adopt, and the event list panel (see the Structure canvas
  design for the canvas side). Planned events use a colour and a "Planned" label; the "Now" divider sits between
  the last happened and the first planned event.
- The event editor: title, date, note, ordered changes with the element names resolved for reading; refusal
  messages built from `chain_broken` causes in Finnish and English; the form keeps input on failure.
- The scenario notice ("its start changed") from `start_changed_at`, with an acknowledge button.
- All other tabs (Types, Metrics, Simulations, Analysis) follow the selected line; the Types tab is shared by
  all lines and says so.

### Interim state

Between tickets 04 and 09 the backend moves ahead of the web UI. Tickets 04 and 07 update the frontend client minimally so
that the existing Structure, Metrics, Simulations and Analysis tabs keep working on the Base line; Scenarios and events
appear in the UI only with ticket 09. The product is not released during this time (the product owner tests locally).

## Authentication and authorization

Per `domain-model.md`: Owners and Admins write the Base line; Members write Scenarios; reading needs membership;
a read-only Organization cannot write; Scenario rename and delete: creator, Owner or Admin. Agents use the person's
rights. Support Access still opens no model route.

## Testing

- Backend unit: replay engine (each change and cause), compaction, ordering by date then entry order, planned
  computation with a fixed clock, a generated-sequences test (random valid events replay to a model equal to
  a straightforward reference).
- Backend API (PostgreSQL): lines, events, state by event and by date, every refusal cause and message fields, branch
  point protection, delete with children, concurrent stale writes (409), the model lock, roles and read-only
  Organization, audit entries without names, row-level security across Organizations (as `test_models_graph.py`).
- Migration: upgrade of a database with versions, graphs, metrics and simulations to lines; element ids, positions
  and metric values preserved; downgrade works; CI upgrade/downgrade passes.
- MCP: each tool with roles and the call log; `test_no_llm_calls.py` still passes.
- Frontend unit: refusal message builder, event list grouping and Planned/Now marks. Browser: create a Scenario
  from a past event, plan an event, break and fix a chain.
- Performance: a script builds a model with 2000 events and 500 nodes and records the time of `state`, `events` and
  a write on the development stack; the numbers go into this document.

Select checks using [`docs/agents/testing.md`](../../docs/agents/testing.md).

## Configuration

New: `LIMIT_EVENTS_PER_LINE` (default 5000) and `LIMIT_LINES_PER_MODEL` (default 200), in `.env.example` and
`.env.production.example`. Refused writes beyond a limit give 409 `limit_reached`.

## Architecture effects

No new service or port. The backend gains the `timeline` package; the C4 model gets the new components; the DBML gets
the new tables in the models group. The worker is not involved (planned events are computed on read).

## Documentation effects

- [ ] Update `docs/user/` and `docs/admin/` (ticket 11)
- [ ] Update `docs/operations/` (limits; ticket 05) and `docs/runbooks/mcp-interface.md` (ticket 08)
- [ ] Update `docs/gdpr/` (audit carries no names; evaluated in ticket 05)
- [ ] Update `docs/architecture/` (database, api, audit, stack, C4, DBML; per ticket)
- [ ] Update `docs/design/` (ticket 09)
- [ ] Accept ADR-0048, ADR-0049 and ADR-0050 and supersede ADR-0045 (ticket 08)
- [ ] Update `CONTEXT.md` (ticket 11)
- [ ] Update `.env.example` and `.env.production.example` (ticket 05)

## Options and decision

1. **Event replay with validation on write** (chosen): history is the data; any state is derived; corrections are possible
   while the chain stays valid. Cost: replay on every write and read.
2. A full graph snapshot per event: reads are trivial, but every event copies the graph, a correction must rewrite all
   later snapshots, and validity is implicit. Rejected.
3. Valid-from/valid-to dates on elements (temporal columns): fits one linear history, but branching Scenarios and
   re-routing do not fit, and "state after event E" is awkward. Rejected.
4. Keep versions and add dates to them: does not give branching from a past state or an editable history. Rejected.
5. Cache states: not in the first version; added only if the performance criterion fails.
