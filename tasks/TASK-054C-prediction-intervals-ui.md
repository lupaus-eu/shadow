# TASK-054C Prediction Interval Selection And Charts

## Source Plan

Approved plan: "Prediction Intervals for Forecasts", amended so the selectable
integer prediction-interval level defaults to 80 percent.

Dependency: TASK-054B Prediction Intervals Backend And Persistence must be
completed and its API contract accepted before this task is implemented.

## Goal

Let a user choose a prediction-interval level before preflight and prediction
creation, then clearly display the saved MLForecast and SARIMA uncertainty
bands when comparing immutable prediction versions.

Keep valid point forecasts visible when their interval is unavailable and keep
baseline, formula-derived and live Reality series visually distinct as
unbanded lines.

## Requirements

### API client and generation form

- Extend the frontend prediction request DTO with required
  `confidenceLevel: number` and extend list/detail DTOs with required
  `confidenceLevel`.
- Extend result DTOs with `predictionIntervalStatus` and nullable
  `predictionIntervalReason`; extend point DTOs with nullable `lowerBound` and
  `upperBound`.
- Add an accessible required whole-number percentage input to the prediction
  generation settings, with a visible 50--99 range and an 80-percent default.
- Explain that the selection is a nominal prediction interval for future
  observed values and that higher percentages generally produce wider bands.
  Do not label it as guaranteed coverage or as a confidence interval around a
  mean.
- Validate blank, fractional and out-of-range input before preflight or create.
- Include the selected `confidenceLevel` in both preflight and create payloads.
- Changing the level after preflight must invalidate the preflight, matching
  other generation inputs; creation remains available only after a fresh valid
  preflight.
- Preserve the selected level after successful creation while resetting the
  existing version-name and preflight state as currently designed.

### Saved-version comparison and charts

- Identify each saved version's selected interval level in the version
  comparison option and prediction provenance.
- Carry complete lower/upper bound pairs through date and selection filtering
  in the prediction chart-data helper.
- Include available lower and upper bounds in each metric chart's Y-axis domain
  so interval bands are never clipped by point-only scaling.
- Render an available MLForecast or SARIMA interval behind its point line as a
  closed, translucent SVG band using the line's color. Draw bands before lines
  and points so point estimates and overlapping versions remain identifiable.
- Include the date, point estimate, lower bound, upper bound, unit and saved
  interval level in the relevant accessible SVG title/tooltip content.
- Keep naive, seasonal-naive, average, formula-derived, live Reality and
  interval-unavailable results as ordinary lines with no band.
- When an MLForecast or SARIMA point result has
  `predictionIntervalStatus="unavailable"`, keep its line visible and include
  the safe backend reason in legend/provenance text.
- Ensure legend/provenance text identifies the interval level and distinguishes
  saved prediction intervals from manually entered live Reality values.
- Reuse the current in-repository SVG chart and CSS patterns. Add no charting or
  other frontend dependency.

## Acceptance Criteria

- [ ] The generation form initially displays 80 and accepts only whole numbers
      from 50 through 99.
- [ ] Invalid confidence-level input blocks preflight and creation with an
      accessible message.
- [ ] Preflight and create requests always contain the visible selected level,
      and changing it invalidates stale preflight results.
- [ ] Saved-version choices and provenance display each version's selected
      interval level.
- [ ] Available MLForecast and SARIMA bounds render as translucent bands behind
      their corresponding point lines.
- [ ] Chart Y-axis scaling includes lower and upper bounds, and tooltip/title
      content exposes point and bound values with the correct level and unit.
- [ ] Baselines, formula-derived results, live Reality and
      interval-unavailable fitted results render without bands.
- [ ] An unavailable interval does not hide its valid point forecast, and its
      safe reason is visible in provenance.
- [ ] Multiple versions with different interval levels and overlapping bands
      remain individually identifiable.
- [ ] Existing date, version, scenario, model, metric and Reality filters keep
      their current behavior.
- [ ] Frontend lint, tests and production build pass without a new dependency.
- [ ] No backend, migration, modelling algorithm or Analysis workspace change
      is included.

## Out Of Scope

- Backend schemas, interval generation, persistence or migrations.
- Prediction intervals for naive, seasonal-naive, average, formula-derived or
  live Reality values.
- User-selectable interval visibility, multiple levels within one version,
  asymmetric bands, coverage analytics or interval export.
- Replacing the existing SVG chart, adding a charting dependency or changing
  the Analysis workspace.
- Background generation progress, polling, scheduling, retries or deletion of
  saved versions.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-007-predictions-forecasting-domain.md
docs/decisions/ADR-011-prediction-intervals.md
docs/domains/FORECASTING.md
docs/TESTING.md
tasks/TASK-054B-prediction-intervals-backend.md
tasks/TASK-054C-prediction-intervals-ui.md
```

- Update the existing typed client in `frontend/src/api/predictions.ts` and the
  existing Predictions form/chart components rather than adding a parallel
  data path.
- Build the band path from upper points in chronological order and lower points
  in reverse order, closing the SVG path. Render no partial band if any visible
  point lacks either bound.
- Assign one color consistently to a line and its band. Use restrained opacity
  and retain existing dash patterns for point lines.
- Treat every saved version's level as required. Point bounds remain nullable
  because not-applicable and unavailable result intervals intentionally have no
  band.
- Use backend-provided interval status and reason rather than inferring model
  failure from absent bounds alone.

## Testing

Required:

- [ ] Frontend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] AI review record

Not applicable:

- [ ] Backend tests: backend behavior belongs to TASK-054B.
- [ ] Backend integration tests: no schema or backend change is made here.
- [ ] Backend typecheck: no backend source changes are expected.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Frontend tests must cover the 80-percent initial value, integer/range
validation, preflight invalidation, preflight/create payloads,
bounds-preserving filters, bounds-aware Y scaling, SVG band path construction,
interval tooltip/provenance text and unbanded unavailable or not-applicable
series.

Manual verification must create otherwise comparable versions at two interval
levels, select them together, confirm that their saved levels and bands are
distinguishable, and verify that baseline and Reality lines remain unbanded.

After implementation review, save the required redacted Step 13 record under
`docs/ai-reviews/TASK-054C/` and run:

```bash
python3 scripts/ai_review_records.py validate
```

## Documentation

Update only if implementation requires reusable UI guidance:

- `docs/TESTING.md`
- user-facing Predictions documentation, if one exists at implementation time

ADR, domain, data-model and database documentation belong to TASK-054A and
TASK-054B and must not be redefined here.

## Notes For AI Agent

- Implement only after TASK-054B's API contract exists.
- Preserve all existing Predictions comparison filters and the Analysis route.
- Add no dependency and do not alter backend or migration files.
- Add tests for every changed UI behavior and report all checks run.
