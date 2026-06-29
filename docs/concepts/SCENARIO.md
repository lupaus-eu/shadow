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

- `/scenarios`

---

# Domain Rules

- A scenario may reference a source scenario.
- A scenario may reference an initial organisation state.
- Physical database cascades are hard-delete cleanup/safety behavior only.

---

# AI Agent Guidance

When implementing Scenario features:

- read `docs/domains/ORG_STATES.md`
- preserve soft-delete propagation rules
- update data and diagram docs when relationships change

Avoid:

- treating physical cascade deletes as the normal deletion path
- adding metamodel copy behavior unless task scope requires it

---

# Open Questions

- protected scenario behavior
- scenario copy and branching behavior
