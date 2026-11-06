# TASK-041A Predictions Architecture And Domain

## Source Plan

Approved plan: "Prediction Feature Task Specifications", based on the approved
Predictions workspace plan.

This is the first task in the Predictions feature sequence. TASK-041B and
TASK-041C depend on the ADR and domain boundary defined here.

## Goal

Define and document the Forecasting Domain before prediction persistence,
modelling APIs or the Predictions UI are implemented. The decision must make
the chosen modelling libraries, immutable result lifecycle, source-data
boundaries and synchronous MVP execution explicit.

## Requirements

- Create a new ADR for the Forecasting Domain and its modelling approach.
- The ADR must decide and justify:
  - MLForecast with a deterministic scikit-learn `RandomForestRegressor` for
    the primary machine-learning forecast;
  - Statsmodels SARIMAX for seasonal modelling;
  - rolling-origin cross-validation where enough history exists;
  - immutable, uniquely named prediction versions;
  - synchronous API-request execution for the MVP and documented server-side
    prediction-work limits;
  - no background-job system in this MVP.
- Add `docs/architecture/domains/FORECASTING.md` and register it in `docs/architecture/domains/DOMAIN.md`.
- Define that the Forecasting Domain owns derived prediction versions, target
  metric prediction records, per-model result metadata and prediction points.
- Define the data boundary:
  - the active protected `reality` scenario supplies the only observed target
    values used for training and baselines;
  - each target scenario contributes only its own events and graph structure;
  - no values from another non-Reality scenario may enter a prediction;
  - every result retains immutable audit and source-input metadata.
- Document the five result kinds and their semantics:
  - MLForecast;
  - naive;
  - seasonal naive, repeating the observation one seasonal cycle ago;
  - average over all Reality history available under the selected cutoff mode;
  - SARIMA.
- Document automatic seasonality detection, manual per-metric fallback, the
  two user-selected Reality cutoff modes, and per-model ineligibility as a
  normal stored result state.

## Acceptance Criteria

- [ ] A Forecasting Domain ADR exists and is internally consistent with
      `docs/architecture/overview.md` and ADR-001.
- [ ] The ADR explicitly identifies MLForecast, RandomForestRegressor and
      SARIMAX, plus their execution and resource-boundary decisions.
- [ ] `docs/architecture/domains/FORECASTING.md` defines ownership, dependencies, data
      sourcing, output semantics, immutability and audit expectations.
- [ ] `docs/architecture/domains/DOMAIN.md` lists the Forecasting Domain and its ownership
      boundary.
- [ ] The documentation explicitly prohibits using other scenario values as
      prediction targets or training data.
- [ ] The documentation distinguishes stored ineligible model results from
      unexpected generation failures.
- [ ] No application code, dependency manifest, migration, API route, UI or
      generated diagram artifact is changed.

## Out Of Scope

- Database tables, ORM models, migrations and data-model diagrams.
- Backend dependencies, feature engineering, model fitting or API routes.
- Predictions workspace tab and any frontend API client or chart.
- Background jobs, queues, retries, scheduling or asynchronous workers.
- Changes to existing Analysis workspace behavior.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0001-tech-stack.md
docs/architecture/domains/DOMAIN.md
docs/architecture/domains/AI.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/operations/testing.md
docs/archive/tasks/TASK-041A-predictions-architecture-domain.md
```

- Forecasting is a new derived-data domain, not an extension of the current
  candidate AI Domain, whose scope is document-oriented classifications,
  summaries and extractions.
- The ADR and domain document are the required source of truth for TASK-041B
  and TASK-041C. Do not start those tasks until this task has been reviewed and
  accepted.
- This is a documentation-only task. Do not introduce libraries, code or
  database changes while documenting the decision.

## Testing

Required:

- [ ] Manual verification

Not applicable:

- [ ] Frontend tests: no frontend code changes.
- [ ] Backend tests: no backend code changes.
- [ ] Integration tests: no runtime behavior changes.
- [ ] Lint: no repository Markdown lint command is configured.
- [ ] Build: no build inputs change.
- [ ] Typecheck: no typed source changes.

Manual verification must confirm:

- ADR links and domain-document links resolve.
- The five result kinds have the intended, non-overlapping definitions.
- The Reality-only and scenario-isolated input rules are unambiguous.
- TASK-041B and TASK-041C can use the documents without making a new
  architecture decision.

## Documentation

Update:

- `docs/adr/0007-predictions-forecasting-domain.md`
- `docs/architecture/domains/FORECASTING.md`
- `docs/architecture/domains/DOMAIN.md`

## Notes For AI Agent

- Read the listed source documents before editing.
- Keep the scope to the ADR and domain documentation.
- Do not add dependencies or implementation artifacts.
- Report the documents created and the validation performed.
