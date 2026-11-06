# Concept Name

Status: draft

## Purpose

Kuvaa mitä käsite tarkoittaa järjestelmässä.

Kerro myös mitä käsite ei tarkoita, jos se voi sekoittua muihin käsitteisiin.

---

# Owner

Owning Domain:

- Domain Name

Related Domain Document:

- `docs/architecture/domains/<DOMAIN>.md`

---

# Definition

Lyhyt täsmällinen määritelmä.

Example:

```text
A Customer is ...
```

---

# Key Fields

- id
- name
- status
- created_at
- updated_at

---

# Invariants

Invariantit ovat sääntöjä, joiden pitää aina pitää paikkansa.

- Invariant 1
- Invariant 2
- Invariant 3

---

# Lifecycle

States:

- draft
- active
- archived

Transitions:

```text
draft -> active
active -> archived
```

Jos lifecycle on tärkeä, lisää PlantUML state diagram:

```text
docs/architecture/diagrams/state-<concept>-lifecycle.puml
docs/architecture/diagrams/generated/state-<concept>-lifecycle.svg
```

---

# Relationships

Related Concepts:

- Other Concept

Related Tables:

- table_name

Related APIs:

- `/api/path`

---

# Domain Rules

- Rule 1
- Rule 2
- Rule 3

---

# AI Agent Guidance

When implementing this concept:

- read the owning domain document
- preserve invariants
- update data model documentation if fields or relationships change
- update diagrams if lifecycle or relationships change

Avoid:

- changing ownership without updating `docs/architecture/domains/DOMAIN.md`
- adding fields without documenting their meaning
- bypassing lifecycle rules

---

# Open Questions

- question 1
- question 2
