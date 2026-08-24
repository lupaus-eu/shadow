# Forecasting Domain

Status: accepted in ADR-007; no schema, API or runtime implementation yet

## Purpose

The Forecasting Domain produces and stores auditable, immutable predictions for
scenario metrics. It keeps derived model output distinct from manually entered
Reality timeseries values and does not change source scenario data.

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
- a clear distinction between manual Reality values and derived predictions

Does NOT Own:

- organisations
- scenarios, organisation states or events
- timeseries definitions or manually entered timeserie values
- graph nodes, graph edges, metamodels or graph attributes
- the existing Analysis workspace

## Domain Rules

### Reality Is The Observed Truth Source

The active protected scenario with stable key `reality` is the only source of
observed values for Forecasting. Every target metric must match an active
Reality metric by stable timeserie key and use compatible time-unit and display
unit metadata.

Values from every other scenario are prohibited as targets, training data,
baseline data or gap-imputation data. Forecasting does not write into
`timeserie_values` and does not turn its results into manual Reality data.

### Scenario-Isolated Explanatory Inputs

For a target scenario, Forecasting may use only that scenario's own known
events and graph history as explanatory inputs. It derives period-specific
event counts, active graph node/edge totals, type counts and target-metric
linked node counts. Graph visibility uses the Organisation Twin Structure
Domain's logical lifetime rules.

The domain never combines a target scenario's model inputs with another
non-Reality scenario's metric values, events or graph structure.

### Eligible Metrics And Date Grid

Only number-valued timeseries are eligible. The Reality history must be
contiguous on the matching metric time-unit grid; no missing observation is
interpolated or forward-filled. Non-numeric, unmatched, incompatible,
incomplete or insufficient metrics are normal ineligible states with a saved
reason.

Prediction requests provide a start and end date. Each target metric produces
only the valid day, week, month or year starts that fall inside that inclusive
range. The request requires the start date to be earlier than the end date.

### Training Cutoff Modes

Each version records one selected truth cutoff mode:

- `asOfStart` uses only Reality observations strictly before the first
  predicted metric period. It supports non-leaking historical forecasts.
- `allCurrentReality` uses all currently active Reality observations. A caller
  must disclose that it can use future knowledge for a past prediction range.

### Result Kinds

Every otherwise eligible target metric attempts these five result kinds:

| Kind | Meaning |
| --- | --- |
| MLForecast | Deterministic MLForecast using scikit-learn RandomForestRegressor, target lags, calendar features and known target-scenario inputs. |
| Naive | Repeats the latest eligible Reality observation. |
| Seasonal naive | Repeats the Reality observation one selected seasonal cycle ago. |
| Average | Uses the mean of all Reality observations available under the selected cutoff mode. |
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

Every saved result retains creator and creation metadata, target and Reality
identifiers, cutoff mode, seasonal period/source, deterministic model
configuration and seed, validation information, source-input snapshots and
result points. This keeps results auditable after source rows change or are
soft-deleted.

Expected limitations are stored per metric/model with a machine-readable
status and safe explanatory reason. They do not prevent other eligible
metrics/models from being stored in the same version. Unexpected generation
errors abort the version transaction and leave no partial version.

### MVP Execution Bounds

Forecasting runs synchronously in the authenticated backend request. There is
no background worker, queue, scheduler, retry mechanism or progress-polling
protocol in this MVP.

One request permits at most 50 eligible target scenario/metric pairs, 366
generated periods per pair, 10,000 contiguous Reality observations per pair and
100,000 persisted prediction points across the version. A request that exceeds
a limit is rejected rather than truncated.

## Database Ownership

Planned tables:

- prediction versions
- prediction target metrics
- prediction model results
- prediction points

These tables will be owned exclusively by Forecasting Domain after TASK-041B
adds them through paired migrations. Other domains may be referenced as source
data but may not modify Forecasting-owned rows.

## API Ownership

Forecasting's planned organisation-scoped API supports preflight, creation,
listing and detail retrieval of prediction versions. TASK-041B defines and
implements the public route and schema contract.

## Dependencies

Depends On:

- Organisations Domain for organisation scope
- Organisation States Domain for Reality, scenarios, events and timeseries
- Organisation Twin Structure Domain for graph-history inputs
- Users Domain for audit actors

Referenced By:

- Predictions workspace UI planned in TASK-041C

## Common Workflow

### Generate A Prediction Version

1. Validate organisation and selected active target scenarios.
2. Resolve the active protected Reality scenario.
3. Match active numeric target metrics to compatible Reality metrics by stable
   key.
4. Validate continuous Reality history and construct only the target
   scenario's known event and graph inputs.
5. Detect seasonality or request a manual period where detection is
   inconclusive.
6. Fit and evaluate the requested models within the synchronous work limits.
7. Persist the immutable named version, result metadata, points and source
   snapshot; persist normal ineligibility states alongside valid outputs.
8. Roll back the entire version when an unexpected generation error occurs.

## AI Agent Guidance

Before changing Forecasting behavior, read:

```text
docs/decisions/ADR-007-predictions-forecasting-domain.md
docs/domains/FORECASTING.md
docs/domains/ORG_STATES.md
docs/domains/ORG_TWIN_STRUCTURE.md
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
db/migrations/README.md
```

- Keep manual Reality values and derived prediction values in separate storage
  and presentation paths.
- Enforce source-data isolation in backend services; frontend selection is not
  the security boundary.
- Do not introduce a worker or queue without a new accepted ADR.
- Update data-model documentation and diagrams with any implemented Forecasting
  schema in TASK-041B.
