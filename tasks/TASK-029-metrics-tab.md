# TASK-029 Metrics Tab

## Source Plan

Approved plan: "Metrics Tab Implementation Plan".

## Goal

Replace the placeholder Metrics workspace tab with a scenario-scoped,
spreadsheet-like interface for viewing and maintaining timeserie values.

The tab lets users list all timeseries in the selected scenario, add date
columns, edit typed values by cell, import row values from CSV, and persist
changes row-by-row or all at once.

## Requirements

- Add scenario-level timeseries list API support.
- Add scenario-level timeserie value update API support.
- Extend timeserie responses with active values.
- Use the existing `timeseries` and `timeserie_values` tables.
- Do not add a database migration unless implementation discovers the existing
  model mapping is incomplete.
- Add frontend API client support for listing timeseries and updating values.
- Replace the Metrics placeholder with a real `MetricsTab`.
- Metrics must require a selected scenario but must not require a selected org
  state.
- Render timeseries as rows and dates as columns.
- Support adding manual date columns.
- Support adding the next valid date for a row based on that row's `timeUnit`.
- Support editing `number`, `string` and `boolean` values with type-appropriate
  controls.
- Prevent editing cells whose date is not a valid start date for the row's
  `timeUnit`; weeks start on Monday.
- Support row-level save and save-all-changed behavior.
- Support CSV import for one row using two columns: `date,value`, without a
  header, using comma or semicolon separators.
- Reuse existing frontend styling, API client and workspace patterns.
- Do not add new dependencies.

## Acceptance Criteria

- [ ] Metrics tab renders real UI instead of placeholder content.
- [ ] Metrics tab is available at `/schatten/{orgId}/metrics`.
- [ ] Metrics shows an empty state when no scenario is selected.
- [ ] Metrics fetches active timeseries for the selected scenario.
- [ ] Empty scenario timeseries list shows a user-visible empty state.
- [ ] Timeseries rows are sorted by stable timeserie id.
- [ ] Date columns include all active value dates plus user-added unsaved dates.
- [ ] `number` values can be edited only as finite numbers.
- [ ] `string` values can be edited as text.
- [ ] `boolean` values can be edited as blank, `true` or `false`.
- [ ] Blank cells remove that date value from the next save payload.
- [ ] Invalid time-unit date cells are read-only.
- [ ] `Save row` persists only the selected changed row.
- [ ] `Save changes` persists all changed rows.
- [ ] Successful saves refresh row baseline state and clear dirty indicators.
- [ ] Failed loads or saves show user-friendly errors.
- [ ] CSV import validates date format, time-unit start date and value type.
- [ ] Backend returns timeserie values in sorted date order.
- [ ] Backend rejects invalid values and invalid time-unit dates.
- [ ] Backend soft-deletes active values omitted from a replacement payload.
- [ ] No new dependency is added.

## Out Of Scope

- Creating or deleting timeseries from the Metrics tab.
- Editing timeserie metadata from the Metrics tab.
- Copying timeseries between scenarios.
- Pagination or virtualized grids.
- Summary or Analysis tab behavior.
- Authentication or authorization changes.
- New database schema unless required by an implementation-discovered mismatch.

## Implementation Notes

Read these before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-001-tech-stack.md
docs/domains/ORG_STATES.md
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
docs/TESTING.md
```

Expected implementation areas:

- `backend/app/api/v1/org_states/schemas.py`
- `backend/app/api/v1/org_states/org_states_service.py`
- `backend/app/api/v1/org_states/router.py`
- `frontend/src/api/timeseries.ts`
- `frontend/src/features/metrics/MetricsTab.tsx`
- `frontend/src/pages/Workspace.tsx`
- `frontend/src/styles/app.css`
- Relevant backend and frontend tests.

Backend API additions:

```text
GET   /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries
PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}/values
```

Timeserie response shape should be:

```json
{
  "id": "revenue",
  "name": "Revenue",
  "description": "Monthly revenue",
  "unit": "EUR",
  "timeUnit": "month",
  "valueUnit": "number",
  "values": [
    { "date": "2030-01-01", "value": 1000 }
  ]
}
```

`PATCH /values` request shape should be:

```json
{
  "values": [
    { "date": "2030-01-01", "value": 1000 }
  ]
}
```

Use stable public ids in API payloads. Keep internal bigint ids inside backend
persistence and service logic.

## Testing

Required:

- [ ] Frontend tests
- [ ] Backend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck

Not applicable:

- [ ] Integration tests: use existing backend API tests and frontend interaction
      tests unless implementation discovers a lightweight existing integration
      path.

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

- listing active timeseries with sorted active values
- replacing number, string and boolean values
- rejecting invalid value types
- rejecting dates that are not valid starts for the timeserie `timeUnit`
- duplicate submitted dates with last value winning
- omitted active dates being soft-deleted
- soft-deleted values being excluded from list and get responses

Frontend tests should cover:

- Metrics route rendering
- no-scenario, loading, empty and error states
- fetching by selected scenario
- date column construction
- typed cell editing and dirty row indicators
- invalid date cells being read-only
- row save and save-all payloads
- CSV import success and validation failures

Manual verification should cover:

- select a scenario in Scenarios
- open Metrics
- create a timeserie through Structure if needed
- add a date column
- edit number, string and boolean rows where available
- save one row
- save all changed rows
- import CSV into one row
- refresh and confirm persisted values are reloaded

## Documentation

Update documentation if public API behavior, domain behavior or data behavior
changes:

- `docs/domains/ORG_STATES.md`
- `docs/data/DATA-MODEL.md`
- `docs/data/DATABASE.md`
- `docs/TESTING.md`, only if Metrics-specific testing guidance is added

Diagram updates are not expected unless implementation changes schema or domain
ownership.

## Notes For AI Agent

- Read `AGENTS.md`, `ARCHITECTURE.md`, relevant domain docs and
  `docs/TESTING.md` before implementation.
- Preserve soft-delete behavior for scenario-owned timeseries and values.
- Use existing abstractions and frontend styling patterns.
- Add tests for all changed application behavior.
- Do not implement functionality outside this task scope.
- Do not add dependencies without approval.
- Report what changed and which checks were run.
