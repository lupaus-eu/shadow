# Forecasting Domain

Status: persistence and synchronous backend API implemented by TASK-041B

## Purpose

The Forecasting Domain produces and stores auditable, immutable predictions for
scenario metrics. It keeps derived model output distinct from manually entered
scenario timeseries values and does not change source scenario data.

## Responsibilities

Owns:

- prediction versions
- target-metric prediction records
- per-model result metadata and eligibility states
- dated prediction points
- immutable modelling and source-input snapshots

Provides:

- named, comparable forecast versions for one organisation
- prediction-method provenance and cross-validation metadata
- a clear distinction between manual scenario values and derived predictions

Does NOT Own:

- organisations
- scenarios, organisation states or events
- timeseries definitions or manually entered timeserie values
- graph nodes, graph edges, metamodels or graph attributes
- the existing Analysis workspace

## Domain Rules

### Scenario-Owned Observation Sources

Each selected target scenario supplies its own observed metric values. A target
metric needs no Reality counterpart, and Forecasting never reads, merges,
falls back to or imputes from Reality or another scenario's values. Reality is
an eligible target scenario and, when selected, uses only its own values.

Forecasting does not write into `timeserie_values` or turn derived predictions
into manual scenario values.

Derived metric targets are not model-fitted. Forecasting first creates normal
metric results, then evaluates a derived metric equation independently for each
matching result kind using its normal input result points. Missing, unavailable
or invalid inputs produce an ineligible derived result with saved provenance.

### Scenario-Isolated Explanatory Inputs

For a target scenario, Forecasting may use only that scenario's own known
events and graph history as explanatory inputs. It derives period-specific
event counts, active graph node/edge totals, type counts and target-metric
linked node counts. Graph visibility uses the Organisation Twin Structure
Domain's logical lifetime rules.

The domain never combines a target scenario's model inputs or values with any
other scenario's metric values, events or graph structure.

### Eligible Metrics And Date Grid

Only number-valued target timeseries are eligible. The target scenario's own
effective history must be contiguous on the matching metric time-unit grid; no
missing observation is interpolated or forward-filled. Non-numeric, incomplete
or insufficient metrics are normal ineligible states with a saved reason.

Prediction requests provide a start and end date. Each target metric produces
only the valid day, week, month or year starts that fall inside that inclusive
range. The request requires the start date to be earlier than the end date.

### Training Cutoff Modes

Each version records one selected observation cutoff mode:

- `asOfStart` uses only effective permitted observations strictly before the
  first predicted metric period. It supports non-leaking historical forecasts.
- `allCurrentScenario` uses all currently active target-scenario observations.
  A caller must disclose its future-knowledge risk for a past prediction range.

### Result Kinds

Every otherwise eligible target metric attempts these five result kinds:

| Kind | Meaning |
| --- | --- |
| MLForecast | Deterministic MLForecast using scikit-learn RandomForestRegressor, target lags, calendar features and known target-scenario inputs. |
| Naive | Repeats the latest eligible effective observation. |
| Seasonal naive | Repeats the effective observation one selected seasonal cycle ago. |
| Average | Uses the mean of effective observations available under the selected cutoff mode. |
| SARIMA | Statsmodels SARIMAX with the selected seasonal period and known target-scenario inputs. |

Seasonality is automatically detected per metric using autocorrelation and
rolling-origin validation. If detection is inconclusive, a manual per-metric
seasonal period is required before seasonal-naive and SARIMA results can be
generated.

MLForecast cross-validation uses rolling origins when enough history supports
three validation windows. The result records MAE or an explicit unavailable
state. Forecasting persists all result kinds rather than silently selecting one
winner.

### Versioning, Audit And Failures

A prediction version has an organisation-local, case-insensitively unique
name. Saved versions are immutable and cannot be overwritten; a new execution
needs a new name.

Every saved result retains creator and creation metadata, target identity,
cutoff mode, seasonal period/source, deterministic model
configuration and seed, validation information, source-input snapshots
including each effective observation source, and result points. This keeps
results auditable after source rows change or are soft-deleted.

Expected limitations are stored per metric/model with a machine-readable
status and safe explanatory reason. They do not prevent other eligible
metrics/models from being stored in the same version. Unexpected generation
errors abort the version transaction and leave no partial version.

### MVP Execution Bounds

Forecasting runs synchronously in the authenticated backend request. There is
no background worker, queue, scheduler, retry mechanism or progress-polling
protocol in this MVP.

One request permits at most 50 numeric target scenario/metric candidates, 366
generated periods per pair, 10,000 contiguous
effective observations per pair, and 100,000 persisted prediction points across
the version. Detailed eligibility is evaluated only within the candidate bound.
A request that exceeds a limit is rejected rather than truncated.

## Database Ownership

Owned tables:

- prediction versions
- prediction target metrics
- prediction model results
- prediction points

These tables are owned exclusively by Forecasting Domain. Other domains may be
read through their service boundaries but may not modify Forecasting-owned rows.
Target source identities are retained as stable-key snapshots rather than source
foreign keys, so saved versions remain readable when source rows are soft-deleted.

## API Ownership

The organisation-scoped API exposes `preflight`, create, list and detail routes
under `/api/v1/organisations/{organisation_key}/predictions`. Preflight is
read-only. Create is authenticated, origin/CSRF-protected and stores an audit
actor; list and detail follow the existing authenticated organisation boundary.

## Dependencies

Depends On:

- Organisations Domain for organisation scope
- Organisation States Domain for scenarios, events and timeseries
- Organisation Twin Structure Domain for graph-history inputs
- Users Domain for audit actors

Referenced By:

- Predictions workspace UI planned in TASK-041C

## Common Workflow

### Generate A Prediction Version

1. Validate organisation and selected active target scenarios.
2. Resolve active numeric metrics and their own target-scenario history.
3. Validate continuity and construct only the target scenario's known event and
   graph inputs.
4. Detect seasonality or request a manual period where detection is
   inconclusive.
5. Fit and evaluate the requested models within the synchronous work limits.
6. Persist the immutable named version, result metadata, points and source
   snapshot; persist normal ineligibility states alongside valid outputs.
7. Roll back the entire version when an unexpected generation error occurs.

## AI Agent Guidance

Before changing Forecasting behavior, read:

```text
docs/decisions/ADR-007-predictions-forecasting-domain.md
docs/decisions/ADR-008-target-scenario-observation-overrides.md
docs/decisions/ADR-009-scenario-owned-prediction-inputs.md
docs/domains/FORECASTING.md
docs/domains/ORG_STATES.md
docs/domains/ORG_TWIN_STRUCTURE.md
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
db/migrations/README.md
```

- Keep manual scenario values and derived prediction values in separate storage
  and presentation paths.
- Enforce source-data isolation in backend services; frontend selection is not
  the security boundary.
- Do not introduce a worker or queue without a new accepted ADR.
- Update data-model documentation and diagrams with any implemented Forecasting
  schema in TASK-041B.
