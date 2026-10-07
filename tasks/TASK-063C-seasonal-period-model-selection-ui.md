# TASK-063C Seasonal Period Model Selection UI

## Source Plan

Approved plan: "Seasonal period only when seasonal-naive or SARIMA is selected".

The manual seasonal period does not affect Prophet, MLForecast, naive or
average results. Only seasonal-naive and SARIMA use it. Amended ADR-014
(TASK-063A) and the backend (TASK-063B) evaluate seasonality only when the
selection contains one of these kinds.

The developer asked that the Predictions tab show the manual period input and
the period text after preflight only when seasonal-naive and/or SARIMA is
selected. The eligibility status and reason, e.g. "ineligible — Target scenario
has no observations available under the selected cutoff.", must still be shown
where they apply.

This task depends on TASK-063B.

## Goal

The Predictions queue form only asks for, shows and sends seasonal periods when
the selected models use them. Entered periods are not lost while hidden.

## Requirements

- In `frontend/src/api/predictions.ts`, next to `MODEL_KINDS`, define the
  seasonal-period kinds `seasonal_naive` and `sarima`. Add a small helper that
  tells whether a model selection contains one of them.
- Preflight results (`PreflightResults` in
  `frontend/src/features/predictions/PredictionsTab.tsx`):
  - When the request selection contains a seasonal-period kind, behave as
    today. Show the editable manual period input, or the "Automatic seasonal
    period: N (source)" text, under TASK-062's rules.
  - Otherwise show neither the manual input nor the period text for any metric.
  - The `scenario · metric` label and the `status — reason` text are always
    shown for every metric.
- Model selection changes:
  - A change that keeps the selection in the same class does not invalidate
    preflight, as today. The classes are "contains a seasonal-period kind" and
    "contains none".
  - A change between classes invalidates preflight, like other request-field
    changes.
  - Update the comment above the Models dropdown accordingly.
- Preflight and creation requests:
  - With a seasonal-period kind selected, send `manualSeasonalPeriods` and
    apply TASK-062's keep/drop rules after preflight, as today.
  - With none selected, send `manualSeasonalPeriods: {}` and leave the entered
    periods unchanged in the open tab. Selecting seasonal-naive or SARIMA
    again restores and sends them on the next preflight.
- Creation check:
  - The check that blocks a missing or invalid (`< 2`) manual period applies
    only when a seasonal-period kind is selected.
  - The other creation checks are unchanged.

## Acceptance Criteria

- [ ] With only non-seasonal models selected (any of naive, average,
      MLForecast, Prophet), the preflight results show no manual period input
      and no "Automatic seasonal period" text.
- [ ] Every preflight row still shows its status and reason, including an
      ineligibility reason such as "Target scenario has no observations
      available under the selected cutoff.".
- [ ] With seasonal-naive alone, SARIMA alone or both selected, the input and
      period text follow TASK-062's rules.
- [ ] Switching between a selection with and one without a seasonal-period kind
      invalidates preflight. Switching within the same class does not.
- [ ] Without a seasonal-period kind, preflight and creation send
      `manualSeasonalPeriods: {}`, and creation is not blocked by a missing
      period.
- [ ] A period entered before seasonal kinds were deselected is sent again
      after SARIMA or seasonal-naive is reselected and preflight is re-run.
- [ ] The TASK-062 behaviour is unchanged with the default all-models selection.

## Out Of Scope

- Backend, API or migration changes (TASK-063B).
- Remembering manual periods across page reloads, organisations or users.
- Per-scenario manual periods.
- Changing the eligibility status or reason wording.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-014-prophet-and-model-selection.md (as amended by TASK-063A)
docs/domains/FORECASTING.md
docs/TESTING.md
tasks/TASK-062-preflight-manual-period-and-point-rounding.md
```

- These are all in `PredictionsTab.tsx`:
  - the model selection: `requestModelKinds` and the "Models"
    `MultiSelectDropdown`
  - the period state: `manualPeriods` and `usesManualSeasonalPeriod`
  - `handlePreflight`, `handleCreate`, `invalidatePreflight` and
    `PreflightResults`
- Derive "seasonal-period kind selected" from `requestModelKinds`. Because a
  class change invalidates preflight, a shown preflight always matches the
  current class, so no separate stored flag is needed.
- Do not confuse `requestModelKinds` with `selectedModelKinds`. The latter is
  the saved-results chart filter.
- No new dependencies.

## Testing

Required:

- [ ] Frontend tests in
      `frontend/src/features/predictions/PredictionsTab.test.tsx`:
  - Make the `runPreflight()` helper work when the period input is absent.
  - Update "sends only the remaining models in canonical order without
    invalidating preflight" so its selection stays in one class, e.g. Naive and
    SARIMA.
  - New tests:
    - input and period text hidden for a non-seasonal selection, with status
      and reason (including a non-period ineligible reason) still shown;
    - input shown for seasonal-naive only and for SARIMA only;
    - a class change invalidates preflight, and a same-class change does not;
    - `{}` sent and creation not blocked without a seasonal-period kind;
    - an entered period is kept while hidden and sent again after
      reselection.
  - Existing TASK-062 manual-period tests still pass.
- [ ] `frontend/src/api/predictions.test.ts`: cover the selection helper if
      it lives there.
- [ ] Manual verification at `https://app.localhost` with a metric whose
      seasonality is inconclusive:
  - Prophet only: no period input, eligible, and the queued version has
    results.
  - Add SARIMA: preflight clears; after re-running preflight, the manual
    input appears and creation requires the period.
  - A target with no observations under the cutoff shows its ineligible reason
    for both selections.
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

Update:

- `docs/TESTING.md`: add the new frontend coverage to the Predictions UI
  section.
- `docs/domains/FORECASTING.md`: only if the UI behaviour differs from what
  TASK-063A recorded.

## Notes For AI Agent

- Use the branch `feature/TASK-063C-seasonal-period-model-selection-ui`.
- Do not start until TASK-063B is merged.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-063C/`.
- Report all changed files and every verification command run.
