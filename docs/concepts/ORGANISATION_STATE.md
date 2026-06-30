# Organisation State Concept

Status: core concept baseline

## Purpose

Organisation State tarkoittaa skenaariokohtaista nimettya snapshotia organisaatiosta tiettya tavoitepaivaa tai versiota varten.

Organisation State ei tarkoita organisaation master-dataa eika metamodelia.

---

# Owner

Owning Domain:

- Organisation States Domain

Related Domain Document:

- `docs/domains/ORG_STATES.md`

---

# Definition

```text
An Organisation State is a named scenario-specific snapshot state of an Organisation.
```

---

# Key Fields

- org_state_id
- scenario_id
- org_state_key
- name
- version
- description
- target_date
- created_by
- created_time
- modified_by
- modified_time
- deleted_by
- deleted_time

---

# Invariants

- Organisation State must belong to exactly one scenario.
- Organisation State must always have `org_state_key`.
- Organisation State must always have `name`.
- Active organisation state keys are unique within a scenario.
- Active non-null `target_date` values are unique within a scenario at the API level.
- Normal deletion is soft delete through the owning scenario flow.
- A new organisation receives a default organisation state named `Initial state`.

---

# Lifecycle

States:

- active
- deleted

Transitions:

```text
active -> deleted
```

Organisation states are normally soft-deleted when their owning scenario is soft-deleted.

Organisation states can also be soft-deleted through the backend CRUD API.
When the deleted organisation state is the scenario initial state, the parent
scenario's `initial_state_id` is cleared.

---

# Relationships

Related Concepts:

- Scenario
- Organisation

Related Tables:

- org_states
- scenarios
- graphs

Related APIs:

- `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states`
- `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states`
- `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}`
- `PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}`
- `DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}`

---

# Domain Rules

- `name` is required and is the display name for the snapshot.
- `org_state_key` is the stable scenario-local key.
- Organisation state create generates `org_state_key` server-side.
- Organisation state responses use stable `org_state_key` as `id`.
- Organisation state patch accepts `name`, `description` and `targetDate`.
- Duplicate active non-null `targetDate` values inside one scenario return HTTP
  `409`.
- Soft-deleted organisation states do not reserve historical `targetDate`
  values.
- The default organisation state uses description `Initial state of reality`
  and target date `2020-01-01`.
- A graph may belong to one organisation state through Organisation Twin Structure Domain.
- Organisation state CRUD does not create graph data or synchronise graph dates.

---

# AI Agent Guidance

When implementing Organisation State features:

- read `docs/domains/ORG_STATES.md`
- preserve required `name`
- preserve scenario-local active key uniqueness
- preserve scenario-local active non-null target-date uniqueness
- coordinate graph behavior through Organisation Twin Structure Domain

Avoid:

- creating graph data unless the task explicitly includes graph behavior
- modifying organisation rows directly
- documenting graph-date synchronisation unless implemented by the task

---

# Open Questions

- snapshot copy behavior
