# TASK-041B Predictions Backend And Modelling

## Source Plan

Approved plan: "Prediction Feature Task Specifications", based on the approved
Predictions workspace plan and the architecture/domain decision in
TASK-041A.

Dependency: TASK-041A Predictions Architecture And Domain must be accepted
before this task is implemented.

## Goal

Implement the Forecasting Domain persistence, backend API and deterministic
prediction modelling. The backend creates immutable, named versions of
numeric-metric forecasts for selected scenarios while ensuring Reality is the
only source of observed metric values.

## Requirements

### Dependencies and persistence

- Add the approved direct backend dependencies `mlforecast`, `scikit-learn`
  and `statsmodels`, and update `backend/uv.lock`.
- Add SQLAlchemy models and paired up/down migrations for:
  - immutable organisation-owned prediction versions;
  - scenario/metric prediction records with source and model-input snapshots;
  - per-model result metadata and eligibility status;
  - dated numeric prediction points.
- Prediction version names must be case-insensitively unique inside an
  organisation. Versions have no update or overwrite behavior.
- Persist the target-scenario identity, stable metric metadata, Reality source,
  chosen cutoff mode, seasonal period and source, model configuration/seed,
  cross-validation score or unavailable state, input snapshots, creator and
  creation time.
- Normal ineligibility must be stored per metric/model without preventing valid
  metrics in the same prediction version. Unexpected generation failure must
  roll back the version transaction.

### API

- Add authenticated organisation-scoped routes:

```text
POST /api/v1/organisations/{organisation_key}/predictions/preflight
POST /api/v1/organisations/{organisation_key}/predictions
GET  /api/v1/organisations/{organisation_key}/predictions
GET  /api/v1/organisations/{organisation_key}/predictions/{prediction_key}
```

- The preflight request validates selected active scenario keys, date range,
  Reality matching, history continuity, target-scenario feature availability,
  automatic seasonality and required manual overrides. It returns
  eligible/ineligible metric rows and any per-metric manual seasonal-period
  requirement without persisting a version.
- The create request contains a non-blank version name, explicit non-empty
  target scenario IDs, `startDate`, `endDate`, cutoff mode (`asOfStart` or
  `allCurrentReality`) and manual seasonal-period overrides keyed by metric ID.
- Resolve the active protected Reality scenario by its stable `reality` key.
  Missing Reality, inactive target scenarios and cross-organisation resources
  return validation/not-found responses consistent with existing API patterns.
- Return list metadata separately from prediction-version detail. Detail must
  contain the saved scenario, metric, model, status, scores, inputs metadata
  and points needed by TASK-041C.
- Keep routes thin, use Pydantic strict schemas, validate all untrusted input,
  apply existing authentication/unsafe-request and organisation-boundary
  patterns, and write audit actors for created rows.

### Forecasting behavior

- Process active numeric target metrics only. A metric is eligible only if the
  active Reality scenario has the same stable metric ID, matching time unit and
  compatible unit. String and boolean metrics receive a saved exclusion reason.
- Values from target scenarios and all other non-Reality scenarios must never
  be used as the observed model target or baseline input.
- For each target scenario and metric, construct known exogenous features from
  that scenario only: per-period event count, active graph node/edge totals,
  node/edge type counts and target-metric-linked node count. Do not derive
  features from graph attributes or values in other scenarios.
- Evaluate graph lifetime visibility at each metric period start and bucket
  events into the corresponding day/week/month/year period.
- Require contiguous Reality observations on the metric time-unit grid. Do not
  impute missing periods; save an ineligible status instead.
- Support a selected date range with `startDate < endDate`; generate only valid
  time-unit starts inside the inclusive date range.
- In `asOfStart` mode, train and calculate baselines from Reality observations
  strictly before the first generated period. In `allCurrentReality` mode, use
  all current Reality observations and persist the selected mode so callers can
  disclose future leakage for retrospective ranges.
- Always attempt and persist these five output kinds for each otherwise
  eligible metric:
  - naive: repeat the latest eligible Reality observation;
  - seasonal naive: repeat the Reality observation one seasonal cycle ago;
  - average: mean of all Reality observations available under the chosen cutoff
    mode;
  - MLForecast: deterministic MLForecast with `RandomForestRegressor`, target
    lags, calendar features and the scenario-derived exogenous features;
  - SARIMA: Statsmodels SARIMAX using the same seasonal period and exogenous
    features.
- Detect candidate seasonal periods with autocorrelation and choose a period by
  rolling-origin seasonal-naive validation. If no credible period can be
  selected, require a manual per-metric override; otherwise mark seasonal
  outputs ineligible with a reason.
- Use MLForecast rolling cross-validation when enough contiguous history
  supports three validation windows. Persist MAE or an explicit
  cross-validation-unavailable status. Do not select only a winning model:
  persist every requested output kind.
- Use fixed random seeds and bounded model-search/work limits from the accepted
  ADR. This task must remain synchronous and must not add a worker, queue or
  scheduler.

## Acceptance Criteria

- [ ] Backend dependency declarations and lockfile contain only the approved
      modelling dependencies needed by this task.
- [ ] All new schema changes are supplied as one or more paired migrations and
      apply and roll back on disposable PostgreSQL.
- [ ] Versions are immutable and duplicate case-insensitive names in one
      organisation are rejected.
- [ ] Preflight returns actionable eligible/ineligible metric and seasonality
      information without writing prediction rows.
- [ ] Creation, listing and detail endpoints enforce existing authentication
      and organisation isolation patterns.
- [ ] A target scenario's result uses only Reality values plus that target's
      own events and graph history.
- [ ] Naive, seasonal-naive, average, MLForecast and SARIMA results follow the
      stated definitions and persist provenance/status metadata.
- [ ] `asOfStart` does not use Reality observations on or after the first
      predicted period; `allCurrentReality` records its selected mode.
- [ ] Missing history, absent Reality matching metrics, manual-seasonality
      requirements and insufficient model data are visible as normal statuses.
- [ ] Expected per-model ineligibility does not discard successful results;
      unexpected failures leave no partial version.
- [ ] Data, database and PlantUML documentation describe the implemented
      Forecasting Domain schema and relationships.
- [ ] No Predictions frontend or background-job implementation is added.

## Out Of Scope

- The Predictions workspace tab, form, version library and charts.
- Modifying the existing Analysis workspace or `/analysis` route.
- Background jobs, asynchronous workers, queues, retries or scheduling.
- Editing manually entered Reality data or any existing scenario metrics.
- Forecasting string or boolean metrics, imputing gaps, or user-selected
  individual numeric metrics.
- New model providers, remote services or unapproved dependencies.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-001-tech-stack.md
docs/decisions/ADR-007-predictions-forecasting-domain.md
docs/domains/FORECASTING.md
docs/domains/ORG_STATES.md
docs/domains/ORG_TWIN_STRUCTURE.md
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
db/migrations/README.md
docs/TESTING.md
tasks/TASK-041A-predictions-architecture-domain.md
tasks/TASK-041B-predictions-backend-modeling.md
```

- Follow existing `org_states` and `org_twin_structure` models, services,
  routers, stable public-key and soft-delete lookup patterns. Keep Forecasting
  Domain writes inside its own service boundary.
- The public API uses stable keys only; bigint foreign keys remain internal.
- Prediction input snapshots and result points must remain readable when source
  rows are later soft-deleted. Normal scenario deletion rules must be extended
  only if the accepted domain decision requires it.
- Add the new API client contract only when needed by this backend task's API
  tests; browser-facing UI client work belongs to TASK-041C.
- Do not modify existing scenario copy behavior. It intentionally does not copy
  timeseries, and target metrics must therefore be matched to Reality by stable
  ID rather than persistence identity.

## Testing

Required:

- [ ] Backend tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests: Predictions UI is TASK-041C.
- [ ] Frontend build: no frontend source changes are expected.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright

MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten \
  uv run pytest tests/test_migrations_integration.py -v
```

Backend tests must cover:

- preflight and creation validation, authentication and organisation isolation;
- immutable version names, no overwrite behavior and audit metadata;
- Reality-only observed values and scenario-isolated events/graph features;
- same-ID numeric metric matching and all ineligibility reasons;
- period construction, contiguous-history rejection and both cutoff modes;
- exact naive, seasonal-naive and average baseline outputs;
- automatic seasonality, manual fallback, MLForecast CV availability and
  persisted scores/statuses;
- SARIMA and MLForecast result persistence; and
- unexpected failure rollback plus migration up/down behavior.

Manual verification must create suitable Reality values and target scenario
events/graph history, run a preflight and a named prediction version, inspect
the stored result metadata, and confirm that changing another scenario's values
does not affect the result.

## Documentation

Update:

- `docs/domains/FORECASTING.md`
- `docs/data/DATA-MODEL.md`
- `docs/data/DATABASE.md`
- `docs/diagrams/data-logical-model.puml`
- `docs/diagrams/db-physical-schema.puml`
- corresponding generated SVGs in `docs/diagrams/generated/`

## Notes For AI Agent

- TASK-041A's ADR and Forecasting Domain document are prerequisites.
- Add only the dependencies approved by the source plan.
- Use paired SQL migrations and never alter production data manually.
- Add tests for every changed backend behavior.
- Do not implement browser UI or a background execution system.
- Report changed files and every check run.
