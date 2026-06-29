# Organisation Twin Structure Domain

Status: core domain baseline

## Purpose

Organisation Twin Structure Domain hallitsee metamodelit ja organisaatiotilan graph-rakenteen.

Metamodel maarittaa sallitut node- ja edge-tyypit. Graph kuvaa yhden organisaatiotilan snapshotin solmut ja yhteydet.

---

# Responsibilities

Owns:

- metamodels
- node types
- edge types
- type attributes
- allowed connections
- graphs
- graph nodes
- graph edges

Provides:

- default metamodel
- organisation-specific metamodels
- graph snapshot structure for organisation states
- graph node and edge attribute storage

Does NOT Own:

- organisation records
- scenario lifecycle
- organisation state lifecycle
- timeseries definitions or values

---

# Domain Rules

## Metamodel Scope

A metamodel is default when `organisation_id IS NULL`.

An organisation-specific metamodel belongs to exactly one organisation.

There can be one active default metamodel and one active organisation-specific metamodel per organisation.

## Type Ownership

Metamodels own node types, edge types, type attributes and allowed connections.

Type attributes must belong to exactly one node type or exactly one edge type.

## Graph Scope

A graph belongs to exactly one organisation state.

Only one active graph may exist for an organisation state.

Graph nodes and graph edges belong to a graph snapshot.

---

# Database Ownership

Tables:

- metamodels
- node_types
- edge_types
- type_attributes
- allowed_connections
- graphs
- graph_nodes
- graph_edges

Owned exclusively by Organisation Twin Structure Domain.

Other domains may reference these tables but may not modify them directly unless a task explicitly defines a service boundary.

---

# API Ownership

Endpoints:

```text
TBD
```

Exact HTTP operations and versioned paths are defined in backend implementation tasks.

---

# Dependencies

Depends On:

- Organisations Domain
- Organisation States Domain
- Users Domain for audit references

Referenced By:

- None currently

---

# Common Workflows

## Use Default Metamodel

Flow:

1. Load active default metamodel.
2. Read node types, edge types, attributes and allowed connections.
3. Apply structure rules when graph data is created or validated.

## Create Graph Snapshot

Flow:

1. Validate organisation state exists and is active.
2. Validate relevant metamodel rules.
3. Create one active graph for the organisation state.
4. Create graph nodes and graph edges.

---

# AI Agent Guidance

When implementing organisation twin structure features:

- read this document before changing metamodel, type or graph data
- preserve one-active-graph-per-org-state behavior
- preserve one-active-default-metamodel behavior
- keep dynamic graph attributes in JSONB unless an ADR changes the data strategy

Avoid:

- modifying organisation or scenario rows directly
- adding metamodel copy behavior without explicit task scope
- bypassing allowed connection rules when graph validation is in scope

---

# Open Questions

- metamodel copy and versioning workflow
- graph validation API boundaries
