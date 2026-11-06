# TASK-054B Prediction Intervals Backend And Persistence

## Source Plan

Approved plan: "Prediction Intervals for Forecasts", amended so the selectable
integer prediction-interval level defaults to 80 percent.

Dependency: TASK-054A Prediction Intervals Architecture must be completed and
ADR-011 accepted before this task is implemented.

## Goal

Extend immutable prediction versions with a selected prediction-interval level
and persist model-specific lower and upper bounds for directly fitted
MLForecast and SARIMA results. Preserve valid point forecasts when expected
interval calculation fails.

Expose the saved interval metadata and bounds through the existing
organisation-scoped prediction routes without adding dependencies or changing
the synchronous execution model.

## Requirements

### Persistence and migration

- Add paired migrations:

```text
db/migrations/014_add_prediction_intervals.sql
db/migrations/014_add_prediction_intervals.down.sql
```

- The approved assumption is that no prediction data exists in production.
  Migration 014 may begin by truncating `prediction_versions` with its owned
  cascading rows so development prediction data does not need a backfill or
  compatibility path.
- Add non-null `prediction_versions.confidence_level` using an integer type,
  defaulting to 80 and constrained to values from 50 through 99.
- Add `prediction_model_results.prediction_interval_status`, constrained to
  `available`, `unavailable` or `not_applicable`, non-null for every new result,
  and add a nullable `prediction_interval_reason`.
- Add nullable `lower_bound` and `upper_bound` columns to
  `prediction_points`. Database constraints must require the pair to be both
  null or both non-null and, when present, finite, ordered and enclosing the
  point value.
- The down migration may also discard development prediction rows before
  restoring the old schema. It must not target data outside the
  Forecasting-owned prediction tables.
- Update SQLAlchemy models and physical/logical data documentation and diagrams
  to match the migration.

### API contract

- Extend both preflight and create request schemas with camel-case
  `confidenceLevel`, represented internally as an integer from 50 through 99.
  Omitted input defaults to 80 as product behavior.
- Extend list and detail version responses with required, non-null
  `confidenceLevel`.
- Extend every model-result response with:
  - `predictionIntervalStatus`;
  - nullable `predictionIntervalReason`.
- Extend every prediction point with nullable `lowerBound` and `upperBound`.
- Persist the selected level on every new version and include the interval
  method, calibration configuration and level in the immutable model
  configuration snapshot.
- Keep all existing route paths, authentication, CSRF/origin enforcement,
  organisation isolation, audit actors and immutable-name behavior unchanged.

### Interval generation

- Generate central, two-sided bounds only for directly fitted normal-metric
  `mlforecast` and `sarima` results.
- MLForecast must use its installed built-in conformal-error support with
  `n_windows=3`, `h=1` and the selected level. Parse the central prediction and
  named lower/upper columns explicitly; do not depend on positional last-column
  selection after interval columns are added.
- SARIMA must use the fitted result's native forecast-result API, reading its
  predicted mean and confidence bounds with
  `alpha = 1 - confidence_level / 100`.
- Keep naive, seasonal-naive and average points unchanged with interval status
  `not_applicable` and null bounds.
- Formula-derived results, including derived results whose result-kind name is
  `mlforecast` or `sarima`, remain point-only with interval status
  `not_applicable`; do not propagate source bounds through formulas.
- Validate each generated interval as a complete result set. All lower/upper
  values must be finite, ordered and enclose their corresponding point value.
  Do not clip negative values.
- If an expected MLForecast calibration, SARIMA interval extraction or bound
  validation failure occurs after valid point generation, persist the points
  with null bounds, keep the model result available and set interval status to
  `unavailable` with a safe reason.
- A model with no valid point forecast retains its existing ineligible result
  behavior. Unexpected errors retain the existing transaction-wide rollback.
- Do not partially persist bounds for one result. Do not change the 50-pair,
  366-period, 10,000-observation or 100,000-point limits; bounds are columns on
  existing point rows and do not increase point-count accounting.
- Add no direct or transitive dependency expressly for this feature.

## Acceptance Criteria

- [ ] Migration 014 applies and rolls back cleanly on disposable PostgreSQL,
      intentionally discarding existing development prediction versions in
      both directions while leaving non-Forecasting data intact.
- [ ] Database constraints reject out-of-range confidence levels, half-present,
      non-finite, inverted and point-excluding bounds.
- [ ] Preflight and creation accept integer levels 50 and 99, default omitted
      input to 80, and reject values outside the range or non-integer values.
- [ ] Every new version persists and returns its selected non-null level.
- [ ] Direct MLForecast results use three one-step conformal-error calibration
      windows and return finite bounds at the selected level.
- [ ] Direct SARIMA results use native Statsmodels forecast bounds at the
      selected level.
- [ ] Available interval points satisfy
      `lowerBound <= value <= upperBound`, and the full result has bounds.
- [ ] Expected interval failure retains valid point forecasts, returns null
      bounds and exposes an unavailable status plus safe reason.
- [ ] Baseline and formula-derived results remain unchanged point forecasts and
      expose `not_applicable` with null bounds.
- [ ] Existing model ineligibility, version rollback, source isolation,
      authentication, authorisation, audit and resource-limit behavior remains
      covered by regression tests.
- [ ] Data/database documentation and committed PlantUML sources and generated
      SVGs match the implemented schema.
- [ ] No frontend UI, background processing or dependency change is included.

## Out Of Scope

- Confidence-level form controls, frontend DTO changes, chart bands and UI
  interval messages; those belong to TASK-054C.
- Prediction intervals for naive, seasonal-naive, average, live Reality or
  formula-derived outputs.
- Asymmetric or simultaneous intervals, empirical coverage analysis,
  resampling, interval clipping or metric-specific value constraints.
- New model kinds, model selection, parameter tuning or cross-validation
  changes unrelated to generating MLForecast intervals.
- New routes, workers, queues, retry protocols, monitoring services or changed
  prediction-work limits.
- Preservation or backfill of prediction versions created before this feature.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0002-database-migrations.md
docs/adr/0007-predictions-forecasting-domain.md
docs/adr/0009-scenario-owned-prediction-inputs.md
docs/adr/0010-derived-metrics.md
docs/adr/0011-prediction-intervals.md
docs/architecture/domains/FORECASTING.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
db/migrations/README.md
docs/architecture/diagrams/README.md
docs/operations/testing.md
docs/archive/tasks/TASK-054A-prediction-intervals-architecture.md
docs/archive/tasks/TASK-054B-prediction-intervals-backend.md
```

- Reuse the installed `mlforecast` and `statsmodels` capabilities. Do not
  change `backend/pyproject.toml` or `backend/uv.lock` for this feature.
- Represent interval generation with an explicit internal result structure so
  point values, optional bounds, interval status and reason are not coupled by
  fragile tuple ordering.
- Isolate expected interval calculation from point calculation so a handled
  calibration failure cannot discard otherwise valid model points.
- Preserve the current distinction between expected model limitations and
  unexpected transaction-aborting failures.
- Update migration discovery expectations and fixtures that construct
  prediction request/response objects.

## Testing

Required:

- [ ] Backend tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck
- [ ] Diagram build
- [ ] AI review record

Not applicable:

- [ ] Frontend tests and frontend build: frontend behavior belongs to
      TASK-054C.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright

MIGRATION_TEST_DATABASE_URL=postgresql://shadow:shadow_dev_password@localhost:5432/shadow \
  uv run pytest tests/test_migrations_integration.py -v

cd ..
docker compose --profile docs build diagram-renderer
docker compose --profile docs run --rm diagram-renderer
docker compose --profile docs run --rm diagram-renderer \
  -tsvg -o generated data-logical-model.puml
```

Backend tests must cover request boundaries and defaulting, API round trips,
both interval algorithms, levels producing different bounds, complete-bound
validation, handled unavailable intervals, baseline/derived exclusion,
existing model ineligibility, unexpected rollback and the intentional
development prediction-data reset in both migration directions.

Manual verification must generate otherwise identical versions at two selected
levels, inspect their saved configuration and point bounds, and confirm that
baseline and derived results have no fabricated intervals.

After implementation review, save the required redacted Step 13 record under
`docs/ai-reviews/TASK-054B/` and run:

```bash
python3 scripts/ai_review_records.py validate
```

## Documentation

Update:

- `docs/architecture/domains/FORECASTING.md` if implementation details require clarification
- `docs/architecture/data/DATA-MODEL.md`
- `docs/architecture/data/DATABASE.md`
- `db/migrations/README.md`
- `docs/architecture/diagrams/data-logical-model.puml`
- `docs/architecture/diagrams/db-physical-schema.puml`
- corresponding generated SVGs under `docs/architecture/diagrams/generated/`

## Notes For AI Agent

- Do not implement until TASK-054A and ADR-011 are accepted.
- Use only paired repository-owned SQL migrations and never alter production
  data manually.
- Add tests for every changed backend and migration behavior.
- Do not implement TASK-054C's browser UI in this task.
- Report all changed files and every verification command run.
