# TASK-054A Prediction Intervals Architecture

## Source Plan

Approved plan: "Prediction Intervals for Forecasts", amended so the selectable
integer prediction-interval level defaults to 80 percent.

This is the first task in the prediction-interval sequence. TASK-054B and
TASK-054C depend on the decision and Forecasting Domain rules established here.

## Goal

Define the statistical meaning, supported result kinds, persistence semantics
and failure behavior for user-selected prediction intervals before changing
the Forecasting schema, backend API or Predictions UI.

The documentation must use the statistically accurate term "prediction
interval": a range for a future observed value, rather than a confidence
interval around an estimated mean.

## Requirements

- Create and accept `docs/adr/0011-prediction-intervals.md` based on
  the developer-approved plan.
- Define one version-wide integer prediction-interval level from 50 through 99
  percent, with 80 percent as the default.
- Define central, two-sided intervals for directly fitted normal-metric
  results only:
  - MLForecast uses its built-in conformal-error interval implementation with
    three one-step calibration windows (`n_windows=3`, `h=1`); the resulting
    interval width is constant across the forecast horizon.
  - SARIMA uses Statsmodels' native forecast interval with
    `alpha = 1 - confidence_level / 100`.
- Define naive, seasonal-naive, average, live Reality and formula-derived
  result intervals as not applicable. Point forecasts remain unchanged for
  these outputs.
- Define per-result interval states `available`, `unavailable` and
  `not_applicable`, including a user-safe reason for an unavailable interval.
- Define that an expected calibration or bound-validation failure preserves a
  valid point forecast and marks only its interval unavailable. Existing
  whole-version rollback behavior remains in force for unexpected generation
  failures.
- Require a complete interval for a result: every generated point has finite,
  ordered lower and upper bounds containing its point estimate, or the entire
  result interval is unavailable.
- Do not clip negative bounds because current numeric metrics have no
  non-negative domain invariant.
- Record the approved data assumption that no prediction data exists in
  production. The schema migration may discard existing development prediction
  versions instead of backfilling confidence levels, interval states or bounds;
  no legacy prediction read or display path is required.
- State that the percentage is nominal coverage, not a guaranteed observed
  coverage rate, and that no new dependency, worker, queue or prediction-work
  limit is introduced.
- Update the Forecasting summary in `docs/architecture/overview.md`, the Forecasting Domain
  rules and relevant ADR cross-references to make the accepted decision the
  implementation source of truth.

## Acceptance Criteria

- [ ] ADR-011 records the selected interval type, 50--99 integer range,
      80-percent default, supported models and exact model-specific methods.
- [ ] The accepted documentation distinguishes prediction intervals from
      confidence intervals around a mean and avoids promising guaranteed
      coverage.
- [ ] MLForecast and SARIMA interval semantics are explicit, including the
      MLForecast one-step calibration and horizon-constant width.
- [ ] Baseline, live Reality and formula-derived outputs are explicitly
      outside interval calculation while retaining their existing point data.
- [ ] Available, unavailable and not-applicable states, validation invariants,
      expected failures and unexpected rollback behavior are unambiguous.
- [ ] The no-production-prediction-data assumption, permitted development-data
      reset and absence of bound clipping are documented.
- [ ] TASK-054B and TASK-054C can implement the decision without making a new
      architecture or statistical-method choice.
- [ ] No application code, migration, ORM model, API schema, frontend source or
      generated diagram is changed.

## Out Of Scope

- SQL migrations, database constraints and SQLAlchemy model changes.
- Backend interval calculation, API contract changes or persistence.
- Frontend input controls, DTOs, chart bands or styling.
- Intervals for baselines or uncertainty propagation through derived formulas.
- Preservation, backfill or UI compatibility for prediction versions created
  before this feature.
- Asymmetric intervals, simultaneous intervals, empirical coverage reporting,
  model selection or model-algorithm changes unrelated to intervals.
- New dependencies, background jobs, queues, retries or monitoring services.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0007-predictions-forecasting-domain.md
docs/adr/0009-scenario-owned-prediction-inputs.md
docs/adr/0010-derived-metrics.md
docs/architecture/domains/FORECASTING.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
docs/operations/testing.md
docs/archive/tasks/TASK-054A-prediction-intervals-architecture.md
```

- Treat the approved plan as the human architecture decision and record it in
  ADR-011 before TASK-054B begins.
- Keep this task documentation-only. Physical data documentation and diagrams
  are updated with the implemented schema in TASK-054B.
- Preserve ADR-007's five result kinds, immutable version lifecycle,
  synchronous execution and failure boundary.

## Testing

Required:

- [ ] Manual verification
- [ ] AI review record

Not applicable:

- [ ] Frontend tests: no frontend code changes.
- [ ] Backend tests: no backend code changes.
- [ ] Integration tests: no runtime or schema changes.
- [ ] Lint: no repository Markdown lint command is configured.
- [ ] Build: no build inputs change.
- [ ] Typecheck: no typed source changes.

Manual verification must confirm that links resolve, terminology and formulas
are internally consistent, and the follow-up tasks require no unstated
statistical or lifecycle decision.

After implementation review, save the required redacted Step 13 record under
`docs/ai-reviews/TASK-054A/` and validate the review-record archive.

## Documentation

Update:

- `docs/adr/0011-prediction-intervals.md`
- `docs/adr/0007-predictions-forecasting-domain.md` for the extension
  cross-reference
- `docs/architecture/domains/FORECASTING.md`
- `docs/architecture/overview.md`

## Notes For AI Agent

- Implement only this documentation scope.
- Do not begin TASK-054B or TASK-054C in this task.
- Do not add code, migrations, dependencies or generated artifacts.
- Report the documents changed and the checks performed.
