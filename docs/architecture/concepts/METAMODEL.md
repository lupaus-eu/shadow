# Metamodel Concept

Status: core concept baseline

## Purpose

Metamodel tarkoittaa tyyppimallia, joka maarittaa organisaatiotwinin sallitut solmut, yhteydet, attribuutit ja yhteyssaannot.

Metamodel ei tarkoita yksittaista graph-snapshotia tai organisaatiotilaa.

---

# Owner

Owning Domain:

- Organisation Twin Structure Domain

Related Domain Document:

- `docs/architecture/domains/ORG_TWIN_STRUCTURE.md`

---

# Definition

```text
A Metamodel is the default or organisation-specific type model used to validate and describe organisation twin graph structure.
```

---

# Key Fields

- metamodel_id
- organisation_id
- version
- created_by
- created_time
- modified_by
- modified_time
- deleted_by
- deleted_time

---

# Invariants

- A metamodel is default when `organisation_id IS NULL`.
- Organisation-specific metamodels belong to exactly one organisation.
- There can be one active default metamodel.
- There can be one active organisation-specific metamodel per organisation.
- Metamodel version values are unique within their default or organisation-specific scope.
- A new organisation receives a copy of the active default metamodel.

---

# Lifecycle

States:

- active
- deleted

Transitions:

```text
active -> deleted
```

Versioning is represented by separate metamodel rows with scoped `version` uniqueness.

---

# Relationships

Related Concepts:

- Organisation
- Organisation State

Related Tables:

- metamodels
- node_types
- edge_types
- type_attributes
- allowed_connections
- graph_nodes
- graph_edges

Related APIs:

- TBD

---

# Domain Rules

- Node types and edge types belong to one metamodel.
- Type attributes belong to exactly one node type or exactly one edge type.
- Allowed connections define valid edge/source/target combinations.
- Organisation-specific metamodel creation copies the active default
  metamodel, node types, edge types, type attributes and allowed connections
  from database rows.
- Scenario graph elements should follow the relevant metamodel rules when graph validation is in scope.

---

# AI Agent Guidance

Authorization and audit rules:

- Both authenticated roles may read and use organisation-specific metamodels
  across all organisations; this scope is not a membership rule.
- Organisation metamodel copies and their copied type rows set `created_by` to
  the authenticated actor. Historical default/seed audit values may remain
  null.

When implementing Metamodel features:

- read `docs/architecture/domains/ORG_TWIN_STRUCTURE.md`
- preserve default and organisation-specific uniqueness rules
- preserve type attribute owner constraints
- update diagrams when fields or relationships change

Avoid:

- adding metamodel copy behavior without explicit task scope
- bypassing allowed connection rules when validation is in scope

---

# Open Questions

- organisation-specific metamodel lifecycle
