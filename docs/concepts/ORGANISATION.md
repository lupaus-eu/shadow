# Organisation Concept

Status: core concept baseline

## Purpose

Organisation tarkoittaa Schattenissa tenant-like rajaa, jonka sisalla skenaariot, organisaatiotilat ja organisaatiokohtaiset metamodelit sijaitsevat.

Organisation ei tarkoita kayttajaa, asiakasta, skenaariota tai graph-snapshotia.

---

# Owner

Owning Domain:

- Organisations Domain

Related Domain Document:

- `docs/domains/ORGANISATIONS.md`

---

# Definition

```text
An Organisation is the stable application boundary for scenario data and organisation-specific metamodel data.
```

---

# Key Fields

- organisation_id
- organisation_key
- name
- created_by
- created_time
- modified_by
- modified_time
- deleted_by
- deleted_time

---

# Invariants

- Organisation must always have `organisation_id`.
- Organisation must always have `organisation_key`.
- Organisation must always have `name`.
- Active `organisation_key` values are unique.
- Active `name` values are unique case-insensitively.
- Soft-deleted organisation names may be reused.

---

# Lifecycle

States:

- active
- deleted

Transitions:

```text
active -> deleted
```

Deletion is soft delete using `deleted_time`.

---

# Relationships

Related Concepts:

- Scenario
- Metamodel

Related Tables:

- organisations
- scenarios
- metamodels

Related APIs:

- `/organisations`

---

# Domain Rules

- Use `organisation_key` as stable external/import identity.
- Exclude soft-deleted organisations from normal reads.
- Enforce active case-insensitive name uniqueness at the database level.

---

# AI Agent Guidance

When implementing Organisation features:

- read `docs/domains/ORGANISATIONS.md`
- preserve active case-insensitive name uniqueness
- preserve soft-delete behavior
- do not expose bigint primary keys as stable external identifiers unless a task explicitly requires it

Avoid:

- changing membership or authorization behavior without a dedicated task
- modifying scenario or graph lifecycle rules from Organisation code

---

# Open Questions

- membership model
- authorization model
- organisation deletion rules when active dependent data exists
