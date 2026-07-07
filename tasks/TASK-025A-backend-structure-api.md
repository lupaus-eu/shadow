# TASK-025A Backend Structure API

## Source Plan

Approved plan: "Structure-tab feature (Structure view)" — Phase A (Backend).

Implement REST API endpoints for graphs, nodes and edges to support the Structure tab UI. Add Pydantic schemas, CRUD endpoints and tests. Authorization is explicitly out of scope for this task and will be implemented in a follow-up task.

## Goal

Add backend REST API endpoints to support graph -node, and -edge CRUD operations within an organization state context so the frontend can load, create, update and bulk-update graph structures.

## Requirements

- Create Pydantic request/response schemas for graphs, nodes, edges, and position updates
- Implement REST endpoints for graph -node, and -edge operations (GET, POST, PATCH, DELETE)
- Implement bulk position update endpoint for efficient node coordinate updates
- Add comprehensive validation for node/edge data, position bounds, and schema constraints
- Leverage existing `org_twin_structure_service.py` and database models; extend if needed
- Write pytest tests covering CRUD, validation and edge cases
- Ensure all endpoints follow existing FastAPI conventions (dependency injection, error handling, response codes)
- Add a standalone DB migration `db/migrations/004_alter_graphs_to_scenarios.sql` for the graph model refactor, removing the graphs table and mapping graph nodes and edges to the scenarios table
- Update code to reflect the DB changes made by this migration

Note: Authorization/permission checks are out of scope for this task and must be added in a separate, dedicated task.

## Acceptance Criteria

- [ ] `backend/app/api/v1/org_twin_structure/schemas.py` created with Pydantic models for Graph, GraphNode, GraphEdge, PositionUpdate, BulkPositionUpdate, and create/update DTOs
- [ ] `backend/app/api/v1/org_twin_structure/router.py` created with endpoints for graphs, nodes, edges and bulk position update
- [ ] Router integrated into `backend/app/api/v1/router.py`
- [ ] Input validation in place and proper error codes used (400, 404, 409, 422)
- [ ] pytest tests in `backend/tests/test_org_twin_structure_api.py` cover CRUD, validation and edge cases
- [ ] All tests pass: `cd backend && uv run pytest`
- [ ] Linting and type checking pass: `uv run ruff check .` and `uv run pyright`

## Out Of Scope

- Authorization and permission enforcement (TBD in a follow-up task)
- WebSocket or real-time graph updates
- Graph layout algorithms or auto-positioning
- Database schema changes unless strictly required

## Implementation Notes

### Files to Create / Modify

- `backend/app/api/v1/org_twin_structure/schemas.py` — Pydantic models
- `backend/app/api/v1/org_twin_structure/router.py` — FastAPI endpoints
- `backend/app/api/v1/router.py` — include new router
- `backend/app/api/v1/org_twin_structure/org_twin_structure_service.py` — extend if needed
- `backend/tests/test_org_twin_structure_api.py` — pytest tests
- `db/migrations/004_alter_graphs_to_scenarios.sql` - fix db structure for graph data

### Endpoint Summary

All endpoints are nested under `/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/`

- Graphs: get
- Nodes: create, update, delete
- Edges: create, update, delete
- Bulk positions: `PATCH /{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/positions`

### Validation Rules

- Node position: numeric bounds enforced in schema
- Duplicate node/edge keys within a graph => 409 Conflict
- Mutations validate that referenced graph/nodes exist

## Testing

Run:

```bash
cd backend
uv run pytest tests/test_org_twin_structure_api.py -v
```

Tests should cover CRUD, validation and edge cases. Authorization tests are not required in this task.

## Notes For AI Agent

- Read `AGENTS.md` and `ARCHITECTURE.md` before implementing.
- Authorization is out of scope; do not add auth checks in tests or endpoints here.
- Use existing service layer and patterns in `backend/app/api/v1/`.
- Do not add new third-party dependencies without approval.
