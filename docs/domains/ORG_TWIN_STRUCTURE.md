# Organisation Twin Structure Domain

Status: core domain baseline

## Purpose

Organisation Twin Structure Domain hallitsee metamodelit ja skenaariokohtaisen
ajallisen graph-rakenteen.

Metamodel maarittaa sallitut node- ja edge-tyypit. Organisaatiotilan graph on
skenaarion graph-historiasta sen target date -päivälle muodostettu projektio.

---

# Responsibilities

Owns:

- metamodels
- node types
- edge types
- type attributes
- allowed connections
- graph nodes
- graph edges

Provides:

- default metamodel
- organisation-specific metamodels
- scenario-level graph history and organisation-state projections
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

## Graph Scope And Lifetimes

Graph nodes and graph edges belong to exactly one scenario. Their stable keys
are unique among persistence-active elements inside that scenario.

`create_date` starts the logical lifetime and nullable `delete_date` ends it.
An element is visible at an organisation-state target date when
`create_date <= target_date` and `delete_date` is null or
`delete_date >= target_date`. Malformed lifetimes are rejected: deletion may
not precede creation, and an edge lifetime must remain inside both endpoint
node lifetimes.

Structure deletion normally records the selected organisation state's target
date as the logical `delete_date`. Because the logical end date is inclusive,
an element whose `create_date` equals the deletion date is instead
persistence-soft-deleted through `deleted_time`; it would otherwise reappear
in the same organisation-state projection. Same-day node deletion also
persistence-soft-deletes its connected edges. For an earlier-created node,
deletion applies a compatible logical end date to connected edges.
Persistence `deleted_time` is also used for scenario deletion and cleanup
propagation.

## Graph Snapshot Copy

When Organisation States Domain copies a scenario, Organisation Twin Structure
Domain provides the service boundary for copying graph elements visible at the
selected source organisation state's target date into the copied scenario.

Graph copy preserves node and edge stable keys, names, descriptions, type
references, logical lifetime dates, positions and dynamic attributes. Graph
node primary and secondary timeseries references are remapped to the matching
copied scenario-owned timeseries.

---

# Database Ownership

Tables:

- metamodels
- node_types
- edge_types
- type_attributes
- allowed_connections
- graph_nodes
- graph_edges

Owned exclusively by Organisation Twin Structure Domain.

Other domains may reference these tables but may not modify them directly unless a task explicitly defines a service boundary.

---

# API Ownership

Endpoints:

```text
GET    /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/graph/history
GET    /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/graph/types
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

Scenario history responses expose stable node and edge keys plus `createDate`
and nullable `deleteDate`. They include logical history but exclude rows with a
persistence-level `deleted_time`.

All Structure endpoints require an active application session, and mutations
require the shared exact-Origin and session-CSRF guard. Both application roles
intentionally access Structure data under every organisation; route keys do not
establish membership or object-level permission.

Authenticated node, edge, copied graph and copied metamodel creation writes
`created_by`. Patches, position updates, logical lifetime changes and reference
cleanup write `modified_by`. Persistence soft deletion writes `modified_by` and
`deleted_by`, including cascaded graph rows. Historical nullable audit values
are not backfilled.

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

## Create And Project Graph Elements

Flow:

1. Validate organisation state exists and is active.
2. Validate relevant metamodel rules.
3. Create scenario-owned graph nodes and graph edges with the organisation
   state's target date as `create_date`.
4. Project visible elements using their logical lifetimes.

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
   and source-to-copied timeserie id mappings from Organisation States Domain.
2. Load graph elements visible at the selected source target date.
3. Copy visible graph nodes, translating primary and secondary timeseries
   references to copied-scenario rows.
4. Copy visible graph edges to reference the copied graph nodes.

---

# AI Agent Guidance

When implementing organisation twin structure features:

- read this document before changing metamodel, type or graph data
- preserve scenario ownership and logical lifetime invariants
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
