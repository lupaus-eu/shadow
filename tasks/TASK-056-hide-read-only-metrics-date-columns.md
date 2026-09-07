# TASK-056 Hide Read-Only Metrics Date Columns

## Source Plan

Developer-approved plan: hide a Metrics date column when every currently
visible Timeserie has a read-only cell with no value for that date; retain it
when at least one visible Timeserie can edit that date or a visible derived
Timeserie has a value for it.

## Goal

Reduce visual noise in the Metrics grid by rendering only date columns that
are actionable for the current visible Timeseries or contain visible derived
data. A column with no editable cell and no derived value in the displayed rows
must be hidden without changing the underlying grid-date collection or any
persistence behavior.

## Requirements

- Define the Metrics date-cell editability rule in one shared frontend helper:
  a cell is editable only when its Timeserie is not derived and the date is a
  valid start date for that Timeserie's `timeUnit`.
- Do not treat temporary save-time disabled controls as read-only for this
  purpose.
- After the existing inclusive `From`/`Until` range filtering, render a date
  column if at least one currently displayed Timeserie has an editable cell
  for it, or a currently displayed derived Timeserie has an active value for
  that date.
- Base this decision on the post-filter, post-sort displayed Timeseries, not
  the complete scenario Timeserie list. Changing kind or time-unit filters
  must recalculate the rendered columns.
- A blank but otherwise editable cell qualifies as editable. A derived row is
  read-only, but its active value qualifies to show the date column when the
  Derived metrics filter makes that row visible. Invalid time-unit dates and
  blank derived cells do not qualify.
- Preserve the complete unfiltered date collection for draft state, dirty-row
  calculation, next-date generation, CSV imports and row/bulk replacement save
  payloads. Hiding a column must never omit an existing value from a save.
- Retain existing date-range, row-filter, derived-metric, save, CSV and grid
  scrolling behavior.
- Do not add dependencies or modify backend APIs, persistence, migrations,
  domain rules, authentication, authorization, routing or styles unless a
  test exposes a direct existing styling defect.

## Acceptance Criteria

- [ ] A date represented only by visible invalid-grain cells, or blank
      read-only derived cells, is absent from the rendered Metrics grid.
- [ ] A date with an active value in a visible derived Timeserie is rendered,
      even when no visible normal Timeserie can edit that date; hiding derived
      metrics hides that derived-only date column again.
- [ ] A date remains rendered when any one visible normal Timeserie has a
      valid editable cell, whether it currently has a value or is blank.
- [ ] Changing Metrics kind or time-unit filters hides and restores columns
      according to the currently displayed rows.
- [ ] A manually added date invalid for every currently visible row is not
      rendered, while remaining in the full date collection for existing
      behavior.
- [ ] Existing `From`/`Until` filtering remains inclusive and saving after
      columns are hidden preserves off-screen dates in replacement payloads.
- [ ] No backend contract, schema, migration or public API behavior changes.
- [ ] Relevant frontend tests, lint, test suite and build/type checking pass.

## Out Of Scope

- Changing Timeserie or derived-metric editability rules.
- Persisting date-range or Metrics filter state.
- Adding an explicit show-read-only-columns preference.
- Changes to the backend, database, data model, domain documentation,
  migrations, authorization or other workspace tabs.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
tasks/TASK-029-metrics-tab.md
tasks/TASK-047-derived-metrics-and-short-name-editing.md
tasks/TASK-053-metrics-predictions-filter-controls.md
tasks/TASK-056-hide-read-only-metrics-date-columns.md
docs/decisions/ADR-010-derived-metrics.md
docs/domains/ORG_STATES.md
docs/TESTING.md
```

Expected implementation areas:

- `frontend/src/features/metrics/MetricsTab.tsx`
- `frontend/src/features/metrics/MetricsTab.test.tsx`

Keep the all-date collection separate from rendered date columns, as required
by TASK-053. Reuse the same editability rule in date-column selection and cell
rendering so the two cannot diverge, and check a derived Timeserie's active
values separately when deciding whether its visible read-only data retains a
date column.

Suggested branch:

```text
fix/TASK-056-hide-read-only-metrics-date-columns
```

## Testing

Required:

- [ ] Frontend component tests for empty all-read-only columns, a derived-only
      value column, a mixed editable/read-only column, filter-driven
      recalculation, and an invalid manually added date.
- [ ] Regression test confirming hidden dates remain in row/bulk save payloads.
- [ ] Manual Metrics verification with manual and derived Timeseries, filters
      and date-range controls.
- [ ] Lint.
- [ ] Frontend test suite.
- [ ] Build and TypeScript type checking.

Not applicable:

- [ ] Backend tests: no backend behavior or contract changes.
- [ ] Integration tests: this is a local rendered-grid projection with
      component coverage.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

## Documentation

No ADR, architecture, domain, data-model, database, migration, diagram or
public API documentation update is expected. Update `docs/TESTING.md` only if
implementation introduces reusable test guidance beyond this task.

## Notes For AI Agent

- Implement only this frontend projection scope.
- Add or update tests for every changed behavior.
- Do not add dependencies.
- Preserve hidden-date save safety.
- Save each Step 13 AI-review round as a valid redacted record under
  `docs/ai-reviews/TASK-056/` according to `docs/AI-REVIEW-RECORDS.md`.
- Report changed files and verification commands run.
