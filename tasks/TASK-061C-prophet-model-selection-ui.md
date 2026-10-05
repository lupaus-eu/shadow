# TASK-061C Prophet And Model Selection UI

## Source Plan

Approved plan: "Prophet model + per-run model selection in Predictions".
This task implements the Predictions tab part of ADR-014. It depends on the
TASK-061B API.

## Goal

Let users choose which models, baselines included, run in a queued prediction.
Show Prophet results, including their prediction intervals, in the existing
comparison charts.

## Requirements

### API client

- In `frontend/src/api/predictions.ts`, add `modelKinds: string[]` to
  `PredictionRequest`.
- Export `MODEL_KINDS` in this display order: `naive`, `seasonal_naive`,
  `average`, `mlforecast`, `sarima`, `prophet`.

### Queue form

- In `PredictionsTab.tsx`, add a required "Models" `MultiSelectDropdown` to the
  "Queue a prediction" form.
- All six models are selected by default. Use the label "All models" for the
  all option.
- Send the selection with both preflight and create requests.
- Block submission and show a validation message when no model is selected.
- Changing the model selection does not invalidate a successful preflight.
  Eligibility does not depend on models, and under ADR-014's 110,000-point
  limit no valid selection can exceed the point limit.
- If creation is rejected with a validation error (for example a limit), show
  the server's safe error message in the form, using the existing form-error
  pattern.

### Charts

- Draw an interval band whenever a result's `predictionIntervalStatus` is
  `available`, instead of checking a hard-coded `mlforecast`/`sarima` kind list.
- Give Prophet its own line style in `predictionChart.ts`.
- Have `formatModelKind` use a label map: "Naive", "Seasonal naive", "Average",
  "MLForecast", "SARIMA", "Prophet". Unknown kinds fall back to the current
  formatting.

### Saved versions

- Show which models each saved version ran, read from
  `modelConfiguration.modelKinds`.
- For older versions without that field, fall back to the kinds present in the
  version's results.

## Acceptance Criteria

- [ ] The queue form shows all six models selected by default, and the request
      body contains all six.
- [ ] Deselecting models sends only the remaining kinds.
- [ ] Submission is blocked when no model is selected.
- [ ] A create-time validation error is shown to the user.
- [ ] Prophet results appear in the "Models and baselines" comparison filter
      and the charts, with an interval band when one is available.
- [ ] Versions that ran a subset show only their models, and the chart's
      "No results to show for" note stays correct.
- [ ] Model labels use the label map.

## Out Of Scope

- Backend or migration changes.
- Remembering the model selection between sessions or per user.
- A results table or display of cross-validation MAE.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-014-prophet-and-model-selection.md
docs/domains/FORECASTING.md
docs/TESTING.md
```

- Reuse the existing `MultiSelectDropdown`, `toggleSet` and form validation
  patterns in `PredictionsTab.tsx`. Do not add a new component library.
- No new frontend dependencies.

## Testing

Required:

- [ ] Frontend tests:
  - `PredictionsTab.test.tsx`: default request, subset request, validation
    with none selected, Prophet band
  - `predictionChart.test.ts`: label map
  - `api/predictions.test.ts`: request body
- [ ] Manual verification: locally at `https://app.localhost` with the worker
      running, queue a run with all models and a run with only `naive` and
      `prophet`, then compare them
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

Update `docs/domains/FORECASTING.md` only if UI behavior needs clarifying.

## Notes For AI Agent

- Do not start until TASK-061B's API is available.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-061C/`.
- Report all changed files and every verification command run.
