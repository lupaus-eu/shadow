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
- Protected scenarios cannot be patched or deleted through the backend CRUD API.

---

# Lifecycle

States:

- active
- deleted

Transitions:

```text
active -> deleted
```

When a scenario is soft-deleted, owned organisation states, events, graphs, timeseries and timeserie values must be soft-deleted by application or service logic.

The default `Reality` scenario is protected and cannot be patched or deleted
through normal backend CRUD flows.

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
- `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`
- `PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`
- `DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}`

---

# Domain Rules

- A scenario may reference a source scenario.
- A scenario may reference an initial organisation state.
- Physical database cascades are hard-delete cleanup/safety behavior only.
- Scenario create generates `scenario_key` server-side.
- Scenario responses use stable `scenario_key` as `id`.
- Scenario patch accepts `name` and `description`.
- Scenario patch and delete for protected scenarios return HTTP `409`.
- Scenario CRUD does not implement copy or branching behavior.

---

# AI Agent Guidance

When implementing Scenario features:

- read `docs/domains/ORG_STATES.md`
- preserve soft-delete propagation rules
- preserve protected scenario mutation rules
- update data and diagram docs when relationships change

Avoid:

- treating physical cascade deletes as the normal deletion path
- adding metamodel copy behavior unless task scope requires it
- documenting scenario copy or branching behavior unless implemented by the task

---

# Open Questions

- scenario copy and branching behavior
