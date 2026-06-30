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

When the application soft-deletes a scenario, it must also soft-delete owned organisation states, events, graphs, timeseries and timeserie values.

Physical database cascades are hard-delete cleanup/safety behavior only.

## Protected Scenarios

Protected scenarios cannot be patched or deleted through the backend CRUD API.

The default `Reality` scenario is protected.

## Organisation State Target Dates

Every active organisation state has a `target_date`.

Active organisation states inside the same scenario cannot share the same
`target_date`.

Soft-deleted organisation states do not reserve their historical target dates.

## Scenario Copy

Scenario copy creates an editable scenario branch from a selected source
scenario and source organisation state.

Copy rules:

- the source scenario must be active and belong to the requested organisation
- the source organisation state must be active and belong to the source scenario
- the copied scenario receives a generated `scenario_key`
- request `name` and `description` become the copied scenario fields
- copied scenarios are always `protected=false`
- copied `source_scenario_id` references the selected source scenario
- all active source organisation states that belong to the source scenario and
  have `target_date <= sourceOrgStateId.target_date` are copied
- copied organisation states receive generated `org_state_key` values and
  preserve `name`, `description`, `target_date` and `version`
- copied `initial_state_id` points to the copied version of the selected source
  organisation state
- active graph snapshots for copied organisation states are copied through the
  Organisation Twin Structure Domain service boundary
- scenario-owned timeseries and timeserie values are not copied
- source scenario, source organisation states and source graphs are not mutated

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

Organisation state CRUD endpoints:

```text
GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states
POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states
GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}
PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}
DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}
```

The API uses stable text keys in paths and response `id` fields:

- `organisation_key`
- `scenario_key`
- `org_state_key`

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

Create endpoints return HTTP `201`. Delete endpoints return HTTP `204`.
Missing active organisations, scenarios or organisation states return HTTP
`404`.

Protected scenario patch and delete return HTTP `409`.

Duplicate active organisation state target dates inside one scenario return
HTTP `409`.

Scenario copy returns HTTP `201`. Missing active source scenarios or source
organisation states return HTTP `404`.

Organisation state graph-date synchronisation is not implemented. The frontend
Refresh action reloads selected scenario and organisation state data through
existing GET endpoints.

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
4. Create an unprotected scenario with generated `scenario_key`, request fields
   and `source_scenario_id`.
5. Copy active source organisation states in the source scenario whose
   `target_date` is less than or equal to the selected source organisation
   state's `target_date`.
6. Set the copied scenario `initial_state_id` to the copied selected source
   organisation state.
7. Ask Organisation Twin Structure Domain to copy active graph snapshots for the
   copied organisation state pairs.
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

## Patch Scenario

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Reject protected scenarios.
4. Update only supplied `name` and `description` fields.
5. Update `modified_time`.

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

## Delete Scenario

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Reject protected scenarios.
4. Soft-delete active owned timeseries and timeserie values.
5. Soft-delete active owned events.
6. Soft-delete active owned graphs through Organisation Twin Structure Domain.
7. Soft-delete active owned organisation states.
8. Soft-delete the scenario.

## Delete Organisation State

Flow:

1. Validate organisation exists and is active.
2. Validate scenario exists and is active.
3. Validate organisation state exists and is active.
4. Clear `scenarios.initial_state_id` if it points to the deleted organisation state.
5. Soft-delete active owned graphs through Organisation Twin Structure Domain.
6. Soft-delete the organisation state.

## Create Organisation Defaults

Flow:

1. Receive an active organisation created by Organisations Domain.
2. Create the protected `Reality` scenario.
3. Create the `Initial state` organisation state for the scenario.
4. Link the scenario `initial_state_id` to the created organisation state.
5. Commit only as part of the outer organisation creation transaction.

---

# AI Agent Guidance

When implementing scenario or organisation state features:

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
