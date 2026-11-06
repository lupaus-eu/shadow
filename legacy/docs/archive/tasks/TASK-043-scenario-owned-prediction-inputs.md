# TASK-043 Scenario-Owned Prediction Inputs

## Source Plan

Developer-approved plan: "Scenario-Owned Prediction Inputs". Scenario forks
now copy active events, timeseries and dated timeserie values through the
selected organisation-state date. Forecasting must consequently use only each
selected target scenario's own data, without a Reality dependency.

## Goal

Amend the Forecasting Domain so every selected scenario trains models and
calculates baselines solely from that scenario's own active numeric timeserie
values. A copied scenario must therefore be independently forecastable from
the values copied during a scenario fork.

Reality becomes an ordinary eligible prediction target. It remains available
as an optional, live manually entered comparison series in the Predictions UI,
but it must not be read as a source for another scenario's prediction.

## Requirements

### Architecture and domain policy

- Add `docs/adr/0009-scenario-owned-prediction-inputs.md` before
  changing implementation. It must supersede the Reality-source and
  target-scenario-override rules in ADR-007 and ADR-008, while retaining the
  existing Forecasting ownership, model stack, routes, synchronous execution
  model and resource limits.
- The selected target scenario is the sole source of observed metric values,
  target history, baseline inputs and model-training targets. Do not read,
  merge, fall back to, or impute from Reality or any other scenario.
- Permit every active in-organisation scenario, including protected Reality,
  as a prediction target. Preserve authentication, organisation-boundary and
  active-row validation.
- Retain only target-scenario events and graph history as known explanatory
  inputs. Do not change feature definitions or model algorithms.

### Backend, persistence and API

- Replace cutoff value `allCurrentReality` with `allCurrentScenario`; retain
  `asOfStart`. `asOfStart` includes target-scenario observations strictly
  before the first generated metric period; `allCurrentScenario` includes all
  current active observations from that target scenario.
- Remove Reality lookup, matching-metric compatibility checks, merged-history
  construction, target-overrides-Reality logic and the prohibition on Reality
  targets from the Forecasting service.
- Determine eligibility from the selected target metric alone: it must be an
  active numeric timeserie with finite values that form a contiguous history
  on its own time-unit grid under the selected cutoff. Keep existing normal
  ineligibility and resource-limit behavior otherwise unchanged.
- Store `observationPolicy: "targetScenarioOnly"` in each new target source
  snapshot. Every effective observation must be recorded as sourced from
  `targetScenario`.
- Remove `reality_scenario_key` from `PredictionTarget`,
  `realityScenarioId` from detail responses and backend schemas, and all
  related frontend DTO fields. Do not change prediction route paths or model
  result response behavior.
- Add paired migrations:
  `db/migrations/011_alter_prediction_target_observation_source.sql` and
  `db/migrations/011_alter_prediction_target_observation_source.down.sql`.
  The up migration replaces the cutoff constraint with
  `asOfStart`/`allCurrentScenario` and drops
  `prediction_targets.reality_scenario_key`. The down migration restores the
  original cutoff constraint and non-null Reality-source column. Existing
  development prediction data need not be preserved.
- Do not add dependencies or modify existing migration files.

### Predictions UI

- Include Reality in the generation target selector and remove copy that says
  Reality is never a prediction target.
- Rename the control and descriptive text from Reality cutoff / All current
  Reality to Observation cutoff / All current scenario. Submit only the new
  cutoff value.
- Keep the optional live Reality chart overlay. It must remain visibly
  identified as current manually entered comparison data rather than a saved
  prediction result, including when a saved prediction targets Reality.

## Acceptance Criteria

- [ ] A planning scenario with an active numeric metric and contiguous own
      values is eligible and can be predicted when Reality lacks that metric or
      has no values.
- [ ] A target's effective history, naive/seasonal-naive/average baselines,
      fitted-model inputs and saved source snapshot contain no Reality or
      other-scenario values.
- [ ] Reality is accepted as a target and forecasts only from its own values.
- [ ] `asOfStart` and `allCurrentScenario` apply only to target-scenario
      observations and reject the removed `allCurrentReality` API value.
- [ ] New source snapshots use `targetScenarioOnly`, mark all effective
      observations as `targetScenario`, and prediction detail responses expose
      no `realityScenarioId` field.
- [ ] A fork whose active metric values were copied through its selected state
      date can be forecast independently; subsequent source-scenario edits do
      not change that fork's prediction inputs.
- [ ] Migration 011 applies and its paired down migration rolls back on a
      disposable PostgreSQL database.
- [ ] Reality is selectable in the Predictions UI, and the renamed cutoff
      value is sent in preflight and create requests.
- [ ] The live Reality overlay remains distinguishable from saved prediction
      lines and works when Reality is among the selected targets.
- [ ] No model-library, route, synchronous-execution, work-limit,
      scenario-fork or dependency change is introduced.

## Out Of Scope

- Changes to forecasting algorithms, result kinds, deterministic model
  configuration, feature definitions, work limits or execution model.
- Changes to scenario-fork copying behavior, timeserie CRUD, event CRUD or
  graph-copy behavior.
- Prediction exports, sharing, deletion, background jobs, queues, retries or
  scheduling.
- Preserving existing development prediction records or supporting the removed
  API cutoff value.
- Revising historical task files, including TASK-041A, TASK-041B, TASK-041C
  and TASK-042.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0007-predictions-forecasting-domain.md
docs/adr/0008-target-scenario-observation-overrides.md
docs/architecture/domains/FORECASTING.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
db/migrations/README.md
docs/operations/testing.md
docs/archive/tasks/TASK-043-scenario-owned-prediction-inputs.md
```

- Create and accept ADR-009 before applying the behavior change; it is the
  current architecture decision for this task.
- Keep source-data isolation enforced in the backend service. Frontend target
  selection is not the security boundary.
- Continue persisting immutable source and input snapshots with prediction
  targets. Forecasting must not write prediction points to `timeserie_values`.
- Update SQLAlchemy models, Pydantic schemas, backend service tests, frontend
  API types, Predictions UI and chart tests together with the migration.
- Regenerate committed SVGs from the changed logical and physical PlantUML
  sources using the repository's established diagram-rendering workflow.
- Use the paired migration convention. The down migration is intentionally
  allowed to discard development prediction data when restoring the removed
  non-null column.

## Testing

Required:

- [ ] Frontend tests
- [ ] Backend tests
- [ ] Migration integration tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest tests/test_predictions_api.py
uv run pytest
uv run pyright

cd frontend
pnpm lint
pnpm test
pnpm build
```

Backend tests must cover scenario-only eligibility and baseline/model history,
Reality-as-target behavior, cutoff behavior, absence of cross-scenario reads,
source-snapshot/API provenance, and forked-timeserie independence. Migration
integration tests must apply all migrations, verify the changed prediction
schema, run migration 011 down, and reapply it on disposable PostgreSQL.

Frontend tests must cover selecting Reality as a target, the renamed cutoff
payload and labels, removed Reality-source DTO field, and the distinct live
Reality overlay.

Manual verification must create or fork a scenario with its own numeric
history while Reality lacks the equivalent metric, generate a prediction for
that scenario, generate one for Reality, and confirm the optional live Reality
overlay remains distinct from saved result lines.

## Documentation

Update current-state documentation:

- `docs/adr/0009-scenario-owned-prediction-inputs.md`
- `docs/adr/0007-predictions-forecasting-domain.md`
- `docs/adr/0008-target-scenario-observation-overrides.md`
- `docs/architecture/domains/FORECASTING.md`
- `docs/architecture/data/DATA-MODEL.md`
- `docs/architecture/data/DATABASE.md`
- `db/migrations/README.md`
- `docs/architecture/diagrams/data-logical-model.puml`
- `docs/architecture/diagrams/db-physical-schema.puml`
- affected files under `docs/architecture/diagrams/generated/`

Do not modify historical task specifications. Update other current-state
documentation only if implementation reveals a directly affected Forecasting
or Predictions UI description.

## Notes For AI Agent

- Implement only this task's scope.
- Do not add dependencies.
- Do not edit production databases manually; use migration 011 and its paired
  down migration.
- Add or update tests for every application-code change.
- Report changed files and all verification commands run.
