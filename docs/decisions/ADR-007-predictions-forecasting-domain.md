# ADR-007: Predictions Forecasting Domain

Status: Accepted; observed-value sourcing superseded by ADR-009

Date: 2026-08-24

---

# Amendment

ADR-009 supersedes this ADR's Reality-baseline, compatible-Reality-metric,
merged-history and `allCurrentReality` decisions. Those sections remain as the
historical basis for the original Forecasting implementation; ADR-009 is the
current decision for prediction observation sources and cutoff naming.

---

# Context

Schatten has scenario-owned events, graph history and typed timeseries. The
protected `reality` scenario contains manually entered realized metric values,
while other scenarios describe alternative event calendars and organisation
structures. The application needs a Predictions workspace that can generate
and compare named forecast versions without treating derived values as manual
Reality data or allowing one planning scenario's values to train another.

The feature requires a clear ownership boundary for derived results, a
repeatable modelling stack, and a bounded execution model. The current AI
Domain is a candidate domain for document classification, summarization and
extraction; it is not the owner of scenario forecasting.

This ADR has completed human architecture review and is `Accepted`. Its
acceptance permits TASK-041B and TASK-041C to implement their separately
scoped backend and UI work. It does not claim that dependencies, schema, API
or UI implementation already exist.

# Decision

## Forecasting Domain And Data Boundary

Schatten introduces a Forecasting Domain for derived scenario prediction
results. It owns immutable prediction versions, target-metric prediction
records, per-model result metadata and dated prediction points. It does not own
or modify scenarios, events, graph elements, timeseries or manually entered
timeserie values.

The active protected scenario with stable key `reality` supplies the baseline
observed target values. ADR-008 amends this rule so that a target scenario's
own matching metric value overrides Reality for the same period; values from
every other non-Reality scenario remain prohibited as model targets, training
values, baseline inputs or imputation sources.

Forecasting reads source data through Organisation States and Organisation Twin
Structure Domain service boundaries. It retains immutable source-input and
configuration snapshots with each result so a saved output remains auditable
if source rows are subsequently edited or persistence-soft-deleted.

## Eligible Metrics And Time Semantics

Only numeric target timeseries are eligible. An active target metric must match
an active Reality metric by stable timeserie key and have a compatible time
unit and display unit. String and boolean metrics, missing Reality matches,
incompatible metadata, gaps in the required Reality time-unit grid and
insufficient history are normal ineligible states, not fallback-to-imputation
conditions.

For each eligible target metric, Forecasting constructs known inputs from the
target scenario only at valid period starts: event count, active graph node and
edge totals, node and edge type counts, and the number of active nodes linked
to that target metric. Graph lifetime visibility follows the Organisation Twin
Structure Domain's inclusive `create_date`/`delete_date` rule. Events are
bucketed into the target metric's day, week, month or year period. Graph
attributes and non-Reality scenario values are excluded from the MVP feature
set.

Users select a prediction range and one of two cutoff modes:

- `asOfStart`: use only merged permitted observations strictly before the first
  generated period. This supports historical forecasts without later values
  leaking into the model.
- `allCurrentReality`: retain the existing API value but use all current merged
  permitted observations. The saved metadata discloses both this leakage mode
  and ADR-008's target-scenario override policy.

## Models And Validation

Each otherwise eligible target metric attempts and persists all five output
kinds; Forecasting does not select and discard all but a winning model.

| Result kind | Decision |
| --- | --- |
| `mlforecast` | MLForecast with a deterministic scikit-learn `RandomForestRegressor`, target lags, calendar features and the known target-scenario inputs. |
| `naive` | Repeat the latest eligible effective observation. |
| `seasonal_naive` | Repeat the effective observation one selected seasonal cycle ago. |
| `average` | Mean of effective observations available under the selected cutoff mode. |
| `sarima` | Statsmodels SARIMAX with the selected seasonal period and the same known target-scenario inputs. |

Seasonality is detected separately for each eligible metric by identifying
candidate autocorrelation periods and selecting a credible candidate with
rolling-origin seasonal-naive validation. If detection is inconclusive, the
caller must provide a manual period for that metric; seasonal-naive and SARIMA
then remain stored as ineligible until a valid override is supplied.

MLForecast uses rolling-origin cross-validation when its contiguous history
supports three validation windows. Its saved metadata records MAE when cross
validation ran and an explicit unavailable status when it could not. Model
seeds and configuration are fixed and saved with the prediction version to make
identical inputs reproducible.

## Version Lifecycle And Failure Semantics

A prediction version belongs to one organisation and has a user-provided name
that is case-insensitively unique within that organisation. A successful
version is immutable: it has no update or overwrite operation. Re-running a
prediction requires a new name.

Expected data or model limitations are persisted per target metric/model with
a machine-readable status and user-safe reason. They do not prevent valid
metrics or models in the same version from being saved. An unexpected
generation failure aborts the transaction and leaves no partial version.

## Execution Model And Resource Limits

The MVP generates predictions synchronously within the authenticated backend
request. It does not add a queue, background worker, scheduler, retry loop or
progress-polling protocol.

Before fitting, preflight and creation enforce these server-side limits for one
request:

- at most 50 numeric target scenario/metric candidates with compatible Reality
  metadata; detailed eligibility is evaluated only within this protective bound;
- at most 366 generated periods per pair;
- at most 10,000 contiguous permitted observations per pair; and
- at most 100,000 persisted prediction points across the version.

A request exceeding a limit is rejected with a validation response that names
the exceeded limit. These limits bound database output and synchronous model
work; they do not change the source-data boundary or silently truncate a
result.

# Options Considered

## Extend The AI Domain

Rejected. The AI Domain's candidate scope is document-derived classifications,
summaries and extractions. Forecasting has different source ownership,
time-series semantics, lifecycle and API consumers. A separate derived-data
domain prevents its model outputs from being mistaken for AI document output or
manual Reality data.

## Use Values From Other Scenarios As Training Data

Rejected. Values from another planning scenario may leak assumptions from one
target into another. ADR-008 permits only the selected target scenario's own
values to override Reality by period for the approved possible-pasts use case.

## Use Only One Best Forecast Model

Rejected. Users need to plot and compare ML, statistical and baseline outputs.
Persisting every result gives users an explicit comparison rather than hiding
the alternative methods behind one backend choice.

## Asynchronous Job Execution

Rejected for the MVP. No job infrastructure currently exists, and the bounded
synchronous request model is simpler to audit and operate. A later ADR is
required before introducing asynchronous execution, retries or scheduling.

## Impute Missing Reality Observations

Rejected. Filling gaps would make a derived input appear observed. The MVP
reports incomplete history as ineligible instead of inventing values.

# Consequences

Benefits:

- predictions are clearly derived, auditable and distinct from manual Reality
  data;
- scenario comparisons can use the same observed truth while reflecting each
  scenario's own known event and graph context;
- users can compare named overlapping versions and all requested methods;
- deterministic configuration, snapshots and cross-validation metadata make
  results reviewable; and
- bounded synchronous work avoids adding operational infrastructure to the MVP.

Costs and constraints:

- prediction versions require new persistence, domain APIs, migrations and UI;
- only numeric, complete merged permitted histories are eligible;
- target scenarios without a compatible same-key Reality metric are excluded;
- long or broad runs can be rejected by the MVP work limits; and
- synchronous generation may need a future background-job design as data size
  or model complexity grows.

# Implementation Rules

- Add `mlforecast`, `scikit-learn` and `statsmodels` only after this ADR is
  accepted and only in TASK-041B's scoped implementation.
- Use repository-owned paired SQL migrations; do not modify production schema
  manually.
- Keep all trusted validation, source isolation, feature construction and
  persistence in FastAPI/backend services.
- Do not write prediction points into `timeserie_values` or present them as
  manually entered Reality values.
- Do not modify the existing Analysis workspace or `/analysis` route. The
  future UI is a separate Predictions tab under TASK-041C.
- Preserve source-row ownership: Forecasting may read Organisation States and
  Organisation Twin Structure data but must not update it.

# References

- `docs/decisions/ADR-001-tech-stack.md`
- `docs/decisions/ADR-008-target-scenario-observation-overrides.md`
- `docs/decisions/ADR-009-scenario-owned-prediction-inputs.md`
- `docs/domains/FORECASTING.md`
- `docs/domains/ORG_STATES.md`
- `docs/domains/ORG_TWIN_STRUCTURE.md`
- `tasks/TASK-041A-predictions-architecture-domain.md`
- `tasks/TASK-041B-predictions-backend-modeling.md`
- `tasks/TASK-041C-predictions-tab-ui.md`
