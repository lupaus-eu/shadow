# Organisation States Domain

Status: core domain baseline

## Purpose

Organisation States Domain hallitsee skenaarioita, organisaatiotilan snapshotteja, tapahtumia ja skenaariokohtaisia aikasarjoja.

Domain kuvaa miten organisaation suunnittelu- tai analyysikonteksti versioidaan ajassa ilman, etta organisaation perustietoja tai graph-rakennetta omistetaan tassa domainissa.

---

# Responsibilities

Owns:

- scenarios
- organisation states
- events
- scenario-owned timeseries
- timeserie values

Provides:

- scenario versioning boundary
- named organisation state snapshots
- event timeline data
- scenario-level timeseries definitions and values

Does NOT Own:

- organisation records
- user records
- metamodel type definitions
- graph nodes or graph edges

---

# Domain Rules

## Scenario Boundary

Every scenario belongs to exactly one organisation.

This relationship is a data-ownership boundary, not a user-membership rule.
Both authenticated roles intentionally access scenarios, states, events and
timeseries in every organisation under the accepted internal-tool trust model.
All unsafe endpoints require the shared exact-Origin and session-CSRF guard.

## Audit Actors

Authenticated creates and copies set `created_by` on every new owned row.
Updates, value replacement, cleanup and other domain mutation actions set
`modified_by`; persistence soft deletion sets both `modified_by` and
`deleted_by`, including propagated child rows. Historical nullable audit values
are not backfilled.

## Service Transaction Boundaries

REST service functions own their transaction and commit once. The
`create_scenario`, `copy_scenario`, `create_org_state`, `create_event`,
`create_timeserie`, `replace_timeserie_values` and `create_derived_metric`
services delegate to `<name>_in_transaction` cores that take an explicit
`actor_user_id`, set the same audit columns, return the ORM entity and flush
but never commit or roll back. The public functions commit, refresh and map the
response. The `create_timeserie` core raises the same `409` when its flush hits
a uniqueness `IntegrityError`; the public function rolls back. Derived-metric
materialisation and recalculation run inside the core's transaction.

Callers that compose several cores, such as AI change-set dry-run and apply
under ADR-015, own the single transaction and its commit or rollback. Cores do
not use SAVEPOINTs.

## Organisation State Naming

Every organisation state has:

- stable `org_state_key`
- human-readable `name`
- `version`

The `name` is the display name for the snapshot and is required.

## Organisation Defaults

When a new organisation is created, the Organisation States Domain creates:

- default scenario `Reality`
- default scenario description `The reality of the organisation`
- protected default scenario flag `True`
- default organisation state `Initial state`
- default organisation state description `Initial state of reality`
- default organisation state target date `2020-01-01`

The default scenario references the created default organisation state as its
`initial_state_id`.

## Soft Delete Propagation

Scenario deletion is a soft delete in normal application flows.

When the application soft-deletes a scenario, it must also soft-delete owned
organisation states, events, graph nodes, graph edges, timeseries and timeserie
values.

Physical database cascades are hard-delete cleanup/safety behavior only.

## Protected Scenarios

Protected scenarios can be patched for `name` and `description` through the
backend CRUD API.

Protected scenarios cannot be deleted through the backend CRUD API and cannot be
cleaned through the backend organisation-state cleanup flow.

The default `Reality` scenario is protected.

## Organisation State Target Dates

Every active organisation state has a `target_date`.

Active organisation states inside the same scenario cannot share the same
`target_date`.

Soft-deleted organisation states do not reserve their historical target dates.

## Event Target Dates

Every active event has a `target_date`.

Events inside the same scenario may share the same `target_date`.

Soft-deleted events are excluded from normal event reads.

## Scenario Copy

Scenario copy creates an editable scenario branch from a selected source
scenario and source organisation state.

Copy rules:

- the source scenario must be active and belong to the requested organisation
- the source organisation state must be active and belong to the source scenario
- the copied scenario receives a generated `scenario_key`
- request `description` becomes the copied scenario description
- request `name` becomes the copied scenario name when provided and non-blank
- missing or blank request `name` defaults to `Fork of {source scenario name}`
- copied scenarios are always `protected=false`
- copied `source_scenario_id` references the selected source scenario
- only the selected active source organisation state is copied
- the copied organisation state receives a generated `org_state_key` value and
  preserves `name`, `description`, `target_date` and `version`
- copied `initial_state_id` points to the copied version of the selected source
  organisation state
- active source events with `target_date` on or before the selected source
  organisation state's `target_date` are copied with their stable keys and
  fields
- every active source timeserie is copied with its stable key and metadata;
  active values are copied only when their date is on or before the selected
  source organisation state's `target_date`
- graph elements visible at the selected source organisation state's target
  date are copied through the Organisation Twin Structure Domain service
  boundary
- source scenario, source organisation states, events, timeseries, values and
  graph history are not mutated

---

# Database Ownership

Tables:

- scenarios
- org_states
- events
- timeseries
- timeserie_values

Owned exclusively by Organisation States Domain.

Other domains may reference these tables but may not modify them directly unless a task explicitly defines a cross-domain service boundary.

---

# API Ownership

The public API is versioned under `/api/v1` and currently nested under
organisations because the frontend uses organisation-scoped routes.

Scenario CRUD endpoints:

```text
GET /api/v1/organisations/{organisation_key}/scenarios
POST /api/v1/organisations/{organisation_key}/scenarios
POST /api/v1/organisations/{organisation_key}/scenarios/copy
GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}
PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}
DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}
```

Organisation state endpoints:

```text
GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states
POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/clean
POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states
GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}
PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}
DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}
```

Event endpoints:

```text
GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events
POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events
GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events/{event_key}
PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events/{event_key}
DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/events/{event_key}
```

Timeserie endpoints:

```text
GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries[?includeValues=false]
POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries
GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}
GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}/exists
PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}/values
PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}/short-name
DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}
POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/derived-metrics
PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/derived-metrics/{timeserie_key}
```

The API uses stable text keys in paths and response `id` fields:

- `organisation_key`
- `scenario_key`
- `org_state_key`
- `event_key`

Scenario responses use:

```json
{
  "id": "reality",
  "name": "Reality",
  "description": "The reality of the organisation",
  "protected": true
}
```

Organisation state responses use:

```json
{
  "id": "initial_state",
  "name": "Initial state",
  "description": "Initial state of reality",
  "targetDate": "2020-01-01"
}
```

Organisation state clean responses use:

```json
{
  "cleaned": 2
}
```

Event responses use:

```json
{
  "id": "event_abc123",
  "name": "Market launch",
  "targetDate": "2030-01-01",
  "eventDetails": "Launch in the northern region"
}
```

Timeserie responses use:

```json
{
  "id": "revenue",
  "name": "Revenue",
  "shortName": "revenue_monthly",
  "description": "Monthly revenue",
  "unit": "EUR",
  "timeUnit": "month",
  "valueUnit": "number",
  "values": [
    { "date": "2030-01-01", "value": 1000 }
  ]
}
```

Timeserie exists responses use:

```json
{
  "id": "revenue",
  "exists": true,
  "shortName": "revenue_monthly"
}
```

Create endpoints return HTTP `201`. Delete endpoints return HTTP `204`.
Missing active organisations, scenarios, organisation states or events return HTTP
`404`.

Protected scenario patch returns HTTP `200` for valid `name` and `description`
updates.

Protected scenario delete and organisation-state cleanup return HTTP `409`.

Duplicate active organisation state target dates inside one scenario return
HTTP `409`.

Scenario copy returns HTTP `201`. Missing active source scenarios or source
organisation states return HTTP `404`.

Organisation state cleanup returns HTTP `200` and soft-deletes all active
organisation states in the selected non-protected scenario. Already
soft-deleted organisation states are not counted. A cleanup call against a
scenario with no active organisation states returns `{ "cleaned": 0 }`.

Event create requires `name` and `targetDate`. Event patch may update `name`,
`targetDate` and `eventDetails`. If `targetDate` is supplied in an event patch,
it cannot be `null`.

Timeserie create requires stable `id`, `name`, `timeUnit` and `valueUnit`.
`shortName` is optional; when supplied it is a trimmed equation-safe ASCII
identifier that starts with a letter and otherwise contains only letters,
numbers and underscores. Timeserie responses return `shortName` as an empty
string when it is absent. Active Timeserie names are unique after trimming and
case-insensitive comparison inside one scenario, and supplied active short
names are unique inside one scenario. Soft-deleted Timeseries do not prevent
reuse of either value.
Supported `timeUnit` values are `day`, `week`, `month` and `year`. Supported
`valueUnit` values are `number`, `string` and `boolean`. Duplicate active
timeserie ids, names or supplied short names inside one scenario return HTTP
`409`. Timeserie delete is a soft delete and also soft-deletes active owned
values. Active graph node links to the deleted timeserie are cleared through
the Organisation Twin Structure Domain service boundary.

Scenario timeseries list returns active timeseries sorted by stable timeserie
id. Timeserie `values` contain active values sorted by `date`; soft-deleted
values are excluded from list and get responses.

The list takes an optional boolean query parameter `includeValues`, default
`true` (TASK-076). With `includeValues=false` it returns the same timeseries
and fields, but reads no values and every `values` list is empty, so an empty
list there does not mean the timeserie has no values. The Structure UI's
Timeserie panel uses it for its link options; the Metrics, Predictions and
Summary views use the default list with values.

Timeserie value replacement uses:

```json
{
  "values": [
    { "date": "2030-01-01", "value": 1000 }
  ]
}
```

The replacement payload becomes the full active value set for that timeserie.
Duplicate submitted dates are accepted with the last submitted value winning.
Active values omitted from the replacement payload are soft-deleted. A
replacement may reactivate a previously soft-deleted value for the same date.

Values must match the timeserie `valueUnit`: `number` requires a finite number,
`string` requires a string and `boolean` requires a boolean. Value dates must be
valid starts for the timeserie `timeUnit`: `day` accepts every date, `week`
starts on Monday, `month` starts on day 1 and `year` starts on January 1.
Invalid value types or invalid time-unit start dates return HTTP `422`.
Derived Metrics are numeric scenario Timeseries whose values are materialized
from one stored formula. Formulas use normal numeric Timeserie short names from
the same scenario and may use `+`, `-`, `*`, `/`, `**` or `^`. Referenced short
names and whole source Timeseries are locked from editing/deletion while the
equation is active; normal source values remain editable and trigger a
transactional recalculation. Derived values are read-only.

Graph element creation and logical deletion use the selected organisation
state's target date through Organisation Twin Structure Domain. Organisation
state target-date edits do not rewrite existing graph lifetime dates. The
frontend Refresh action reloads selected scenario and organisation state data
through existing GET endpoints.

For the MCP read tools (TASK-069H, `docs/domains/AI.md`) the service also
offers `get_timeserie_values_page`, which returns a timeserie with at most a
given number of its values within inclusive dates and the count of values
within them, and `list_scenario_timeseries(include_values=False)`, which reads
no values. `get_timeserie_values_page` has no REST route. Since TASK-076 the
REST timeseries list reaches `include_values=False` through
`includeValues=false`; its default response and the other REST timeserie
responses are unchanged.

---

# Dependencies

Depends On:

- Organisations Domain
- Users Domain for audit references

Referenced By:

- Organisation Twin Structure Domain

---

# Common Workflows

## Create Scenario

Flow:

1. Validate organisation exists and is active.
2. Create scenario.
3. Generate a server-side `scenario_key`.
4. Return scenario data.

Scenario CRUD does not copy source scenario data, graph data or metamodel data.

## Copy Scenario

Flow:

1. Validate organisation exists and is active.
2. Validate source scenario exists, is active and belongs to the organisation.
3. Validate source organisation state exists, is active and belongs to the
   source scenario.
4. Create an unprotected scenario with generated `scenario_key`,
   `source_scenario_id`, request `description` and either request `name` or
   generated default `Fork of {source scenario name}`.
5. Copy only the selected source organisation state.
6. Set the copied scenario `initial_state_id` to the copied selected source
   organisation state.
7. Ask Organisation Twin Structure Domain to copy graph elements visible at the
   selected source target date.
8. Return copied scenario data.

## Create Organisation State

Flow:

1. Validate scenario exists and is active.
2. Validate required `name`.
3. Validate required `target_date`.
4. Validate active `target_date` uniqueness inside the scenario.
5. Generate a server-side `org_state_key`.
6. Create organisation state row.

Organisation state CRUD does not create graph data or synchronise graph dates.

## Create Event

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Validate required `name`.
4. Validate required `target_date`.
5. Generate a server-side `event_key`.
6. Create event row.

Event CRUD does not create graph data, timeseries data or organisation states.

## Create Timeserie

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Validate stable `timeserie_key`, `name`, optional `short_name`, `time_unit`
   and `value_unit`.
4. Validate active scenario-local uniqueness for `timeserie_key`,
   case-insensitive `name` and supplied `short_name`.
5. Create timeserie row.

Timeserie CRUD does not create timeserie values.

## Check Timeserie Existence

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Return whether an active timeserie with the requested stable key exists and,
   when it does, its short name.

Missing timeseries return `{ "exists": false, "shortName": "" }` from the
exists endpoint and HTTP `404` from the get endpoint.

## Clean Organisation States

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Reject protected scenarios.
4. Load active organisation states owned by the scenario.
5. Clear `scenarios.initial_state_id` if it points to one of the cleaned
   organisation states.
6. Soft-delete persistence-active owned graph nodes and edges through
   Organisation Twin Structure Domain.
7. Soft-delete the active organisation states.
8. Return the number of cleaned organisation states as `{ "cleaned": n }`.

Cleanup uses the same soft-delete semantics as other normal application flows.
It does not hard-delete organisation states and does not mutate already
soft-deleted organisation states.

## Patch Scenario

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Update only supplied `name` and `description` fields, including for protected
   scenarios.
4. Update `modified_time`.

## Patch Organisation State

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Validate organisation state exists and is active.
4. Validate supplied `name`.
5. Validate supplied `target_date` is not null when the field is patched.
6. Validate active `target_date` uniqueness inside the scenario.
7. Update only supplied `name`, `description` and `target_date` fields.
8. Update `modified_time`.

## Patch Event

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Validate event exists and is active.
4. Validate supplied `name`.
5. Validate supplied `target_date` is not null when the field is patched.
6. Update only supplied `name`, `event_details` and `target_date` fields.
7. Update `modified_time`.

## Delete Scenario

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Reject protected scenarios.
4. Soft-delete active owned timeseries and timeserie values.
5. Soft-delete active owned events.
6. Soft-delete persistence-active owned graph nodes and edges through
   Organisation Twin Structure Domain.
7. Soft-delete active owned organisation states.
8. Soft-delete the scenario.

## Delete Organisation State

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Validate organisation state exists and is active.
4. Clear `scenarios.initial_state_id` if it points to the deleted organisation state.
5. Soft-delete persistence-active owned graph nodes and edges through
   Organisation Twin Structure Domain.
6. Soft-delete the organisation state.

## Delete Event

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Validate event exists and is active.
4. Soft-delete the event.

## Delete Timeserie

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Validate timeserie exists and is active.
4. Clear active graph node links to the timeserie through Organisation Twin
   Structure Domain.
5. Soft-delete active owned timeserie values.
6. Soft-delete the timeserie.

## Create Organisation Defaults

Flow:

1. Receive an active organisation created by Organisations Domain.
2. Create the protected `Reality` scenario.
3. Create the `Initial state` organisation state for the scenario.
4. Link the scenario `initial_state_id` to the created organisation state.
5. Commit only as part of the outer organisation creation transaction.

---

# AI Agent Guidance

When implementing scenario, organisation state, event or timeseries features:

- read this document before changing scenario, org state, event or timeseries data
- preserve soft-delete behavior
- keep organisation state `name` required
- update data and diagram docs when fields or relationships change

Avoid:

- modifying organisation rows directly
- implementing metamodel copy behavior unless the task explicitly requires it
- treating physical cascade deletes as normal application deletion behavior

---

# Open Questions

- scenario lifecycle states beyond active and soft-deleted
