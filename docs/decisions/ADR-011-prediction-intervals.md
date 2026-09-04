# ADR-011: Prediction Intervals

Status: Accepted

Date: 2026-09-04

---

# Context

Forecasting currently saves deterministic point predictions for five result
kinds. Point values do not communicate how uncertain a fitted model is, so a
user comparing prediction versions cannot see the range of future observed
values that a model considers plausible.

The required uncertainty range is a prediction interval for a future observed
value. It is not a confidence interval around an estimated mean. The interval
must remain auditable as part of an immutable prediction version, must not turn
baseline or formula-derived values into unsupported probabilistic claims, and
must preserve useful point predictions when interval calculation has an
expected limitation.

# Decision

## Version-Level Selection

Each new prediction version has one user-selected integer prediction-interval
level from 50 through 99 percent. The default is 80 percent. The selection is
made before preflight and creation, applies to every supported result in the
version and is persisted with the immutable version and modelling
configuration.

The selected percentage is nominal coverage, not a guarantee that the same
percentage of future observations will fall inside the saved bounds. Higher
levels generally produce wider intervals.

## Supported Results And Methods

Forecasting generates central, two-sided prediction intervals only for
directly fitted normal-metric results:

- `mlforecast` uses MLForecast's built-in conformal-error interval method with
  three one-step calibration windows (`n_windows=3`, `h=1`) and the selected
  level. One-step calibration makes the interval width constant across the
  generated forecast horizon.
- `sarima` uses the fitted Statsmodels forecast result's native interval with
  `alpha = 1 - confidence_level / 100`.

The `naive`, `seasonal_naive` and `average` baselines remain point forecasts.
Live manually entered Reality data is observed comparison data and has no
prediction interval. Formula-derived results remain point-only even when their
result-kind name is `mlforecast` or `sarima`: Forecasting does not propagate
source bounds through an equation or fit the derived metric independently.

No prediction-interval method clips negative bounds. Current numeric metrics
have no domain invariant that requires non-negative values.

## Interval States And Validation

Each saved model result records one interval state:

- `available`: every generated point has a lower and upper bound;
- `unavailable`: a directly fitted result has no complete requested interval,
  either because its point result is ineligible or because interval calculation
  or validation failed, with a user-safe reason; or
- `not_applicable`: the result is a baseline or formula-derived output for which
  this decision defines no interval.

An available interval is complete across the result. Every lower and upper
bound must be finite and ordered so that
`lower_bound <= point_value <= upper_bound`. Forecasting never saves a partial
set of bounds for a result.

An expected calibration, interval-extraction or bound-validation failure keeps
otherwise valid point predictions and records the interval as `unavailable`.
A directly fitted point-model failure retains the existing model-ineligibility
behavior and also records its requested interval as `unavailable`, using the
safe model reason. An unexpected generation failure retains ADR-007's
transaction boundary: the entire prediction version is rolled back.

## Data And Execution Boundary

There is no prediction data in production when this decision is accepted.
Implementation may discard existing development prediction versions in the
paired schema migration instead of backfilling confidence levels, interval
states or bounds. No legacy prediction read or display behavior is required.

The interval feature reuses the accepted MLForecast and Statsmodels
dependencies. It does not introduce a new dependency, result kind, worker,
queue, retry protocol or monitoring service. Bounds are attributes of existing
prediction points, so ADR-007's candidate, history, period and persisted-point
limits remain unchanged.

# Options Considered

## Confidence Interval Around The Mean

Rejected. It describes uncertainty in an estimated mean rather than the range
of a future observed value and is narrower than the uncertainty the user needs
when comparing predictions.

## Intervals For Every Result Kind

Rejected. Baselines are retained as simple comparison points, and propagating
uncertainty through arbitrary derived formulas requires distribution and
dependency assumptions that the current domain does not define.

## One Uniform Interval Algorithm

Rejected. MLForecast already provides conformal prediction intervals and
Statsmodels provides an interval from the fitted SARIMA result. Using the
model-specific supported methods avoids introducing a separate uncertainty
model.

## Discard A Point Forecast When Its Interval Is Unavailable

Rejected. A handled interval limitation does not invalidate an otherwise useful
point forecast. The explicit interval state keeps the limitation visible
without hiding the point result or aborting unrelated results.

## Preserve Existing Development Prediction Versions

Rejected. No prediction data exists in production, and development prediction
versions are disposable. Resetting them avoids nullable version metadata,
fabricated bounds and a permanent legacy display path.

# Consequences

Benefits:

- users can select the uncertainty level appropriate to a prediction version;
- supported fitted-model charts can communicate both central predictions and
  uncertainty;
- saved method, level, state and bounds keep the result auditable;
- baseline and formula-derived outputs do not imply unsupported probabilistic
  semantics; and
- expected interval limitations do not erase useful point forecasts.

Costs and constraints:

- MLForecast's one-step conformal calibration produces horizon-constant interval
  widths;
- nominal coverage can differ from observed coverage, especially with limited
  or shifting history;
- different fitted models use different accepted interval methods;
- formula-derived and baseline results have no uncertainty bands; and
- the schema migration discards existing development prediction versions.

# Implementation Rules

- TASK-054B must add the version level, per-result interval state/reason and
  per-point bounds through a paired repository-owned migration.
- TASK-054B must validate complete finite bounds without clipping and preserve
  valid point results on expected interval failure.
- TASK-054C must require a visible level selection before preflight and creation
  and render only available bounds as prediction bands.
- The UI must call these ranges prediction intervals and must not claim
  guaranteed coverage.
- Do not add dependencies, result kinds, background execution or intervals for
  baselines, live Reality or formula-derived results in this work.

# References

- `docs/decisions/ADR-007-predictions-forecasting-domain.md`
- `docs/decisions/ADR-009-scenario-owned-prediction-inputs.md`
- `docs/decisions/ADR-010-derived-metrics.md`
- `docs/domains/FORECASTING.md`
- `tasks/TASK-054A-prediction-intervals-architecture.md`
- `tasks/TASK-054B-prediction-intervals-backend.md`
- `tasks/TASK-054C-prediction-intervals-ui.md`
