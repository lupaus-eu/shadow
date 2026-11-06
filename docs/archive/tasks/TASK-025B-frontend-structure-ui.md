# TASK-025B Frontend Structure UI

## Source Plan

Approved plan: "Structure-tab feature (Structure view)" — Phase B (Frontend).

Implement the Structure tab UI for viewing and editing org-state graphs. Add an API client, React components, tests, and integrate the tab into the workspace. Authorization is out of scope for this task and will be implemented in a follow-up task.

## Goal

Implement the "Structure" tab UI to display, view and edit org-state graphs. Users must be able to load graphs, create/edit/delete nodes and edges, drag nodes to update positions, and persist changes to the backend. The UI will include three modes: "Show and Edit", "Create" and "AI Assistant" (the latter left as an empty state for future work).

## Requirements

- Create API client module (`orgTwinStructure.ts`) with typed fetch wrappers for backend endpoints, including the graph type catalog endpoint (see Backend API Paths section below)
- Implement `StructureTab` component that loads and manages graph state within workspace context
- Implement `GraphViewer` component to render nodes and edges (Cytoscape.js approved)
- Implement editor UI: node/edge creation forms, metadata editing, bulk position updates (debounced on drag)
- Add node list in left sidebar: grouped by node type, collapsible, with type counters and unique background colors per type
- Add node filtering: checkboxes to toggle node type visibility, "Select All" and "Deselect All" buttons
- Use Cytoscape's native zoom/pan interactions and add a "Zoom to Fit" button
- Support node drag-to-reposition with optimistic UI update and debounced bulk backend commit
- Add three UI modes: "Create", "Show and Edit" and "AI Assistant" mode (left with an empty state to be implemented later)
- Place graph viewer in center and editor panel on the right
- Write Vitest unit and component tests for new components
- Attach real Structure content to the existing `"graph"` workspace tab and preserve its current scenario+org-state gating

Note: Authorization and permission enforcement are out of scope and will be added in a separate task.
Adding the Cytoscape.js dependency is acceptable in this task if needed for the approved graph viewer implementation.

## Acceptance Criteria

- [ ] `frontend/src/api/orgTwinStructure.ts` created with typed fetch functions for graph data, graph type catalog, nodes, edges and bulk position updates
- [ ] `frontend/src/features/structure/StructureTab.tsx` created, loads graph and renders GraphViewer and editor panel
- [ ] `frontend/src/features/structure/GraphViewer.tsx` implemented with Cytoscape.js, supports native pan/zoom, selection and drag
- [ ] Editor toolbar and forms (`GraphEditorToolbar.tsx`, `NodeForm.tsx`, `EdgeForm.tsx`) created
- [ ] Left sidebar node list grouped by type with counters and colors; clicking a node focuses and centers it
- [ ] Node type filtering with "Select All" and "Deselect All" buttons
- [ ] Node drag-to-reposition with optimistic UI and debounced `bulkUpdatePositions` commit (300-500ms debounce)
- [ ] Modes implemented: "Create", "Show and Edit", and "AI Assistant" (Create is the default; AI Assistant shows empty state)
- [ ] Vitest tests added: `StructureTab.test.tsx`, `GraphViewer.test.tsx`, component tests (>70% coverage target)
- [ ] Real Structure content is attached to the existing `"graph"` workspace tab and preserves the current scenario+org-state gating in the workspace UI
- [ ] All frontend tests pass and build succeeds (`pnpm test`, `pnpm build`)

## Out Of Scope

- Authorization and permission enforcement (TBD in follow-up task)
- Real-time collaboration (WebSockets)
- Graph layout algorithms or auto-positioning
- Export/import and undo/redo

## Implementation Notes

### Files to Create / Modify

- `frontend/src/api/orgTwinStructure.ts` — typed fetch wrappers
- `frontend/src/features/structure/StructureTab.tsx`
- `frontend/src/features/structure/GraphViewer.tsx`
- `frontend/src/features/structure/GraphEditorToolbar.tsx`
- `frontend/src/features/structure/NodeForm.tsx`
- `frontend/src/features/structure/EdgeForm.tsx`
- `frontend/src/features/structure/NodeList.tsx`
- `frontend/src/features/structure/TimeseriesMode.tsx` (optional)
- `frontend/src/features/structure/*.test.tsx` — Vitest tests
- `frontend/src/workspace/workspaceTabs.ts` — update only if needed to preserve the existing `"graph"` tab gating and attach real Structure content

### UI Modes

The UI must offer three modes:

- "Create": default focused mode for adding new nodes and edges
- "Show and Edit": mode where users can inspect the graph and perform edits on selected nodes/edges
- "AI Assistant": placeholder empty state for future assistant features

### Backend API Paths

The backend API endpoints for structure operations (from TASK-025A and TASK-025A2) are:

All endpoints are nested under `/api/v1/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/`

**Graph operations:**
- `GET /api/v1/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/graph` — Fetch graph with all nodes and edges
- `GET /api/v1/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/graph/types` — Fetch node and edge type metadata for labels, colors and form choices

**Node operations:**
- `POST /api/v1/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/graph/nodes` — Create node
- `PATCH /api/v1/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/graph/nodes/{nodeKey}` — Update node
- `DELETE /api/v1/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/graph/nodes/{nodeKey}` — Delete node

**Edge operations:**
- `POST /api/v1/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/graph/edges` — Create edge
- `PATCH /api/v1/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/graph/edges/{edgeKey}` — Update edge
- `DELETE /api/v1/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/graph/edges/{edgeKey}` — Delete edge

**Position updates:**
- `PATCH /api/v1/organisations/{orgKey}/scenarios/{scenarioKey}/org-states/{orgStateKey}/graph/positions` — Bulk update node positions

### Data Flow

1. Load graph and graph type metadata on tab activation via API client using the GET graph and GET graph type catalog endpoints
2. Create/update/delete operations call API client endpoints and update local state optimistically
3. Node position updates are debounced and sent via the bulk position update endpoint

## Testing

Run:

```bash
cd frontend
pnpm test
pnpm lint
pnpm build
```

Tests should cover API client payloads, component rendering and interactions. Authorization tests are out of scope for this task.

## Notes For AI Agent

- Read `AGENTS.md` and `docs/architecture/overview.md` before implementing.
- Authorization is out of scope for this task; do not add auth checks in code or tests here.
- Use existing hooks, contexts and API utility patterns in the frontend.
