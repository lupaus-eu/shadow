# TASK-053 Metrics And Predictions Filter Controls

## Source Plan

Developer-approved plan: "Metrics and Predictions UI improvement plan".

## Goal

Improve the Metrics workspace's control bar so users can limit visible metric
rows and time-value columns, select a date range, and adjust the width of
time-value cells without affecting saved data.

Improve the Predictions workspace's selection controls so long lists can be
searched, comparison filters are compact multiselect dropdowns, and prediction
form controls remain usable as the available viewport width changes.

## Requirements

### Metrics

- Replace the separate "Show manual metrics timeseries" and "Show derived
  metrics timeseries" checkboxes with one `Filter by` multiselect dropdown.
- The filter dropdown must contain Manual metrics, Derived metrics, and the
  Day, Week, Month, and Year time-unit options. All six options are selected
  by default.
- A timeserie is visible only when both its kind (manual or derived) and its
  time unit are selected.
- Add `From` and `Until` date inputs immediately to the right of the filter.
  Apply non-empty bounds inclusively to the rendered date columns.
- Keep the full, unfiltered set of active and manually added date columns for
  dirty-state calculation, next-date calculation, CSV import, and replacement
  save payloads. Narrowing the visible date range must never delete values
  outside that range when a row or all rows are saved.
- Add minus and plus buttons and a range input to the right of the `Until`
  input for adjusting only the time-value column width. Use the existing
  Metrics width of 150px as the default, named minimum/maximum bounds, and a
  consistent fixed increment for the buttons.
- Follow the Summary timeline zoom control's accessible button-and-slider
  interaction pattern. The controls must expose meaningful labels and disable
  at their respective width limits.
- Keep a 72px visual separation between the `Sort by` dropdown and the
  following add-date controls. These controls start distinct functional groups,
  so this intentional gap is larger than the standard toolbar spacing.
- Retain the existing sorting, date-column creation, saving, derived-metric,
  loading, error, and horizontal-grid-scroll behavior.

### Predictions

- Add a reusable in-dropdown search input to the Target scenarios multiselect
  and filter its option labels case-insensitively without changing selections.
- Replace the native Start event and End event selects with searchable
  single-select dropdowns. Their search inputs must appear inside the opened
  dropdown and must preserve current event-to-date synchronization and the
  strict filtering of the opposite event list.
- Turn the Saved versions selector and Compare saved results `Versions` and
  `Numeric metrics` controls into searchable multiselect dropdowns. Preserve
  the saved-version labels and metadata in the Saved versions selector.
- Keep Models and baselines as a multiselect dropdown, but do not add search
  to that control.
- Use the same selected-version state for the Saved versions and comparison
  Versions controls. On the initial successful version load, select only the
  first version in the existing display/API order; leave no version selected
  when none exist. Creating a version must retain the established behavior of
  adding the created version to the current selection.
- Remove the outer fieldset borders from the comparison Versions, Target
  scenarios, Models and baselines, and Numeric metrics controls while keeping
  visible labels and accessible grouping.
- Make controls in `section.detail-card.predictions-panel`,
  `section.predictions-preflight`, and `div.predictions-preflight__row` shrink
  and grow with their container. Date fields, search inputs, dropdown triggers,
  and manual seasonal-period inputs must not force horizontal overflow at
  narrow widths.
- Preserve loading, error, empty, chart filtering, Reality visibility,
  keyboard focus, click-outside dismissal, and Escape-dismissal behavior.

## Acceptance Criteria

- [ ] Metrics initially shows manual and derived rows of every time unit; any
      kind/time-unit filter combination limits rows as specified.
- [ ] Metrics `From`/`Until` bounds limit displayed date columns inclusively,
      and an unset bound remains open-ended.
- [ ] Saving while a Metrics date range hides existing columns preserves every
      omitted value in the API replacement payload.
- [ ] Metrics cell-width minus, slider, and plus controls update displayed
      time-value cell widths, start at 150px, and respect their limits.
- [ ] The `Sort by` dropdown and add-date controls retain their intentional
      72px visual separation.
- [ ] Target scenarios, Saved versions, comparison Versions, and Numeric
      metrics support in-dropdown case-insensitive search and retain checked
      options when a search term changes.
- [ ] Start and End event dropdowns support search while still setting their
      matching date, clearing stale opposite selections, and exposing only
      strictly valid opposite-event choices.
- [ ] Models and baselines is a working multiselect dropdown without a search
      input.
- [ ] Only the first saved version is selected after the initial load; later
      selection changes and newly created versions remain selectable.
- [ ] The four requested comparison controls have no outer borders but retain
      accessible labels and keyboard-operable dropdowns.
- [ ] Prediction controls scale within wide and narrow viewports without
      input-driven horizontal overflow.
- [ ] No dependency, backend API, schema, migration, domain rule, routing,
      authentication, authorization, or chart-rendering behavior is changed.
- [ ] Relevant frontend tests, lint, and build pass.

## Out Of Scope

- Backend filtering, API query parameters, persistence of UI filters, or any
  database migration.
- Changing metrics data ownership, timeserie validation, value editing rules,
  derived-metric calculation, CSV format, or save semantics other than
  protecting filtered-out values from accidental omission.
- Changing prediction generation, version immutability, forecasting models,
  preflight eligibility, chart algorithms, current-Reality data behavior, or
  the Analysis workspace.
- New dependencies, a general-purpose select component library, or a visual
  regression-test framework.
- Visual redesign outside the specified control layout, border removal, and
  responsive sizing corrections.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/archive/tasks/TASK-029-metrics-tab.md
docs/archive/tasks/TASK-030-summary-tab.md
docs/archive/tasks/TASK-041C-predictions-tab-ui.md
docs/archive/tasks/TASK-053-metrics-predictions-filter-controls.md
docs/adr/0007-predictions-forecasting-domain.md
docs/adr/0009-scenario-owned-prediction-inputs.md
docs/adr/0010-derived-metrics.md
docs/architecture/domains/FORECASTING.md
docs/operations/testing.md
```

Expected implementation areas:

- `frontend/src/features/metrics/MetricsTab.tsx`
- `frontend/src/features/metrics/MetricsTab.test.tsx`
- `frontend/src/features/predictions/PredictionsTab.tsx`
- `frontend/src/features/predictions/PredictionsTab.test.tsx`
- `frontend/src/styles/app.css`
- `frontend/src/styles/components.css`

- Reuse or carefully generalize the existing details-based Predictions
  multiselect behavior rather than adding a dependency. It must close on an
  outside pointer interaction and Escape, returning focus to its trigger on
  Escape.
- Keep a full Metrics date-column collection separate from the filtered list
  passed to `MetricsGrid`. Pass the complete collection to save-payload and
  dirty-row helpers.
- Define Metrics date-cell-width defaults, limits, and button increment as
  named constants. Apply the current width through a CSS custom property to
  date headers and cells only; do not resize the metric or action columns.
- Use `min-width: 0`, `minmax(0, ...)`, and width-constrained input styles
  where required by the Predictions layout. Do not rely on a fixed oversized
  minimum width for filter controls.
- Maintain the distinction between saved immutable prediction outputs and the
  optional live current-Reality layer defined by the Forecasting domain.
- If implementation requires an API, persistence, domain-rule, or architectural
  change, stop and obtain an approved task and ADR where applicable before
  proceeding.

Suggested branch:

```text
feature/TASK-053-metrics-predictions-filter-controls
```

## Testing

Required:

- [ ] Frontend tests covering Metrics filter combinations, inclusive date-range
      display, save-payload preservation of hidden columns, and every
      cell-width control.
- [ ] Frontend tests covering searchable scenario, event, version, and metric
      controls; non-searchable models/baselines; initial first-version
      selection; and existing event/date synchronization regressions.
- [ ] Manual verification of the Metrics and Predictions controls at wide and
      narrow viewport widths, including keyboard focus, Escape, outside-click
      dismissal, grid scrolling, and save behavior with a restrictive date
      range.
- [ ] Lint
- [ ] Build

Not applicable:

- [ ] Backend tests: no backend code or contract changes.
- [ ] Integration tests: no service boundary changes.
- [ ] Dedicated frontend typecheck command: the repository has no separate
      script; `pnpm build` runs `tsc -b` before the Vite build.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

## Documentation

No documentation, ADR, data-model, database, migration, or diagram update is
expected. Update `docs/operations/testing.md` only if implementation introduces reusable
frontend test guidance that is not already documented.

## Notes For AI Agent

- Read the documents listed in Implementation Notes before implementation.
- Implement only this task's frontend scope; do not alter APIs or backend code.
- Do not add dependencies.
- Add or update tests for all changed application behavior.
- Preserve off-screen Metrics values in saves; this is a data-safety invariant.
- Save each Step 13 AI-review round as a valid redacted record under
  `docs/ai-reviews/TASK-053/` according to `docs/agents/ai-review-records.md`.
- Report changed files and the verification commands run.
