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

During implementation, the developer also asked that the queue form's fields
be disabled while preflight or queueing runs. Otherwise a change made while a
request is in flight, such as a Models change between selection classes, could
leave a shown preflight that no longer matches the form.

The Step 13 review (`TASK-063C/review-001`, F-001) found a pre-existing defect
that this task makes easier to reach. A manual period the backend rejects, i.e.
not a whole number of at least 2, stays in the tab after preflight is cleared.
Every later preflight then fails with a validation error, and no period input
is shown to correct it, so only a page reload recovers. The developer asked
for the fix in this task.

The second review (`TASK-063C/review-002`, F-001) found that the creation
check blocked only missing periods and periods below 2. A shown non-integer
period such as 2.5 passed it, so the user saw the backend's validation message
instead of the form's. The developer asked for this fix in this task too.

This task depends on TASK-063B.

## Goal

The Predictions queue form only asks for, shows and sends seasonal periods when
the selected models use them. Valid entered periods are not lost while hidden,
and an invalid one can never block later requests. The form cannot change
while its preflight or creation request is in flight.

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
  - With none selected, send `manualSeasonalPeriods: {}` and leave the valid
    entered periods unchanged in the open tab. Selecting seasonal-naive or SARIMA
    again restores and sends them on the next preflight.
- Creation check:
  - The check that blocks a missing or invalid manual period applies only when
    a seasonal-period kind is selected. Invalid means not a whole number of at
    least 2, the rule the backend enforces. This replaces TASK-062's `< 2`
    check, and the message reads "Enter every manual seasonal period as a whole
    number of 2 or more, or clear it and run preflight again to try automatic
    detection."
  - The other creation checks are unchanged.
- Invalid periods when preflight is cleared:
  - Whenever preflight is invalidated, for example by a request-field change
    or a Models change between classes, drop every manual period that is not
    a whole number of at least 2. No period input is shown then, so such a
    period could not be corrected and would make every later request fail.
  - Keep valid periods unchanged. A metric whose period was dropped and that
    still requires one starts again from 2, under TASK-062's rule.
  - Use the same whole-number rule as the creation check.
- Form fields while a request runs:
  - While preflight or creation is in flight, disable every queue form field:
    version name, target scenarios, start and end dates, start and end events,
    observation cutoff, prediction interval level, Models and the shown manual
    period inputs. Use the existing `submitting` state, which already disables
    the two buttons.
  - Enable them again when the request succeeds or fails.
  - The dropdowns and event selects are fieldsets, so disable them through the
    fieldset's native `disabled`. Style a disabled dropdown's summary as
    disabled, because a summary is not a form control.
  - The "Compare saved results" filters are not part of the queue form and
    stay enabled.

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
- [ ] Every queue form field, including a shown manual period input, is
      disabled while preflight or creation is in flight and enabled again after
      it succeeds or fails. The comparison filters stay enabled.
- [ ] A manual period below 2 or not a whole number is dropped when preflight
      is cleared, by a request-field change or a class change, so the next
      preflight succeeds and shows the input again from 2. Valid periods are
      kept.
- [ ] Creation is blocked, with the form's message, while a shown manual
      period is missing, below 2 or not a whole number (e.g. 2.5).

## Out Of Scope

- Backend, API or migration changes (TASK-063B).
- Remembering manual periods across page reloads, organisations or users.
- Per-scenario manual periods.
- Changing the eligibility status or reason wording.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0014-prophet-and-model-selection.md (as amended by TASK-063A)
docs/architecture/domains/FORECASTING.md
docs/operations/testing.md
docs/archive/tasks/TASK-062-preflight-manual-period-and-point-rounding.md
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
  - Update "blocks preflight and creation when no model is selected": an empty
    selection has no seasonal-period kind, so deselecting all models after a
    default all-models preflight clears it. Run preflight with a non-seasonal
    selection first, so the creation check is still covered.
  - New tests:
    - input and period text hidden for a non-seasonal selection, with status
      and reason (including a non-period ineligible reason) still shown;
    - input shown for seasonal-naive only and for SARIMA only;
    - a class change invalidates preflight, and a same-class change does not;
    - `{}` sent and creation not blocked without a seasonal-period kind;
    - an entered period is kept while hidden and sent again after
      reselection;
    - a hidden missing period does not block creation;
    - the TASK-062 creation-block test also blocks `2.5` and expects the
      updated message;
    - invalid periods (`1`, `2.5`) are dropped and valid ones kept when a
      request-field change or a class change clears preflight, and the next
      preflight succeeds;
    - the queue form fields are disabled while preflight and while creation
      are pending, and enabled again after success and after failure, with the
      comparison filters still enabled.
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
  - The form fields are disabled while preflight and queueing run.
  - Enter 1 as a manual period, change the end date and run preflight again:
    preflight succeeds and the input shows 2.
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

- `docs/operations/testing.md`: add the new frontend coverage to the Predictions UI
  section.
- `docs/architecture/domains/FORECASTING.md`: remove the "pending TASK-063C" markers, and
  state that the queue form's fields are disabled while preflight or queueing
  runs.
- `docs/adr/0014-prophet-and-model-selection.md`: mark the UI as
  implemented by TASK-063C in the status line.

## Notes For AI Agent

- Use the branch `feature/TASK-063C-seasonal-period-model-selection-ui`.
- Do not start until TASK-063B is merged.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-063C/`.
- Report all changed files and every verification command run.
