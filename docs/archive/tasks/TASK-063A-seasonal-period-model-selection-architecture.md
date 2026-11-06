# TASK-063A Seasonal Period Model Selection Architecture

## Source Plan

Approved plan: "Seasonal period only when seasonal-naive or SARIMA is selected".

Only `seasonal_naive` and `sarima` use the seasonal period. Prophet uses fixed
seasonality per time unit (ADR-014), and naive, average and MLForecast do not
use the period at all. Yet today a metric whose automatic seasonality is
inconclusive is not eligible until a manual period is supplied, even when only
Prophet or the simple baselines are selected. In that case every selected result
kind is stored as `ineligible`. The Predictions tab also always shows the manual
period input and the "Automatic seasonal period" text after preflight.

Developer decisions recorded with the plan:

- Eligibility stays target-level, but it becomes selection-aware.
  Seasonality is evaluated only when the request's `modelKinds` contains
  `seasonal_naive` or `sarima`.
- Per-kind eligibility, already rejected in ADR-014, stays rejected.
- The UI shows the manual period input and the period text only when
  seasonal-naive and/or SARIMA is selected.
- The eligibility status and reason stay visible for every metric. For example,
  "ineligible — Target scenario has no observations available under the
  selected cutoff." is still shown where it applies.

This is the first task in the sequence. TASK-063B and TASK-063C depend on the
decision recorded here.

## Goal

Amend ADR-014 so that seasonal-period detection and the manual-period
requirement apply only when the selection contains a kind that uses the period.
Align ADR-007 and `docs/architecture/domains/FORECASTING.md` with the amended rule before any
backend or UI change.

## Requirements

- Amend `docs/adr/0014-prophet-and-model-selection.md`:
  - Define the seasonal-period result kinds as `seasonal_naive` and `sarima`.
  - When the selection contains at least one seasonal-period kind, the
    existing rules apply unchanged:
    - Automatic detection runs.
    - A sent manual period overrides detection.
    - Inconclusive detection without a manual period makes the target
      `requires_manual_seasonal_period`, so every selected kind is
      `ineligible`.
  - When the selection contains no seasonal-period kind:
    - Seasonality is not evaluated.
    - The target is `eligible` with null `seasonalPeriod` and
      `seasonalPeriodSource`, unless it is ineligible for another reason.
    - Any sent manual period for it is ignored and is not recorded as the
      target's period.
    - Earlier ineligibility checks are unchanged: no observations under the
      cutoff, the history limit, contiguity, and derived-metric rules.
  - Rewrite the Prophet eligibility paragraph (currently "Target-level
    eligibility is unchanged …"). Prophet needs a period only when it is
    selected together with a seasonal-period kind.
  - Rewrite the work-limit paragraph (currently "Eligibility does not depend on
    the selection …"):
    - Eligibility now depends on whether the selection contains a
      seasonal-period kind.
    - A passed preflight stays valid when the selection changes within the
      same class: still with, or still without, a seasonal-period kind.
    - A change between classes requires a new preflight.
    - The raised `MAX_POINTS` still admits every valid request, even though
      more targets can be eligible for a non-seasonal selection.
    - Creation remains authoritative.
  - Under "Per-Kind Eligibility For Prophet Without A Seasonal Period", add why
    the selection-aware variant was chosen instead. It keeps target-level
    eligibility, and needs no new snapshot shape, result status or migration.
  - Record that legacy snapshots without `modelKinds` calculate the legacy
    five kinds. These include seasonal-period kinds, so their behaviour does not
    change.
  - Record the UI consequence:
    - The manual period input and period text are shown only for a
      seasonal-period selection.
    - Entered periods are kept in the open tab while hidden.
    - Hidden periods are not sent.
- Amend `docs/adr/0007-predictions-forecasting-domain.md`:
  - Mark the seasonality paragraph "Amended by ADR-014".
  - Correct its wording to target-level, selection-aware eligibility. Today it
    says only seasonal-naive and SARIMA stay ineligible.
- Update `docs/architecture/domains/FORECASTING.md`, in the seasonality and Predictions-tab
  paragraphs and the Prophet bullet:
  - Describe the selection-aware rule and the conditional UI.
  - Keep the TASK-062 rules for a shown period: it is kept, sent, blocks
    creation when missing or below 2, and is dropped after preflight.

## Acceptance Criteria

- [ ] ADR-014 defines the seasonal-period kinds and the eligibility rule both
      with and without one in the selection, including that a sent manual
      period is ignored without one.
- [ ] ADR-014 states when a passed preflight stays valid after a model-selection
      change and when a new preflight is required.
- [ ] ADR-014 records why this was chosen over the rejected per-kind option, and
      that legacy snapshots are unaffected.
- [ ] ADR-007 and `FORECASTING.md` are consistent with amended ADR-014.
- [ ] TASK-063B and TASK-063C can be implemented without a new architecture
      choice.
- [ ] No application code, migration, API schema or frontend source is changed.

## Out Of Scope

- Any code, schema or migration change.
- Per-kind eligibility, or new result or eligibility statuses.
- Changing how seasonality is detected, or which kinds use the period.
- Remembering manual periods across page reloads.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0007-predictions-forecasting-domain.md
docs/adr/0014-prophet-and-model-selection.md
docs/architecture/domains/FORECASTING.md
docs/archive/tasks/TASK-062-preflight-manual-period-and-point-rounding.md
```

Current code anchors that the amendment describes:

- `backend/app/api/v1/predictions/service.py`:
  - `_seasonal_period` and the `requires_manual_seasonal_period` return in
    target preparation
  - `_calculate_normal_result_set`
- `frontend/src/features/predictions/PredictionsTab.tsx`: `PreflightResults`,
  `handlePreflight`, `handleCreate`

The DB column `prediction_targets.seasonal_period` and the snapshot fields are
already nullable, so no data-model change is expected. Check this and state it
in the ADR.

`docs/architecture/overview.md` does not describe the seasonal-period rule. Update it only if
the review finds a conflicting statement.

## Testing

Required:

- [ ] Manual verification (documentation consistency review)
- [ ] AI review record

Not applicable:

- [x] Reason: documentation-only task; there are no application tests.

```bash
python3 scripts/ai_review_records.py validate
```

## Documentation

Update:

- `docs/adr/0014-prophet-and-model-selection.md`
- `docs/adr/0007-predictions-forecasting-domain.md`
- `docs/architecture/domains/FORECASTING.md`
- `AGENTS.md` and `docs/architecture/overview.md`, only if a conflicting statement is found

## Notes For AI Agent

- Use the branch `docs/TASK-063A-seasonal-period-model-selection-architecture`.
- Do not change code in this task.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-063A/`.
- Report all changed files and every verification command run.
