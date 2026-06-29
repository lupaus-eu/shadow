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
- Normal deletion is soft delete through the owning scenario flow.

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

- `/org-states`

---

# Domain Rules

- `name` is required and is the display name for the snapshot.
- `org_state_key` is the stable scenario-local key.
- A graph may belong to one organisation state through Organisation Twin Structure Domain.

---

# AI Agent Guidance

When implementing Organisation State features:

- read `docs/domains/ORG_STATES.md`
- preserve required `name`
- preserve scenario-local active key uniqueness
- coordinate graph behavior through Organisation Twin Structure Domain

Avoid:

- creating graph data unless the task explicitly includes graph behavior
- modifying organisation rows directly

---

# Open Questions

- default organisation state naming strategy
- snapshot copy behavior
