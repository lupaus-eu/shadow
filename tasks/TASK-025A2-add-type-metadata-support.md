# TASK-025A2 Add Type Metadata Support

## Source Plan

Follow-up to `TASK-025A Backend Structure API`.

AI review found that the Structure UI task needs reliable user-friendly node and
edge type metadata for labels, colors and create/edit forms. `TASK-025A`
currently exposes graph nodes and edges with stable type keys only.

## Goal

Add backend type metadata/catalog support for the Structure tab so the frontend
can render node and edge types with user-friendly names, stable colors and
available type choices without hardcoding metamodel data.

The API must expose active type metadata for the selected organisation's active
metamodel in the same organisation/scenario/org-state context as the graph API.

## Requirements

- Add Pydantic response schemas for node type and edge type metadata.
- Include enough metadata for the frontend to render:
  - stable type id/key
  - display name
  - optional technical name
  - node color and shape
  - edge style and source/target endings
- Expose a type catalog endpoint under the existing Structure API route:
  - `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/types`
- The endpoint must validate the same active organisation, scenario and
  organisation state context as `GET .../graph`.
- The endpoint must return only active node and edge types from the active
  organisation-specific metamodel.
- Keep the existing graph response shape unchanged unless tests prove a small
  backward-compatible addition is required.
- Add backend pytest coverage for successful catalog reads and missing parent
  resources.

Note: Authorization/permission checks are out of scope and must be added in a
separate, dedicated task.

## Acceptance Criteria

- [ ] Type metadata schemas exist in
      `backend/app/api/v1/org_twin_structure/schemas.py`.
- [ ] `GET .../graph/types` is implemented in
      `backend/app/api/v1/org_twin_structure/router.py`.
- [ ] The service returns active node and edge type metadata from the selected
      organisation's active metamodel.
- [ ] Missing active organisation, scenario or organisation state returns HTTP
      `404`.
- [ ] Missing active organisation metamodel still follows existing error
      behavior.
- [ ] Existing graph CRUD and bulk position endpoints remain compatible with
      `TASK-025A`.
- [ ] pytest tests cover type catalog success and missing-resource cases.
- [ ] All backend tests pass: `cd backend && uv run pytest`.
- [ ] Linting and type checking pass: `uv run ruff check .` and
      `uv run pyright`.

## Out Of Scope

- Frontend implementation of the Structure tab.
- New metamodel editing APIs.
- Creating, updating or deleting node types or edge types.
- Attribute-definition editing UI or validation beyond exposing existing type
  metadata.
- Authorization and permission enforcement.
- New third-party dependencies.
- Database schema changes unless implementation proves existing metadata
  columns are insufficient.

## Implementation Notes

### Expected Response Shape

Use this JSON shape unless there is a strong existing local API convention that
requires a minor naming adjustment:

```json
{
  "nodeTypes": [
    {
      "id": "nt_person",
      "name": "Person",
      "displayName": "Person",
      "color": "#FECDC2",
      "shape": "rectangle"
    }
  ],
  "edgeTypes": [
    {
      "id": "et_reports_to",
      "name": "Reports to",
      "displayName": "Reports to",
      "style": "solid",
      "sourceEnd": "none",
      "targetEnd": "arrow"
    }
  ]
}
```

### Files To Create / Modify

- `backend/app/api/v1/org_twin_structure/schemas.py`
- `backend/app/api/v1/org_twin_structure/router.py`
- `backend/app/api/v1/org_twin_structure/org_twin_structure_service.py`
- `backend/tests/test_org_twin_structure_api.py`

### Domain Context

Read before implementation:

```text
docs/domains/ORG_TWIN_STRUCTURE.md
docs/concepts/METAMODEL.md
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
```

The existing `node_types` and `edge_types` models already include UI metadata
columns such as `ui_color`, `ui_shape`, `ui_style`, `ui_source_end` and
`ui_target_end`. Prefer exposing those columns rather than adding new schema.

## Testing

Required:

- [ ] Backend API tests
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests: frontend implementation is handled in `TASK-025B`.
- [ ] Database migration: expected to reuse existing type metadata columns.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest tests/test_org_twin_structure_api.py -v
uv run pytest
uv run pyright
```

## Documentation

Documentation and diagram updates for the Structure feature and graph model
refactor are handled in `TASK-025C`.

Do not update documentation in this task unless implementation unexpectedly
changes the API contract beyond the endpoint described here or requires a
database schema change. If that happens, stop and confirm whether the change
belongs in this task or should be moved to `TASK-025C`.

## Notes For AI Agent

- Read `AGENTS.md`, `ARCHITECTURE.md`, this task and the domain/context docs
  listed above before implementation.
- Implement only type metadata/catalog support.
- Do not add authorization checks in this task.
- Do not add frontend code in this task.
- Do not add new dependencies.
- Prefer existing service-layer patterns in `backend/app/api/v1/`.
- Add or update tests for all changed backend behavior.
- Report the exact verification commands and results at the end.
