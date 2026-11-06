# TASK-028 Structure Timeserie Mode

## Source Plan

Approved plan: "Structure Timeserie Mode".

## Goal

Implement a conditional `Timeserie` mode on the Structure page editor panel. The
mode is available only when a Metric node is selected, and the `Timeserie`
button appears between `Show & Edit` and `AI Assistant`.

The mode lets users manage the selected Metric node's timeseries links, check
effective timeseries existence, create missing timeseries records, and delete
existing timeseries records with confirmation.

## Requirements

- Add scenario-level timeseries API support for create, get, exists and soft
  delete.
- Extend graph node and node type metadata DTOs to expose timeseries link fields
  and timeseries type metadata.
- Allow graph node patch requests to update primary and secondary timeseries
  links by stable timeserie key or clear them with `null`.
- Add `timeserie` as a Structure editor mode.
- Render the `Timeserie` mode button only for selected Metric nodes or node
  types with timeseries metadata.
- Add a Structure-side Timeserie panel for editing link fields, listing
  effective timeserie ids, checking existence, creating missing records and
  deleting existing records.
- Reuse existing frontend styling and API client patterns.

## Acceptance Criteria

- [ ] `Timeserie` button is hidden when no node, an edge, or a non-timeseries
      node type is selected.
- [ ] `Timeserie` button is visible between `Show & Edit` and `AI Assistant`
      when a Metric/timeseries-capable node is selected.
- [ ] Leaving a Metric/timeseries-capable node while in `timeserie` mode falls
      back to `edit`.
- [ ] Selected node primary and secondary timeseries links can be saved and
      cleared.
- [ ] Effective timeserie ids are shown with loading, exists and missing states.
- [ ] Missing timeseries can be created with name, description, unit, time unit
      and value unit.
- [ ] Existing timeseries can be deleted only after confirmation.
- [ ] Backend validates time unit, value unit and stable timeserie keys.
- [ ] Relevant frontend and backend tests pass.

## Out Of Scope

- Full Metrics tab value grid implementation.
- Timeseries copy between scenarios.
- New dependencies.
- Authorization or permission enforcement changes.
- Database schema changes unless implementation discovers the existing
  schema/model mapping is incomplete.

## Implementation Notes

Relevant documents:

```text
docs/architecture/overview.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
docs/operations/testing.md
```

Expected implementation areas:

- Backend timeseries schemas/service/router under Organisation States domain.
- Backend graph schemas/service updates under Organisation Twin Structure
  domain.
- Frontend API client for timeseries.
- `frontend/src/features/structure/GraphEditorToolbar.tsx`
- `frontend/src/features/structure/StructureTab.tsx`
- New Structure `TimeseriePanel` component.
- Structure frontend tests and backend API/service tests.

Use stable public ids in API payloads. Keep internal bigint ids inside backend
persistence/service logic.

## Testing

Required:

- [ ] Frontend tests
- [ ] Backend tests
- [ ] Integration tests where practical
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck

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

## Documentation

Update documentation if public API behavior, domain behavior or data behavior
changes:

- `docs/architecture/domains/ORG_STATES.md`
- `docs/architecture/domains/ORG_TWIN_STRUCTURE.md`
- `docs/architecture/data/DATA-MODEL.md`
- `docs/architecture/data/DATABASE.md`
- `docs/architecture/diagrams/*.puml`
- `docs/architecture/diagrams/generated/*.svg`

## Notes For AI Agent

- Read `AGENTS.md`, `docs/architecture/overview.md`, relevant domain docs and
  `docs/operations/testing.md` before implementation.
- Preserve soft-delete behavior for scenario-owned timeseries and values.
- Use existing abstractions and frontend styling patterns.
- Add tests for all changed application behavior.
- Do not implement functionality outside this task scope.
