# TASK-030 Summary Tab

## Source Plan

Approved plan: "Summary Tab Implementation Plan".

## Goal

Replace the placeholder Summary workspace tab with a scenario-scoped timeline
that combines organisation structure history, events and timeseries values on a
shared date axis.

The view lets users correlate structural lifetimes, dated events and metric
trends. It provides filtering, row visibility controls, timeline zooming,
coordinated scrolling, resizable timeseries rows and refresh behavior without
requiring a selected organisation state.

## Requirements

### Temporal graph history

- Add nullable `delete_date` columns to `graph_nodes` and `graph_edges` through
  a versioned database migration.
- Keep `deleted_time` reserved for persistence-level soft deletion, including
  scenario deletion, cleanup and Structure deletion when an element is deleted
  on its `create_date`.
- Treat a graph element as visible at an organisation-state target date when
  `create_date <= target_date` and `delete_date` is null or
  `delete_date >= target_date`.
- Change Structure node and edge deletion to normally record the selected
  organisation state's target date as the logical `delete_date` instead of
  removing the element from historical reads. When the target date equals the
  element's `create_date`, persistence-soft-delete it so it does not reappear in
  the same projection.
- When logically deleting a node, apply a compatible deletion date to its
  connected edges. When persistence-soft-deleting a same-day node, also
  persistence-soft-delete its connected edges.
- Reject deletion dates before creation dates and reject edge lifetimes outside
  the lifetimes of their endpoint nodes.
- Preserve existing persistence-level soft-delete propagation behavior.

### Backend APIs

- Add scenario-level graph history support:

  ```text
  GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/graph/history
  ```

- Add scenario-level graph type catalog support:

  ```text
  GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/graph/types
  ```

- The history response must use stable public ids and include all historical
  graph elements that have not been persistence-soft-deleted.
- Graph node and edge history responses must include `createDate` and nullable
  `deleteDate` values.
- The type catalog must reuse existing node and edge type metadata, including
  display names and node colors.
- Both endpoints must validate organisation/scenario ownership and return the
  established missing-resource errors.
- Reuse the existing scenario-level event and timeseries APIs unchanged.

### Frontend data loading

- Extend `frontend/src/api/orgTwinStructure.ts` with graph-history DTOs,
  `fetchGraphHistory` and scenario-level `fetchGraphTypeCatalog` support.
- Load graph history, graph types, events and timeseries concurrently for the
  selected scenario.
- Abort in-flight requests when the scenario changes or the Summary component
  unmounts.
- Prevent stale responses from replacing data for a newer scenario selection.
- Show user-friendly no-scenario, loading, empty, error and retry states.

### Summary timeline UI

- Replace the Summary placeholder with a real `SummaryTab` at
  `/shadow/{orgId}/summary`.
- Summary must require a selected scenario but must not require a selected
  organisation state.
- Show `Summary of` and the selected scenario name in the page header.
- Provide Filters, Rows, timeline zoom and Refresh controls.
- Render a fixed-width item column beside a horizontally scrollable shared
  timeline.
- Build the timeline from valid node, edge, event and timeseries dates.
- Start the timeline at the earliest represented date and end it at the end of
  the month following the latest represented date.
- Expand the timeline bounds to include the selected organisation-state target
  date when one is available.
- Use a sensible current-date fallback range when there are no valid dates.
- Ignore malformed dates without crashing the page.

### Timeline ordering and rendering

- Sort nodes by node-type display name, node name and stable node id.
- Place each node's outgoing edges immediately after that node, sorted by label
  and stable edge id.
- Sort events by target date, name and stable event id.
- Sort timeseries by stable timeserie id.
- Render nodes as lifetime bars using their node-type color.
- Render edges as thinner lifetime bars using the target node's type color.
- Extend open-ended node and edge bars to the timeline's right boundary.
- Render events as green circular markers at their target dates.
- Render numeric timeseries as line charts with points, a zero baseline,
  rounded Y-axis bounds and nearest-point hover details.
- Show a clear message for string and boolean timeseries, or numeric
  timeseries without numeric values, instead of rendering a line chart.
- Include useful row labels and hover details such as stable id, type,
  source/target, dates, event details, unit, time unit and value unit.

### Timeline interaction

- Automatically fit the initial zoom to the available viewport when the
  selected scenario changes.
- Provide fine-grained minus/plus zoom buttons and a range input.
- Limit zoom to approximately one pixel per seven days through 80 pixels per
  day.
- Keep the date header, timeline rows and bottom horizontal scrollbar aligned.
- Synchronize vertical scrolling between item labels and timeline rows.
- Allow all timeseries rows to be resized together, using a default height of
  approximately 92 px and bounded minimum and maximum heights.
- Add a button for toggling the visibility of individual rows (similar to the
  one for node types on the Structure page).
- Make the Rows menu's All action restore individually hidden rows while
  retaining active category filters.
- Add Filters controls for nodes and edges, edges independently, events,
  timeseries and individual node types.
- Add All and None shortcuts for node-type filters.
- Hide an edge when either endpoint's node type is filtered out.

### Styling and accessibility

- Reuse existing design tokens, frontend components, API clients and workspace
  patterns.
- Add reusable Summary styles to `frontend/src/styles/app.css` rather than
  relying on large inline-style blocks.
- Give buttons, range controls, filter controls and resize handles accessible
  names and semantics.
- Expose the filter trigger's expanded state.
- Preserve full row details through titles or equivalent accessible details
  when long labels are visually truncated.
- Announce loading, error and empty states appropriately.
- Keep the timeline usable at narrower workspace widths.
- Do not add new dependencies.

## Acceptance Criteria

- [ ] Summary renders real UI instead of placeholder content.
- [ ] Summary is available at `/shadow/{orgId}/summary`.
- [ ] Summary is enabled without an organisation state and shows an empty state
      when no scenario is selected.
- [ ] Selecting or changing a scenario loads the correct graph history, graph
      types, events and timeseries without stale data races.
- [ ] Failed loads show a user-friendly error and can be retried with Refresh.
- [ ] An empty scenario shows a user-visible empty timeline state.
- [ ] Graph history preserves logical creation and deletion dates while
      excluding persistence-soft-deleted rows.
- [ ] Structure graph projection respects both creation and logical deletion
      dates at the selected organisation-state target date.
- [ ] Logical node deletion applies compatible dates to connected edges.
- [ ] Invalid node and edge lifetimes are rejected by the backend.
- [ ] Timeline bounds include all valid rendered data dates and use the defined
      fallback when no valid dates exist.
- [ ] Nodes, outgoing edges, events and timeseries use deterministic ordering.
- [ ] Node, edge, event and numeric timeseries rows render on the shared date
      axis with the specified visual forms.
- [ ] Nonnumeric or empty numeric timeseries show an explanatory message.
- [ ] Numeric charts handle positive, negative, mixed, zero and fractional
      values and expose nearest-point hover details.
- [ ] Category and node-type filters update visible rows correctly.
- [ ] Edges are hidden when either endpoint node type is hidden.
- [ ] Individual row visibility can be toggled and Rows > All restores
      individually hidden rows without clearing category filters.
- [ ] Initial zoom fits the selected scenario and manual zoom controls stay
      within the defined limits.
- [ ] Header, rows and horizontal scrollbar remain aligned while scrolling.
- [ ] Label and timeline vertical scrolling remains synchronized.
- [ ] Timeseries row resizing respects the defined minimum and maximum sizes.
- [ ] Summary controls and states have appropriate accessible labels and
      semantics.
- [ ] No new dependency is added.

## Out Of Scope

- Editing graph nodes or edges from the Summary tab.
- Creating, editing or deleting events from the Summary tab.
- Creating, editing or deleting timeseries or timeseries values from the
  Summary tab.
- Comparing multiple scenarios in one timeline.
- AI-generated analysis or Analysis tab behavior.
- Authentication or authorization changes.
- Pagination or timeline virtualization.
- Replacing existing Structure, Events or Metrics workflows.
- Any architecture change; if one becomes necessary, stop and propose an ADR
  before implementation.

## Implementation Notes

Read these before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0001-tech-stack.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/architecture/concepts/ORGANISATION_STATE.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
db/migrations/README.md
docs/operations/testing.md
```

Expected implementation areas:

- `backend/app/api/v1/org_twin_structure/models.py`
- `backend/app/api/v1/org_twin_structure/schemas.py`
- `backend/app/api/v1/org_twin_structure/org_twin_structure_service.py`
- `backend/app/api/v1/org_twin_structure/router.py`
- A new migration under `db/migrations/`
- `frontend/src/api/orgTwinStructure.ts`
- `frontend/src/features/summary/SummaryTab.tsx`
- Testable Summary timeline helper modules as needed
- `frontend/src/pages/Workspace.tsx`
- `frontend/src/styles/app.css`
- Relevant backend and frontend tests

The graph history response should follow the existing camelCase API convention:

```json
{
  "nodes": [
    {
      "id": "node-1",
      "name": "Sales",
      "nodeTypeId": "team",
      "createDate": "2026-01-01",
      "deleteDate": null,
      "attributes": {}
    }
  ],
  "edges": [
    {
      "id": "edge-1",
      "name": "Owns",
      "edgeTypeId": "owns",
      "sourceNodeId": "node-1",
      "targetNodeId": "node-2",
      "createDate": "2026-02-01",
      "deleteDate": "2026-08-01",
      "attributes": {}
    }
  ]
}
```

Use stable public ids in API payloads. Keep internal bigint ids inside backend
persistence and service logic. Keep timeline model construction in pure helper
functions where practical so date, ordering, filtering, chart-scale and zoom
behavior can be tested without depending on layout rendering.

## Testing

Required:

- [ ] Frontend tests
- [ ] Backend tests
- [ ] Migration verification
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck

Not applicable:

- [ ] Broad end-to-end tests: use existing backend API tests and frontend
      interaction tests unless implementation discovers a lightweight existing
      end-to-end path.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build

cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Backend tests should cover:

- graph history organisation/scenario ownership and missing resources
- graph history creation and logical deletion dates
- exclusion of persistence-soft-deleted graph elements
- graph visibility before creation, during lifetime and after logical deletion
- logical node deletion and connected-edge deletion dates
- rejection of invalid deletion dates and invalid edge lifetimes
- scenario-level graph type catalog behavior
- stable response ordering and public ids
- clean migration application against the current schema

Frontend tests should cover:

- Summary route rendering
- no-scenario, loading, empty, error and retry states
- concurrent fetching for the selected scenario
- request cancellation and scenario switching
- timeline date bounds and deterministic row ordering
- node, edge, event, numeric timeseries and nonnumeric timeseries rendering
- positive, negative, mixed, zero and fractional chart scales
- nearest-point hover details
- category filters, node-type All/None and endpoint-dependent edge visibility
- individual row visibility toggling and Rows All behavior
- initial zoom fitting and manual zoom limits
- synchronized scrolling and timeseries row resizing
- malformed and missing data handling
- accessible names and state semantics for controls and status messages

Manual verification should cover:

- select a scenario and open Summary without selecting an organisation state
- verify nodes and edges with different creation and deletion dates
- verify events and numeric, string and boolean timeseries
- use category and node-type filters
- toggle individual row visibility and restore rows with Rows > All
- zoom, scroll and resize timeseries rows
- hover numeric timeseries values
- refresh the data and switch scenarios
- confirm logical graph deletions remain in history and disappear only after
  their effective target date in Structure

## Documentation

Update:

- `docs/architecture/overview.md`
- `docs/architecture/domains/ORG_TWIN_STRUCTURE.md`
- `docs/architecture/data/DATA-MODEL.md`
- `docs/architecture/data/DATABASE.md`
- `docs/operations/testing.md`
- `docs/architecture/diagrams/db-physical-schema.puml`
- `docs/architecture/diagrams/generated/db-physical-schema.svg`
- Add a Summary manual QA checklist under `docs/operations/qa/`

Update additional domain or concept documentation if implementation changes
documented ownership, invariants or lifecycle behavior. Diagram changes are
required because the physical graph schema gains logical deletion dates.

## Notes For AI Agent

- Read `AGENTS.md`, `docs/architecture/overview.md`, the task and all documents listed in
  Implementation Notes before implementation.
- Implement only this task's scope.
- Keep logical graph lifetime dates separate from persistence-level soft-delete
  timestamps.
- Preserve organisation/scenario ownership validation and stable public ids.
- Reuse existing abstractions, styles, API clients and workspace patterns.
- Do not add dependencies without approval.
- Add or update tests for every changed application behavior.
- Do not remove existing tests without approval.
- If implementation requires an architecture decision, stop and propose an ADR
  before coding.
- Report what changed and which checks were run.
