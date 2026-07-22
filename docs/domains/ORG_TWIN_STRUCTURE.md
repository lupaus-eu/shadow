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

When a new organisation is created, the active default metamodel is copied into
an organisation-specific metamodel. The copy preserves stable type keys and
copies the metamodel row, node types, edge types, type attributes and allowed
connections from database rows, not from the JSON seed file at runtime.

## Type Ownership

Metamodels own node types, edge types, type attributes and allowed connections.

Type attributes must belong to exactly one node type or exactly one edge type.

## Graph Scope

A graph belongs to exactly one organisation state.

Only one active graph may exist for an organisation state.

Graph nodes and graph edges belong to a graph snapshot.

## Graph Snapshot Copy

When Organisation States Domain copies a scenario, Organisation Twin Structure
Domain provides the service boundary for copying active graph snapshots from
source organisation states to their copied organisation states.

Graph snapshot copy preserves graph names, descriptions, node and edge stable
keys, type references, create dates, positions and dynamic attributes. Graph
node timeseries references are cleared because scenario-owned timeseries are not
copied by scenario copy.

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
GET    /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph
GET    /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/types
POST   /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/nodes
PATCH  /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/nodes/{node_key}
DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/nodes/{node_key}
POST   /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/edges
PATCH  /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/edges/{edge_key}
DELETE /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/edges/{edge_key}
PATCH  /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/positions
```

Backend implementation:

- `backend/app/api/v1/org_twin_structure/router.py`
- `backend/app/api/v1/org_twin_structure/schemas.py`
- `backend/app/api/v1/org_twin_structure/org_twin_structure_service.py`

Frontend API client:

- `frontend/src/api/orgTwinStructure.ts`

Graph node responses expose stable primary and secondary timeserie keys as
`timeserieId` and `timeserieSecondaryId`. Graph node patch requests may update
these links by stable scenario-owned timeserie key or clear them with `null`.
The backend resolves these stable keys to internal ids and rejects missing,
soft-deleted or cross-scenario timeseries.

Type catalog node type metadata exposes `timeserieId`,
`timeserieSecondaryId` and `timeserieIdRule` so the Structure UI can identify
timeseries-capable node types and display inherited timeserie metadata.

Authorization and permission enforcement are not implemented in the Structure
baseline. They must be added through a separate task before these endpoints are
treated as a production authorization boundary.

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

## Copy Default Metamodel For Organisation

Flow:

1. Load the active default metamodel where `organisation_id IS NULL`.
2. Validate copied values against the allowed attribute data types, node shapes
   and edge endings.
3. Create an organisation-specific metamodel row.
4. Copy node types and edge types while preserving stable keys.
5. Copy type attributes to the copied node or edge types.
6. Copy allowed connections to the copied edge and node types.
7. Commit only as part of the outer organisation creation transaction.

## Create Graph Snapshot

Flow:

1. Validate organisation state exists and is active.
2. Validate relevant metamodel rules.
3. Create one active graph for the organisation state.
4. Create graph nodes and graph edges.

## Edit Graph From Structure Tab

Flow:

1. Frontend loads graph data and type catalog for the selected organisation,
   scenario and organisation state.
2. User creates, edits or deletes graph nodes and graph edges.
3. Backend validates graph context, stable keys, type references, timeserie
   references and allowed connections.
4. Backend persists the mutation through Organisation Twin Structure Domain
   tables.
5. Frontend updates the graph view from the returned response.

## Persist Node Positions

Flow:

1. User drags one or more nodes in the Structure graph viewer.
2. Frontend updates positions optimistically.
3. Frontend sends a debounced bulk position update to the graph positions
   endpoint.
4. Backend validates node references and persists position values.
5. Frontend merges the persisted position response back into graph state.

## Copy Graph Snapshot For Scenario Copy

Flow:

1. Receive source organisation state to copied organisation state id mappings
   from Organisation States Domain.
2. Load active graphs for the source organisation states.
3. Create copied graph rows for copied organisation states.
4. Copy active graph nodes, clearing timeseries references.
5. Copy active graph edges to reference the copied graph nodes.

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

- metamodel versioning workflow after organisation creation
- graph validation API boundaries
