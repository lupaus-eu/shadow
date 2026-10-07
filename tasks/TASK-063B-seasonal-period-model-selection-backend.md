# TASK-063B Seasonal Period Model Selection Backend

## Source Plan

Approved plan: "Seasonal period only when seasonal-naive or SARIMA is selected".
Amended ADR-014 (TASK-063A) records the rule:

- Seasonality is evaluated only when the request's `modelKinds` contains
  `seasonal_naive` or `sarima`.
- Otherwise the target is eligible with no seasonal period, and any sent
  manual period is ignored.

This task depends on TASK-063A. TASK-063C depends on this task.

## Goal

Make backend preflight and creation apply the seasonal-period requirement only
to selections that contain a kind that uses the period. A Prophet-only or
baseline-only request for a metric with inconclusive seasonality then produces
results instead of being stored as ineligible.

## Requirements

- In `backend/app/api/v1/predictions/snapshots.py`, define the seasonal-period
  result kinds `seasonal_naive` and `sarima` as one shared constant next to
  `RESULT_KINDS`. Use the style of the existing kind constants.
- In target preparation in `backend/app/api/v1/predictions/service.py`, at the
  `_seasonal_period(...)` call and the `requires_manual_seasonal_period`
  return:
  - When `payload.model_kinds` contains a seasonal-period kind, behave exactly
    as today.
  - Otherwise do not call `_seasonal_period` and do not read the manual period.
    Prepare the target as `eligible` with `seasonal_period=None` and
    `seasonal_period_source=None`.
- The following stay unchanged for every selection:
  - Earlier ineligibility checks and reasons: no observations under the
    cutoff, the history limit, contiguity.
  - The derived-target handling.
- Preflight and creation use the same rule, so preflight is consistent with the
  frozen snapshot.
- Preflight for a non-seasonal selection reports:
  - `requiresManualSeasonalPeriod: false`
  - null `seasonalPeriod` and `seasonalPeriodSource`
- The persisted target and the snapshot record a null period for a
  non-seasonal selection.
- Worker calculation, legacy snapshots without `modelKinds`, the point limit,
  the API schemas and the DB schema stay unchanged.

## Acceptance Criteria

- [ ] On inconclusive history, preflight with
      `modelKinds: ["naive", "average", "mlforecast", "prophet"]` returns
      `eligible`, null period and source, and
      `requiresManualSeasonalPeriod: false`.
- [ ] A manual period sent with a non-seasonal selection is ignored. The period
      and source stay null in preflight and in the persisted target.
- [ ] On inconclusive history without a manual period, `["seasonal_naive"]`
      alone and `["sarima"]` alone still return
      `requires_manual_seasonal_period` with the existing reason.
- [ ] A created non-seasonal version for that target calculates `available`
      results for the selected kinds.
- [ ] An ineligibility reason unrelated to the period, such as "Target scenario
      has no observations available under the selected cutoff.", is unchanged
      for both seasonal and non-seasonal selections.
- [ ] The existing seasonal-period, SARIMA and legacy-snapshot tests still pass.

## Out Of Scope

- UI changes (TASK-063C).
- API schema, migration, ORM model or snapshot-format changes.
- Changing seasonality detection or how seasonal-naive or SARIMA use the period.
- Per-kind eligibility.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-007-predictions-forecasting-domain.md
docs/decisions/ADR-014-prophet-and-model-selection.md (as amended by TASK-063A)
docs/domains/FORECASTING.md
docs/TESTING.md
```

- `prediction_targets.seasonal_period` and `seasonal_period_source` are
  nullable (`db/migrations/010_create_prediction_schema.sql`). The
  `PredictionTargetSnapshot` fields are also nullable, and its validator does
  not require a period for an eligible target.
- The seasonal-naive generator uses `row.seasonal_period or 1`, and SARIMA reads
  the period. Neither runs for a non-seasonal selection.
- Keep the change small. A helper such as
  `uses_seasonal_period(model_kinds)` is enough. No new dependencies.

## Testing

Required:

- [ ] Backend tests in `backend/tests/test_predictions_api.py`, next to the
      existing inconclusive-seasonality test (`requires_manual_seasonal_period`):
  - non-seasonal selection preflight: eligible with a null period;
  - non-seasonal selection with a sent manual period: still null;
  - `seasonal_naive`-only and `sarima`-only selections still require a manual
    period;
  - non-seasonal creation and calculation: `available` results;
  - a no-observations target keeps its reason for both selection classes.
- [ ] Lint
- [ ] Typecheck

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
python3 scripts/ai_review_records.py validate
```

## Documentation

Update:

- `docs/TESTING.md`: add the new backend coverage to the Forecasting section.
- `docs/domains/FORECASTING.md`: only if implementation details need
  clarifying beyond TASK-063A.

## Notes For AI Agent

- Use the branch `feature/TASK-063B-seasonal-period-model-selection-backend`.
- Do not start until TASK-063A and the ADR-014 amendment are accepted.
- Do not implement TASK-063C's UI in this task.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-063B/`.
- Report all changed files and every verification command run.
