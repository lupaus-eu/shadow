# TASK-055 Prediction Chart Readability And Reality Comparison

## Source Plan

Developer-approved plan: "Predictions chart readability and Reality comparison".

## Goal

Keep dense prediction comparisons readable and show live Reality within the
selected forecasts' period by default. The reported missing Reality line was
not reproduced with out-of-range data; cover actual SVG rendering with regressions.

## Requirements

- Cap evenly spaced date labels at 22 with at least 36 SVG units between them;
  retain endpoints, all plotted points and independent year-boundary guides.
  Suppress colliding year captions.
- At 100 displayed points per line, hide dots but retain invisible hover targets,
  complete lines, interval bands and existing point details. Apply to Reality too.
- Put the unit inside the white SVG area at the upper left, above the plot.
- Derive each metric's default inclusive bounds from selected versions containing
  that metric in selected scenarios. Explicit plot bounds override each side.
  Apply the resulting range to both prediction and Reality points.
- After a successful Reality load, explain missing matching numeric series and
  empty displayed observations per chart. Preserve stable metric-ID matching.

## Acceptance Criteria

- [ ] Dense date and year labels do not overlap; endpoints remain visible.
- [ ] Lines independently switch dots off at 100 filtered points.
- [ ] Units are inside the graph without colliding with plot content.
- [ ] Reality outside the default forecast period is excluded, while explicit
      bounds can expand it; plotted Reality is covered by regression tests.
- [ ] Loading and errors do not produce misleading empty-Reality messages.
- [ ] Frontend checks pass and AI review is recorded.

## Out Of Scope

Backend, public API, database, architecture, new dependencies, other workspace
charts, prediction generation and production deployment.

## Implementation Notes

Reuse PredictionsTab, predictionChart helpers and existing SVG styles. Follow
ADR-009's scenario isolation and ADR-011's interval rendering contract. Relevant
domain references: `docs/domains/FORECASTING.md`, `docs/domains/ORG_STATES.md`.

## Testing

Required: helper/component regressions, frontend lint/tests/build, visual review
at desktop and narrow widths. See `docs/TESTING.md` for the QA checklist.

Cover 0/1/22/23/100/365 dates and multiple years; 99/100/101 points, mixed
density and filtering; unit placement and interval tooltips; Reality before,
within and after forecasts, multiple versions, single-bound overrides, empty
data, request states and checkbox toggling. Assert SVG paths and coordinates.

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Backend tests are not applicable: no backend code changes.

## Documentation

Document comparison behavior, visual QA and verification results. Store the
committed-diff AI review under `docs/ai-reviews/TASK-055/` following
`docs/AI-REVIEW-RECORDS.md`.

## Verification Results

2026-09-07:

- `pnpm --config.verify-deps-before-run=false lint`: passed.
- `pnpm --config.verify-deps-before-run=false test`: 18 files, 217 tests passed.
  One earlier concurrent run failed an unchanged Customers timing test; the
  full rerun passed without changing Customers code or tests.
- `pnpm --config.verify-deps-before-run=false build`: TypeScript and Vite passed.
  The flag uses installed dependencies because the local pnpm pre-run automatic
  install encountered an unrelated ignored tree-sitter build script. No
  dependencies or build-script approvals were changed.
- Headless Chromium rendered the actual MetricChart implementation and repository
  CSS with synthetic 23/100/365-point prediction and Reality series at 1280px and
  390px viewport widths. Screenshots were inspected; bounding-box checks found
  no date/year caption collisions and confirmed units inside the SVG. Dense
  series had only transparent hover targets; sparse series retained dots.
- Browser verification used isolated chart fixtures, not a live authenticated
  backend. Checkbox, date overrides, hover-title content, request failures and
  cancellation were verified by component tests.
