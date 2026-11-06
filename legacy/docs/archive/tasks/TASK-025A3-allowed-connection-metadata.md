# TASK-025A3 Allowed Connection Metadata

## Source Plan

Follow-up split from `TASK-025B Frontend Structure UI`.

Backend changes were needed so the frontend can filter and select valid edge
types based on the selected source and target node type. These changes belong
under the `TASK-025A` backend Structure API line, not the frontend-only
`TASK-025B` branch.

This task documents the backend changes split out from
`feature/TASK-025B-frontend-structure-ui`.

## Goal

Extend the Structure graph type catalog response with allowed source/target
node-type pairs for each edge type.

This allows the frontend to determine valid edge type choices without
hardcoding metamodel rules.

## Requirements

- Add `AllowedConnectionMetadataResponse` to
  `backend/app/api/v1/org_twin_structure/schemas.py`.
- Add `allowedConnections` to `TypeCatalogResponse`.
- Update `get_graph_type_catalog` in
  `backend/app/api/v1/org_twin_structure/org_twin_structure_service.py` to
  return active `AllowedConnection` rows for the active metamodel.
- Resolve database IDs to stable edge and node type keys in the API response.
- Raise the existing invalid graph exception if an allowed connection
  references a missing active type.
- Update `backend/tests/test_org_twin_structure_api.py` to assert
  `allowedConnections` is returned.

## Acceptance Criteria

- [ ] `GET .../graph/types` returns `nodeTypes`, `edgeTypes` and
      `allowedConnections`.
- [ ] Each allowed connection uses this JSON shape:

```json
{
  "edgeTypeId": "et_reports_to",
  "sourceNodeTypeId": "nt_person",
  "targetNodeTypeId": "nt_person"
}
```

- [ ] Only active allowed connections for the selected organisation's active
      metamodel are returned.
- [ ] Existing type catalog behavior remains backward-compatible except for the
      additive `allowedConnections` field.
- [ ] `backend/tests/test_org_twin_structure_api.py` covers the new response
      field.

## Out Of Scope

- Frontend implementation.
- Metamodel editing UI or API.
- New database schema or migrations.
- Authorization changes.
- New dependencies.

## Implementation Notes

The intended schema file is:

```text
backend/app/api/v1/org_twin_structure/schemas.py
```

The endpoint response is an additive extension to the existing type catalog
contract. Keep the existing `nodeTypes` and `edgeTypes` shapes unchanged.

## Testing

Required:

- [ ] Backend API tests
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests: frontend implementation is handled in `TASK-025B`.
- [ ] Database migration: this task exposes existing metamodel relationship
      data.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest tests/test_org_twin_structure_api.py -v
uv run pytest
uv run pyright
```

## Documentation

No broader documentation updates are expected for this task. It documents an
additive backend response field needed by the Structure UI.

## Notes For AI Agent

- Read `AGENTS.md`, `docs/architecture/overview.md` and this task before implementation.
- Implement only backend allowed connection metadata support.
- Do not add frontend code in this task.
- Do not add authorization checks in this task.
- Do not add new dependencies.
- Keep the type catalog change additive.
- Report the exact verification commands and results at the end.
