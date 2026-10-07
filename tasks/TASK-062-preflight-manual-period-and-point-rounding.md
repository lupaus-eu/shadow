# TASK-062 Preflight Manual Period And Point Rounding

## Source Plan

Developer-approved fix after the TASK-061C manual verification. Three back-to-back
local runs with identical inputs gave different results for the metric
"Some valuable thing Primary". The first and third runs used a manual seasonal
period of 2 and produced results. The second run's request snapshot had no
manual period, so the backend correctly made every result kind
`requires_manual_seasonal_period`. The model selection was not the cause.

The developer also asked for prediction point values in the charts to be shown
rounded to at most two decimals, in the same task.

## Goal

A manual seasonal period entered in the Predictions queue form must be kept
and sent for every later prediction queued from the tab, until the user changes
it. Prediction point values in the comparison charts must be easy to read.

Cause of the lost period (frontend, present since the original Predictions tab):

1. A metric with inconclusive automatic seasonality needs a manual period.
   After preflight, the form keeps a period only for metrics that preflight
   reports with `requiresManualSeasonalPeriod`.
2. After a successful queue, the form keeps its manual periods, and the next
   preflight sends them. The metric is then eligible with
   `seasonalPeriodSource: "manual"`, so it no longer requires a manual period.
3. The filter in step 1 then drops that metric's period, so the creation
   request is sent without it and the backend marks the metric ineligible.
   Every second consecutive run loses the period, and the preflight panel
   shows the metric as eligible, so the user is not warned.

## Requirements

### Manual Seasonal Period

- After preflight, keep the manual period for every metric that either requires
  one (`requiresManualSeasonalPeriod`) or already uses one
  (`seasonalPeriodSource === "manual"`). Keep using the current default of 2
  only when a required period has no value yet.
- In the preflight results, show the editable manual seasonal period input for
  both of these cases. Changing the input does not invalidate preflight, as
  today.
- Do not label a manual period as automatic. For a metric that uses a manual
  period, the row shows the editable manual input instead of the "Automatic
  seasonal period" text. Metrics with an automatic period are unchanged.
- The creation check that blocks a missing or invalid (`< 2`) manual period
  applies to both cases.
- Periods for metrics that preflight no longer lists, or that now have an
  automatic period, are dropped as today.

### Prediction Point Rounding

- In the comparison charts, show prediction point estimates and their lower and
  upper bounds rounded to at most two decimals, without adding trailing zeros.
  For example, `12.3456` shows as `12.35`, `12.3` as `12.3`, and `30` or `30.0`
  as `30`. Use `.` as the decimal separator and no thousands separator. This
  applies to the point hover text and to any other place a prediction point
  value is shown in a chart.
- This is display formatting only. Plotted positions, interval bands, API data
  and stored values are unchanged.
- Current Reality values stay as entered.

## Acceptance Criteria

- [ ] Two consecutive preflight-and-queue cycles for a metric that needs a
      manual period send the same manual period in both creation requests.
- [ ] A metric that uses a manual period shows its editable value in the
      preflight results and is not labelled as an automatic period.
- [ ] Creation is blocked when a shown manual period is missing or below 2.
- [ ] Prediction point estimates and bounds in chart hover text are rounded to
      at most two decimals without trailing zeros, and Reality hover values
      stay as entered.
- [ ] Plot geometry (line paths, dots and bands) is unchanged.

## Out Of Scope

- Backend, API or migration changes. The backend behaved correctly.
- Remembering manual periods across page reloads, organisations or users.
- Per-scenario manual periods. `manualSeasonalPeriods` stays keyed by metric,
  as the API defines.
- Rounding the chart's y-axis minimum and maximum labels or Reality values.
- Locale-aware number formatting.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-007-predictions-forecasting-domain.md (seasonal period rules)
docs/domains/FORECASTING.md
docs/TESTING.md
```

- The manual-period filter is in `handlePreflight` in
  `frontend/src/features/predictions/PredictionsTab.tsx`. The preflight row
  rendering is in `PreflightResults`, and the creation check is in
  `handleCreate`.
- The point hover text is built by `pointTitle` in `MetricChart`. Put the
  formatting in a small exported helper in `predictionChart.ts` so it can be
  unit tested.
- No new dependencies.

## Testing

Required:

- [ ] Frontend tests:
  - `PredictionsTab.test.tsx`:
    - two consecutive queue cycles keep the manual period; the second
      preflight returns the metric as eligible with a manual source;
    - the manual input is shown for a manual-source metric;
    - creation is blocked for a missing or invalid manual period;
    - rounded hover text for a point and its bounds, with Reality hover
      unchanged.
  - `predictionChart.test.ts`: the formatting helper (integers stay without
    decimals, one decimal stays one decimal, rounding to two decimals,
    negatives, and no `-0`).
  - Existing hover-text expectations such as `point estimate 30 EUR` stay
    valid; update any that use values with more than two decimals.
- [ ] Manual verification: at `https://app.localhost`, queue the same
      prediction twice in a row for a metric with inconclusive seasonality
      and confirm that both versions have results; hover chart points and
      check that values are rounded to at most two decimals without trailing
      zeros.
- [ ] Lint
- [ ] Build

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
python3 scripts/ai_review_records.py validate
```

## Documentation

- `docs/domains/FORECASTING.md`: if UI behaviour needs it, state that an entered
  manual seasonal period is kept for later requests in the open tab, and that
  chart point values are rounded to at most two decimals.
- `docs/TESTING.md`: add the new frontend coverage to the Predictions UI
  section.

## Notes For AI Agent

- Use the branch `fix/TASK-062-preflight-manual-period-and-point-rounding`.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-062/`.
- Report all changed files and every verification command run.
