# TASK-047 Derived Metrics And Short-Name Editing

## Source Plan

Approved plan: "Derived Metrics and Editable Timeserie Short Names", including
the approved amendment that derived formulas are editable and that changes to
normal metric values, including removed values, recalculate dependent derived
metrics, and that derived-metric names and units are editable.

## Goal

Let users assign and edit an existing Timeserie short name in the Structure
Timeserie status card. A short name becomes immutable while it is referenced
by an active derived-metric equation.

Add scenario-scoped derived numeric metrics to the Metrics workspace. A user
can create a derived metric from a formula containing normal Timeserie short
names, edit its name, unit and formula later, and view its calculated values.
Derived values are calculated from their equations and are never manually
editable or predicted by fitting a model to the derived metric itself.

## Requirements

### Architecture and persistence

- Create and accept an ADR defining the derived-metric ownership, materialized
  value policy, short-name locking, and Forecasting behavior before changing
  application architecture or schema.
- Add paired migration `013_create_derived_metrics.sql` and
  `013_create_derived_metrics.down.sql`.
- Add `timeserie_values.is_derived BOOLEAN NOT NULL DEFAULT FALSE`.
- Add `derived_metrics_equations`, owned by the Organisation States Domain,
  with one active equation per derived Timeserie, its formula text, its
  validated referenced normal-Timeserie IDs, required audit fields,
  soft-delete fields, foreign keys, and active lookup indexes.
- Store calculated derived values in `timeserie_values` with
  `is_derived=true`. Existing manually maintained values remain
  `is_derived=false`.
- Preserve derived Timeseries, equations, reference mapping, and derived-value
  provenance during scenario copy. Existing source-state cutoff behavior still
  applies.

### Timeserie API and validation

- Add authenticated unsafe endpoint:

  ```text
  PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries/{timeserie_key}/short-name
  ```

  It accepts `{ "shortName": string | null }`, applies the existing trimmed
  equation-safe identifier and active-scenario uniqueness rules, and returns
  the updated Timeserie.
- Add authenticated unsafe endpoints:

  ```text
  POST  /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/derived-metrics
  PATCH /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/derived-metrics/{timeserie_key}
  ```

  Creation accepts `{ "name": string, "unit": string | null, "formula": string }`.
  Updates accept one or more of `name`, `unit`, and `formula`; reject an empty
  update payload. Both return the updated derived Timeserie.
- Generate a stable Timeserie key for a derived metric. Its `valueUnit` is
  `number`, its unit is user-specified optional text, and its `timeUnit` is inferred from the
  validated operands. A formula edit updates the inferred time unit atomically
  when its referenced metrics change.
- Apply the existing optional-text trimming convention to derived units: blank
  input is stored as `NULL` and returned as the established empty API value.
- Extend Timeserie list/get/create/update responses and frontend DTOs with
  `isDerived`, `derivedFormula` when applicable, and `shortNameEditable`.
- Reject any short-name change, including clearing, with HTTP `409` while an
  active equation references that Timeserie. Once a formula edit removes a
  reference, its former source short name becomes editable again.
- Formulas may reference only active, normal, numeric Timeseries in the same
  scenario that have short names. Reject unknown, duplicate/ambiguous,
  non-numeric, derived, cross-scenario, or mixed-time-unit references.
- Support finite numeric literals, whitespace, parentheses, unary signs,
  `+`, `-`, `*`, `/`, `**`, and `^`; normalize `^` to exponentiation. All
  operands must share one time unit. Do not add resampling or
  derived-to-derived equations.

### Calculation and lifecycle

- Create or edit the equation, update its reference metadata, and recalculate
  its values in one transaction.
- On every successful normal Timeserie values replacement, including omitted
  dates being soft-deleted, recalculate every affected active derived metric
  in the same transaction.
- Materialize a derived value only for a date present in every referenced
  normal Timeserie. Soft-delete stale derived values no longer calculable;
  omit dates that divide by zero or produce a non-finite result.
- Keep normal Timeserie value replacement, blank-cell removal, row/bulk save,
  CSV import and individual value deletion behavior available even when the
  Timeserie is referenced by a derived equation.
- Reject manual value replacement for a derived Timeserie. Keep derived rows
  read-only in Metrics.
- Reject deletion of an entire normal Timeserie while an active equation
  references it. Deleting a derived Timeserie must soft-delete its equation
  and its active derived values.

### Frontend

- Add a `Set shortname` button and inline editor to existing Timeserie status
  cards. Prefill it with the current short name and show an explanatory locked
  state when `shortNameEditable` is false.
- Add a Metrics-page create-derived-metric panel with name, optional unit and
  formula fields, supported-syntax guidance, and available normal numeric
  short names.
- Add an edit-derived-metric action for derived rows, allowing name, optional
  unit and formula changes. After saving, refresh the row metadata and
  recalculated values when the formula changed.
- Render derived metric rows, formula text and calculated values, but disable
  their cell editors, row save, bulk-save participation, next-date and CSV
  import controls.
- Reuse the existing API client, workspace, form, error-notice and Metrics
  styling patterns; add no frontend dependency.

### Forecasting

- Update Forecasting preflight and creation so normal numeric metrics are
  prepared and forecast first.
- For every derived metric, calculate each result kind (`naive`,
  `seasonal_naive`, `average`, `mlforecast`, `sarima`) from the matching
  normal-input result points and the saved equation.
- Do not fit MLForecast, SARIMA, or another model directly to a derived
  metric's materialized values.
- Mark a derived result ineligible with a clear reason when an input result is
  unavailable, lacks a required period, or the formula cannot produce a finite
  value. Persist equation and input provenance in prediction snapshots.

## Acceptance Criteria

- [ ] An existing Timeserie status card exposes `Set shortname`; a valid
      unused identifier saves and is returned by Timeserie APIs.
- [ ] Invalid, duplicate active-scenario, and equation-referenced short-name
      updates receive the established validation/conflict responses.
- [ ] A source short name becomes editable after every active formula that
      referenced it is edited or soft-deleted.
- [ ] A user can create a derived numeric metric from, for example,
      `(revenue + costs) / 2`, where `revenue` and `costs` are normal metric
      short names.
- [ ] A user can create a derived metric with an optional unit and can edit its
      name, unit and formula. Formula changes update values, reference locks,
      and inferred time unit after the save succeeds; name/unit-only changes
      preserve calculated values.
- [ ] Formula validation accepts the specified operators and rejects malformed,
      unknown, non-numeric, derived, cross-scenario and mixed-time-unit
      references.
- [ ] Derived values exist only on the intersection of input dates and are
      recalculated after a referenced normal metric is saved, including when a
      previously existing source value is removed.
- [ ] Division by zero and non-finite arithmetic do not persist invalid
      derived values or leave obsolete active values behind.
- [ ] Referenced normal metrics remain editable and their values remain
      removable; derived metrics remain read-only in Metrics and reject manual
      value replacement in the API.
- [ ] An active derived equation blocks deletion of its entire normal source
      Timeserie, while deleting a derived Timeserie soft-deletes its equation
      and calculated values.
- [ ] Scenario copy preserves derived equations, remaps sources to copied
      normal Timeseries, and retains only values allowed by the existing cutoff.
- [ ] Prediction versions calculate derived targets per result kind from their
      normal metric prediction outputs without training derived metrics.
- [ ] The new migration applies and rolls back successfully on disposable
      PostgreSQL, including the provenance column and equation table.
- [ ] Relevant frontend/backend tests, lint, build and type checks pass.

## Out Of Scope

- Derived-to-derived formulas, dependency chains, or cycle handling.
- Automatic time-unit resampling, aggregation or unit conversion.
- Editing a derived metric's generated stable key.
- New dependencies, workers, queues, scheduled recalculation, or asynchronous
  prediction generation.
- Changes to authentication, authorization policy, Analysis workspace, or
  prediction-version immutability.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
tasks/TASK-047-derived-metrics-and-short-name-editing.md
docs/decisions/ADR-001-tech-stack.md
docs/decisions/ADR-007-predictions-forecasting-domain.md
docs/decisions/ADR-009-scenario-owned-prediction-inputs.md
docs/domains/ORG_STATES.md
docs/domains/FORECASTING.md
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
db/migrations/README.md
docs/TESTING.md
```

- The new ADR is a prerequisite. If it is not accepted, stop after proposing
  it; do not implement the schema or application changes.
- Keep Organisation States as the sole writer of Timeserie, equation and
  materialized-value rows. Forecasting may read the equation and normal
  prediction outputs but must not write `timeserie_values`.
- Reuse the existing short-name validation and active-scenario uniqueness
  behavior introduced by TASK-045.
- Keep public APIs on stable keys; use bigint IDs only inside persistence and
  stored equation references.
- Do not change prior migrations. Use the next linear paired migration number
  `013`.
- Update existing backend API tests in `backend/tests/test_users_organisations_api.py`
  and `backend/tests/test_predictions_api.py`, plus the relevant Structure and
  Metrics frontend tests.

## Testing

Required:

- [ ] Frontend tests for short-name editing/locking, derived-metric creation,
      name/unit/formula editing, normal-row editing while referenced, derived
      read-only controls, and accessible error states.
- [ ] Backend tests for authentication, organisation/scenario isolation,
      short-name validation/locking, formula parser and reference validation,
      derived name/unit updates, materialization, formula edits, source value
      removal, lifecycle guards, and scenario copy.
- [ ] Prediction tests for per-result-kind derivation, no direct model fitting,
      unavailable inputs, incomplete dates and invalid result arithmetic.
- [ ] PostgreSQL migration integration tests for migration `013` up/down and
      its constraints/indexes.
- [ ] Manual verification of Structure short-name editing, Metrics derived
      creation/editing, normal source value removal and Prediction results.
- [ ] Lint.
- [ ] Build.
- [ ] Typecheck.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build

cd backend
uv run ruff check .
uv run pytest
uv run pyright

MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten \
  uv run pytest tests/test_migrations_integration.py -v
```

Run the migration command only against the disposable database configuration
documented in `docs/TESTING.md`.

## Documentation

Update:

- new accepted ADR for derived-metric architecture and Forecasting policy;
- `docs/domains/ORG_STATES.md` and `docs/domains/FORECASTING.md`;
- `docs/data/DATA-MODEL.md` and `docs/data/DATABASE.md`;
- `db/migrations/README.md` migration inventory;
- `docs/diagrams/data-logical-model.puml` and generated SVG;
- `docs/diagrams/db-physical-schema.puml` and generated SVG.

## Notes For AI Agent

- Implement only this task after the prerequisite ADR is accepted.
- Add no dependencies without explicit approval.
- Use paired version-controlled migrations; never alter a production database
  manually.
- Add tests for every changed application behavior.
- Keep normal Timeserie value editing available when it triggers derived-value
  recalculation.
- Report changed files and exact verification results when finished.
