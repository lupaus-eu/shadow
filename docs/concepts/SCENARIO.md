# Scenario Concept

Status: core concept baseline

## Purpose

Scenario tarkoittaa organisaation suunnittelu- tai analyysikontekstia, jossa organisaatiotilat, tapahtumat ja aikasarjat elavat.

Scenario ei tarkoita organisaatiota itseaan eika yksittaista graph-snapshotia.

---

# Owner

Owning Domain:

- Organisation States Domain

Related Domain Document:

- `docs/domains/ORG_STATES.md`

---

# Definition

```text
A Scenario is a versioned planning or analysis context within one Organisation.
```

---

# Key Fields

- scenario_id
- organisation_id
- scenario_key
- name
- description
- protected
- source_scenario_id
- initial_state_id
- version
- created_by
- created_time
- modified_by
- modified_time
- deleted_by
- deleted_time

---

# Invariants

- Scenario must belong to exactly one organisation.
- Scenario must always have `scenario_key`.
- Scenario must always have `name`.
- Active scenario keys are unique within an organisation.
- Normal scenario deletion is soft delete.
- Protected scenarios can be patched for `name` and `description`.
- Protected scenarios cannot be deleted through the backend CRUD API.
- Protected scenarios cannot be cleaned through the backend organisation-state
  cleanup flow.

---

# Lifecycle

States:

- active
- deleted

Transitions:

```text
active -> deleted
```

When a scenario is soft-deleted, owned organisation states, events, graph
nodes, graph edges, timeseries and timeserie values must be soft-deleted by
application or service logic.

The default `Reality` scenario is protected. It can be renamed and redescribed
through normal backend PATCH flow, but it cannot be deleted through normal
backend CRUD flows.

The default `Reality` scenario and other protected scenarios also reject
organisation-state cleanup through normal backend flows.

---

# Relationships

Related Concepts:

- Organisation
- Organisation State

Related Tables:

- scenarios
- org_states
- events
- timeseries
- timeserie_values

Related APIs:

- `GET /api/v1/organisations/{organisation_key}/scenarios`
- `POST /api/v1/organisations/{organisation_key}/scenarios`
- `POST /api/v1/organisations/{organisation_key}/scenarios/copy`
- `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`
- `PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`
- `DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`
- `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/clean`

---

# Domain Rules

- A scenario may reference a source scenario.
- A scenario may reference an initial organisation state.
- Physical database cascades are hard-delete cleanup/safety behavior only.
- Scenario create generates `scenario_key` server-side.
- Scenario responses use stable `scenario_key` as `id`.
- Scenario patch accepts `name` and `description`.
- Scenario patch accepts `name` and `description` for protected scenarios.
- Scenario delete for protected scenarios returns HTTP `409`.
- Organisation-state cleanup for protected scenarios returns HTTP `409`.
- Organisation-state cleanup clears `initial_state_id` when the referenced
  initial organisation state is cleaned.
- Scenario CRUD does not implement copy or branching behavior.
- Scenario copy creates an unprotected scenario with request `description` and
  either request `name` or generated default `Fork of {source scenario name}`.
- Scenario copy sets `source_scenario_id` to the selected source scenario.
- Scenario copy sets `initial_state_id` to the copied version of the selected
  source organisation state.
- Scenario copy copies only the selected active source organisation state.
- Scenario copy delegates copying of graph elements visible at the selected
  source organisation-state target date to Organisation Twin Structure Domain.
- Scenario copy does not copy scenario-owned timeseries or timeserie values.

---

# AI Agent Guidance

When implementing Scenario features:

- read `docs/domains/ORG_STATES.md`
- preserve soft-delete propagation rules
- preserve protected scenario destructive-action guards
- update data and diagram docs when relationships change

Avoid:

- treating physical cascade deletes as the normal deletion path
- adding metamodel copy behavior unless task scope requires it
- copying scenario-owned timeseries unless task scope requires it

---

# Open Questions

- scenario lifecycle states beyond active and deleted
