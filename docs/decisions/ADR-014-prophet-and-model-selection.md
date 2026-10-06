# ADR-014: Prophet Result Kind And Per-Version Model Selection

Status: Accepted; TASK-061B implemented; TASK-061C pending

Date: 2026-10-05

---

# Context

Forecasting attempts and persists five result kinds for every eligible target
metric (ADR-007): `naive`, `seasonal_naive`, `average`, `mlforecast` and
`sarima`. Users want to compare a further widely used decomposable time-series
model, Meta's Prophet, against the existing models and baselines.

Every version currently fits every model. A user who only wants to compare a
few methods still waits for, and stores, all of them. Prophet is more expensive
to fit than the baselines, so adding it without a selection would make every
queued request slower.

ADR-007 makes the five result kinds authoritative, and ADR-011 and ADR-012
explicitly exclude new result kinds. Adding a result kind, a new backend
dependency and a request-level selection of result kinds therefore needs a new
decision. The approved plan "Prophet model + per-run model selection in
Predictions" records the developer's choices:

- Prophet is fed the metric history plus the existing known target-scenario
  features as extra regressors.
- Every result kind, baselines included, is individually selectable for a
  prediction run. All kinds are selected by default and at least one is
  required.
- The new `prophet` backend dependency and its transitive dependencies
  (`cmdstanpy`, `holidays`, `matplotlib` and others) are approved.

# Decision

## Scope And Amendments

This ADR amends ADR-007's result-kind table, its "attempt and persist all
result kinds" rule and its persisted-point limit, ADR-011's list of
interval-supporting results, and ADR-012's five-result-kind statement and
child-process stop procedure. It does not change scenario-owned observation
sources (ADR-009), target-level eligibility, the derived-metric policy
(ADR-010), interval states and the complete-bound invariant (ADR-011), the
durable request queue, worker, lifecycle and cancellation bound (ADR-012),
immutable saved versions, the candidate, period and history limits, or the
algorithms and configuration of the five existing result kinds.

## Prophet Result Kind

Forecasting adds a sixth result kind, `prophet`, with the display name
"Prophet". It uses the `prophet` Python package with the CmdStan backend
bundled in its prebuilt wheel.

### Input And Regressors

- The model input is the target scenario's own contiguous effective history
  under the selected cutoff mode (ADR-009), as a `ds`/`y` series of period start
  dates and finite values.
- Each column of the existing known target-scenario features
  (`_known_features`: event count, graph node and edge totals, node and edge type
  counts and linked-node count) is added as an additive Prophet regressor, after
  the same history/future column alignment MLForecast uses.
- A feature whose value is constant across the training history has zero
  variance and is dropped. It is not added as a regressor and its future values
  are ignored.
- Future regressor values come from the prediction periods' known features.
  The future frame's `ds` values are the generated prediction period starts.
- Prophet regressors use the package's default standardisation and prior.
  Holiday calendars, custom seasonalities, changepoint tuning and other
  hyperparameters are not configured.

### Seasonality

Seasonality is set explicitly by the target metric's time unit. Prophet's
automatic seasonality detection is not used.

| Time unit | Yearly | Weekly | Daily |
| --- | --- | --- | --- |
| `day` | on | on | off |
| `week` | on | off | off |
| `month` | on | off | off |
| `year` | off | off | off |

Prophet does not use the detected or manual seasonal period from ADR-007 as a
model parameter. Target-level eligibility is unchanged: a target whose
automatic seasonality is inconclusive and that has no manual period is not
eligible, so every selected result kind for it, Prophet included, is
`ineligible` until a manual period is supplied.

### Fitting And Determinism

- Fitting is maximum a posteriori (MAP) optimisation: `mcmc_samples=0`.
- `uncertainty_samples=1000` is fixed.
- The existing version seed (`41`) is passed to every Prophet fit
  (`fit(..., seed=41)`), which seeds the Stan optimiser.
- Prophet's uncertainty sampling draws from NumPy's global random state and has
  no seed parameter. The global state is therefore reset with
  `numpy.random.seed(41)` immediately before every Prophet `predict` call,
  including each cross-validation window. A result then does not depend on
  which targets or windows were calculated before it, and identical inputs
  produce identical points and bounds.
- `growth="linear"` and the package's default changepoint settings are used.

### Eligibility And Failures

- At least 12 contiguous observations are required, as for MLForecast. A
  shorter history makes the result `ineligible` with the reason "Prophet needs
  at least 12 contiguous observations."
- An expected fit or prediction failure for the metric's data makes the
  `prophet` result `ineligible`. Expected failures are the `ValueError` raised
  by Prophet or pandas for unsuitable data and the `RuntimeError` raised by
  `cmdstanpy` when optimisation fails. Any other exception is unexpected.
- The ineligibility reason is the fixed string "Prophet cannot fit this
  metric." Exception messages are never interpolated into a reason, because
  CmdStan messages can contain console output and temporary file paths. Raw
  CmdStan output, file paths and stack traces are never stored or shown.
- An ineligible `prophet` result does not affect the other result kinds,
  target metrics or the version.
- A missing or unimportable dependency is a deployment defect, not an expected
  data limitation. It is an unexpected calculation failure and follows ADR-012:
  the request is `failed` and no partial version is saved.
- The `cmdstanpy` and `prophet` loggers are silenced so model output does not
  flood worker logs or leak data values.

### Cross-Validation

Prophet records cross-validation MAE with the same method shape as MLForecast:
three expanding windows with a horizon of one period (`n_windows=3`, `h=1`).

For each of the last three observations, a Prophet model with the same
configuration, regressors and seed is fitted on all earlier observations and
predicts that observation. The MAE is the mean absolute error of the three
one-step predictions. Zero-variance features are evaluated separately for each
window's training data.

When the point result is available but a validation window cannot be fitted,
the cross-validation status is `unavailable` and the point result is kept.

### Prediction Intervals

Prophet produces central, two-sided prediction intervals with its native
interval method: `yhat_lower` and `yhat_upper` with
`interval_width = confidence_level / 100`, using the version's selected level
(ADR-011). The point value is `yhat`.

The interval follows ADR-011 unchanged:

- An available interval is complete. Every point has finite bounds with
  `lower_bound <= point_value <= upper_bound`. Bounds are not clipped.
- If the bounds are incomplete, non-finite or unordered, the points are kept
  and the interval is `unavailable` with a user-safe reason.
- An ineligible `prophet` result records its interval as `unavailable` with the
  same safe reason.
- A formula-derived `prophet` result is point-only and its interval is
  `not_applicable`, like derived `mlforecast` and `sarima` results.

The version's `model_configuration` records the Prophet interval method in
`predictionIntervals.prophet` (see Recorded Configuration).

## Per-Version Model Selection

### Request And Validation

The preflight and creation request bodies gain `modelKinds`:

- It is a list of result kinds. Every entry must be a supported result kind:
  `naive`, `seasonal_naive`, `average`, `mlforecast`, `sarima` or `prophet`.
- It must not be empty and must not contain duplicates.
- Invalid input is rejected with the API's standard `422` validation response.
- When `modelKinds` is omitted, all six supported kinds are selected. Existing
  clients therefore keep working and get Prophet in addition.
- The accepted selection is stored in the canonical result-kind order
  (`naive`, `seasonal_naive`, `average`, `mlforecast`, `sarima`, `prophet`),
  regardless of request order.

One selection applies to the whole version: every normal and derived target
metric in that version uses the same selected kinds.

### Snapshot And Version Recording

- The selection is frozen into the immutable request input snapshot when the
  request is accepted. Later code or default changes cannot alter a queued
  request. The snapshot model attribute is `model_kinds`; like the other
  snapshot fields it is stored by its alias, so the stored JSON key is
  `modelKinds`.
- The snapshot format identifier stays `schatten.prediction-input.v1`; the
  field is additive.
- A queued snapshot whose stored JSON has no `modelKinds` key was created
  before this decision. It is calculated with the five legacy kinds (`naive`,
  `seasonal_naive`, `average`, `mlforecast`, `sarima`) exactly as before, never
  with Prophet.
- The published version records the selection as `modelKinds` in
  `prediction_versions.model_configuration`, next to the deterministic
  configuration sections described in Recorded Configuration. Versions remain
  immutable.
- A saved version without `modelKinds` predates this decision. Its result kinds
  are the kinds present in its saved results.

### Recorded Configuration

Every new version's `model_configuration` keeps the existing top-level `seed`,
`mlforecast`, `sarima` and `predictionIntervals` entries and adds:

| Key | Value |
| --- | --- |
| `modelKinds` | The selected kinds in canonical order. |
| `prophet.mcmcSamples` | `0` |
| `prophet.uncertaintySamples` | `1000` |
| `prophet.growth` | `"linear"` |
| `prophet.seasonality` | Object keyed by time unit (`day`, `week`, `month`, `year`), each with boolean `yearly`, `weekly` and `daily`, as in the Seasonality table. |
| `prophet.regressors` | `"knownFeatures"` |
| `prophet.dropZeroVarianceRegressors` | `true` |
| `prophet.minObservations` | `12` |
| `prophet.crossValidation` | `{"nWindows": 3, "h": 1}` |
| `predictionIntervals.prophet` | `{"method": "native_forecast_result", "intervalWidth": <confidence_level / 100>, "uncertaintySamples": 1000}` |

The `prophet` sections are recorded even when Prophet is not selected, like
the existing `mlforecast` and `sarima` sections; `modelKinds` states which kinds
ran.

### Calculation, Persistence And Derived Metrics

- Only the selected kinds are calculated and persisted. A kind that is not
  selected is never fitted and has no result row. "Not selected" is not a
  result status.
- Publication expects exactly the snapshot's selected kinds for every target.
- Derived targets (ADR-010) evaluate their formula for the selected kinds only,
  using the matching normal results. All normal targets in a version share the
  same selection, so every derived result kind has its matching normal inputs.

### Work Limit

The persisted-point estimate counts selected kinds only:
`sum(generated periods per eligible pair) × number of selected kinds` must not
exceed `MAX_POINTS`.

`MAX_POINTS` is raised from 100,000 to 110,000. The largest request the
candidate and period limits admit is 50 pairs × 366 periods, which is 91,500
points with the five legacy kinds and 109,800 with all six. With the raised
limit, every request that passes the candidate and period limits today still
passes with all six kinds selected. The candidate, period and history limits
are unchanged.

Preflight validates `modelKinds` and applies this estimate. Eligibility does
not depend on the selection, and because no valid selection can exceed the
raised limit, a passed preflight stays valid when only the selection changes.
Creation still recomputes the estimate from the frozen snapshot and remains
authoritative. If creation rejects a request for any validation reason,
including a limit, the Predictions UI shows the safe error message to the user.

## Dependency And Runtime

The approved `prophet` dependency (`prophet>=1.1.6,<2`) and its transitive
dependencies are added only in TASK-061B. No other new dependency is approved.

Prophet runs inside the existing single prediction worker's calculation child
process (ADR-012). No new service, queue, worker, scheduler or retry is added.
Prophet must not need network access and must not write outside `/tmp`.

### Calculation Child Process Group And Temporary Files

CmdStan runs as a separate process started by the calculation child. To keep
ADR-012's single-calculation and cancellation guarantees, this ADR amends the
child stop procedure:

- Each calculation child starts its own process group (`os.setsid()`) as the
  first action of its entry function, before any model import. Its process
  group ID is then its own PID.
- When the supervisor stops a child, it sends `SIGTERM` both to the child
  process directly and to the process group whose ID is the child's PID, waits
  at most two seconds, then sends `SIGKILL` the same two ways, and reaps the
  child. CmdStan processes therefore stop with their child.
- The supervisor addresses the group only by the child's PID. It never looks up
  the child's current process group, because a spawned child that has not yet
  called `os.setsid()` is still in the supervisor's own group. A group signal
  that fails because the group does not exist (`ProcessLookupError`) is
  ignored. This happens when the child has not created its group yet, has
  already exited, or is an injected test child; the direct child signal still
  stops it. The five-second cancellation bound is unchanged.
- The supervisor creates one private temporary directory under `/tmp` for
  each calculation child and passes its path to the child as a start argument.
  `multiprocessing` cannot pass a separate environment to a child, and the
  supervisor's own environment is not changed.
- Right after `os.setsid()`, and before any model import or temporary-file use,
  the child sets `TMPDIR` and `MPLCONFIGDIR` to that path and resets Python's
  cached temporary directory (`tempfile.tempdir = None`). CmdStan, which
  creates a temporary directory when `cmdstanpy` is imported, and matplotlib
  therefore write their files there.
- After reaping the child on every outcome (completed, cancelled, failed,
  stopped, or a child that exited or crashed on its own), the supervisor sends
  `SIGKILL` to the process group whose ID is the child's PID, ignoring
  `ProcessLookupError`. A CmdStan process left by a child that died without
  being stopped therefore cannot overlap the next calculation. This is safe:
  Linux does not reuse a PID while a process group still has it as its ID, and
  the supervisor finishes this cleanup before it starts the next child.
- Only then does the supervisor remove the child's temporary directory,
  tolerating removal errors. Files from a killed or crashed child therefore
  never accumulate in the worker's tmpfs.

# Options Considered

## Prophet Without Known-Feature Regressors

Rejected by the developer. MLForecast and SARIMA already use the
target-scenario's known features. Using them in Prophet as well keeps the
comparison fair and lets scenario-specific events and structure affect
Prophet's forecast.

## Fixed Model Set With Prophet Always On

Rejected. Every version would pay Prophet's fitting cost even when the user
only needs a quick baseline comparison.

## Selecting Only Fitted Models, Baselines Always On

Rejected by the developer. Baselines are cheap but not always wanted in a
comparison. A uniform per-kind selection is simpler to explain and validate.

## Per-Kind Eligibility For Prophet Without A Seasonal Period

Rejected by the developer. Prophet does not need the seasonal period, but
making it eligible when other kinds are not would split target-level
eligibility into per-kind eligibility and change preflight, the snapshot and
the UI. Prophet follows the existing target-level eligibility instead.

## Keep The 100,000-Point Limit

Rejected by the developer. With six kinds selected by default, requests that
pass today could be rejected. Raising the limit to 110,000 keeps every
currently admissible request admissible and makes the limit independent of the
selection.

## Persist Unselected Kinds As A New Result Status

Rejected. A "not selected" row would add a result status, change the
`prediction_model_results` lifecycle and fill saved versions with empty
results. The recorded `modelKinds` already explains which kinds were run.

## New Snapshot Format Version

Rejected. The change is additive. A missing field has one clear legacy meaning,
so queued snapshots stay readable without a second snapshot schema.

## Prophet MCMC Sampling Or Holiday Calendars

Rejected for this decision. MCMC sampling is much slower and adds sampler
settings. Holiday calendars need a country choice the domain does not define.
Both can be decided later.

## Prophet's Built-In `cross_validation` Helper

Rejected. It is defined by time-based `initial`, `period` and `horizon` windows
and does not handle regressor frames per window. A three-window, one-step
expanding loop is directly comparable with MLForecast's MAE.

# Consequences

Benefits:

- users can compare Prophet with the existing models and baselines in the same
  charts, including its prediction intervals;
- users can run only the models they need, which shortens queued work and
  reduces stored points;
- existing clients and already-queued requests keep working unchanged; and
- deterministic Prophet configuration and recorded selection keep versions
  auditable.

Costs and constraints:

- The backend image, shared by the API, migration job and prediction worker,
  grows because of Prophet, CmdStan, `holidays` and `matplotlib`. TASK-061B
  records the measured size difference.
- Importing Prophet is slow. Prophet is imported lazily inside the calculation
  child process, so the cost is paid by each calculation that runs Prophet, not
  by API requests. TASK-061B checks whether worker start-up or health-check
  timing must change.
- CmdStan writes temporary model and output files. The read-only worker can
  only write to its `/tmp` tmpfs (currently 64 MB), so TASK-061B measures usage
  and raises the tmpfs size if needed (256 MB proposed).
- The worker's child stop procedure changes to process-group signalling with
  per-child temporary directories. TASK-061B must verify that cancelling or
  stopping during a Prophet fit leaves no running CmdStan process and no
  leftover temporary directory, and still meets the five-second cancellation
  bound.
- Raising `MAX_POINTS` to 110,000 allows about 10% more stored points per
  version than before.
- Builds need a prebuilt manylinux `prophet` wheel with bundled CmdStan for the
  build host's architecture. The `python:3.12-slim` production stage has no
  compilers, so a source build is not supported.
- Prophet's native intervals are sampled. Their coverage is nominal and can
  differ from MLForecast's conformal and SARIMA's analytic intervals.
- Snapshots forbid unknown fields. A rollback to a release before this decision
  cannot calculate queued snapshots that contain `model_kinds`, or publish
  `prophet` results. Pending requests must be handled during such a rollback as
  ADR-012's release contract already requires.
- Each result kind now appears in a version only when it was selected, so
  readers must not assume all kinds are present.

# Implementation Rules

- TASK-061B adds the dependency, the `prophet` result kind and its paired
  migration, the request/snapshot selection, selected-kind calculation,
  persistence, the raised point limit, the recorded configuration, the child
  process-group and temporary-directory handling, and the runtime
  verification. It must not change the existing models' algorithms or
  configuration.
- TASK-061C adds the model selection to the Predictions queue form, Prophet's
  labels, line style and interval band, the saved-version model display, and
  shows create-time validation errors.
- Do not add Prophet holidays, MCMC sampling, changepoint tuning, per-request
  hyperparameters or saved per-user or per-organisation default selections.
- Do not add a new worker, service, queue or retry.

# References

- `docs/decisions/ADR-007-predictions-forecasting-domain.md`
- `docs/decisions/ADR-009-scenario-owned-prediction-inputs.md`
- `docs/decisions/ADR-010-derived-metrics.md`
- `docs/decisions/ADR-011-prediction-intervals.md`
- `docs/decisions/ADR-012-background-prediction-requests.md`
- `docs/decisions/ADR-013-shared-entra-local-https-deployment.md`
- `docs/domains/FORECASTING.md`
- `tasks/TASK-061A-prophet-model-selection-architecture.md`
- `tasks/TASK-061B-prophet-model-selection-backend.md`
- `tasks/TASK-061C-prophet-model-selection-ui.md`
