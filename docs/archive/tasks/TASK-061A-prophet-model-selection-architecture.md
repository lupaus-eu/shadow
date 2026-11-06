# TASK-061A Prophet And Model Selection Architecture

## Source Plan

Approved plan: "Prophet model + per-run model selection in Predictions".

Developer decisions recorded with the plan:

- Prophet is fed the metric history plus the existing known features
  (`_known_features`) as extra regressors.
- Each model, including every baseline, is individually selectable for a
  prediction run. All six models are selected by default. At least one model
  is required.
- Approving the plan approves the new `prophet` backend dependency and its
  transitive dependencies (`cmdstanpy`, `holidays`, `matplotlib`, among others).

This is the first task in the sequence. TASK-061B and TASK-061C depend on the
decision recorded here.

## Goal

Record the architecture decision for adding Meta's Prophet as a sixth
Forecasting result kind, and for letting each prediction version run only a
user-selected subset of result kinds. Do this before any schema, backend or UI
change.

## Requirements

- Create and accept `docs/adr/0014-prophet-and-model-selection.md`.
- The ADR defines a new result kind `prophet`:
  - It uses the `prophet` Python package. Fitting is MAP (`mcmc_samples=0`), with
    a fixed seed and a fixed `uncertainty_samples`.
  - Input is the target scenario's history (ADR-009). Each `_known_features`
    column is added as a regressor. Zero-variance features are dropped. Future
    regressor values come from the prediction periods.
  - Seasonality depends on time unit:
    - weekly seasonality only for `day`
    - yearly seasonality for `day`, `week` and `month`
    - daily seasonality always off
  - At least 12 observations are required, as for MLForecast.
  - Cross-validation MAE uses 3 expanding windows with `h=1`, so it can be
    compared with MLForecast.
  - Intervals are Prophet's native intervals with
    `interval_width = confidence_level / 100`. They follow ADR-011's complete,
    ordered-bounds invariant.
  - When an expected fit fails or history is too short, the `prophet` result is
    `ineligible` with a user-safe reason. The rest of the version is unaffected.
- The ADR defines per-version model selection:
  - `modelKinds` is a non-empty list with no duplicates. Each entry is a
    supported result kind.
  - When the API request omits `modelKinds`, all supported kinds are used.
  - The selection is frozen into the request input snapshot and recorded in
    `prediction_versions.model_configuration`. Versions stay immutable.
  - Only the selected kinds are calculated and persisted. Models that are not
    selected are never fitted.
  - Derived metrics are calculated for the selected kinds only.
  - Queued snapshots without a selection are calculated with the legacy five
    kinds.
  - The prediction-work limit (`MAX_POINTS`) counts selected kinds only.
- The ADR records the runtime consequences:
  - The backend/worker image grows.
  - Importing Prophet makes worker start-up slower.
  - CmdStan writes temporary files into the read-only worker's `/tmp` tmpfs.
  - A prebuilt manylinux wheel must be available for the build host's
    architecture.
  - No new service, queue or worker is added.
- Amend ADR-007 (the result-kinds table) and ADR-011 (the models that support
  intervals) with "Amended by ADR-014" cross-references.
- Update the Forecasting summary in `docs/architecture/overview.md` and the rules in
  `docs/architecture/domains/FORECASTING.md`. They must list six result kinds and describe
  model selection.

## Acceptance Criteria

- [ ] ADR-014 records the Prophet configuration, regressors, seasonality rules,
      minimum history, CV method, interval method and failure behavior.
- [ ] ADR-014 records model-selection validation, the default, snapshot and
      version recording, derived-metric behavior, legacy-snapshot behavior and
      the work-limit change.
- [ ] ADR-014 records the dependency approval and the runtime consequences.
- [ ] ADR-007, ADR-011, `docs/architecture/overview.md` and `FORECASTING.md` are consistent
      with ADR-014.
- [ ] TASK-061B and TASK-061C can be implemented without a new architecture or
      statistical-method choice.
- [ ] No application code, migration, ORM model, API schema or frontend source
      is changed.

## Out Of Scope

- Any code, migration, dependency or runtime configuration change.
- Prophet holiday calendars, MCMC sampling, changepoint tuning and per-request
  model hyperparameters.
- Saving per-user or per-organisation default model selections.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0007-predictions-forecasting-domain.md
docs/adr/0009-scenario-owned-prediction-inputs.md
docs/adr/0010-derived-metrics.md
docs/adr/0011-prediction-intervals.md
docs/adr/0012-background-prediction-requests.md
docs/adr/0013-shared-entra-local-https-deployment.md
docs/architecture/domains/FORECASTING.md
```

Keep this task documentation-only. TASK-061B updates the physical data
documentation and data diagrams together with the implemented migration.

## Testing

Required:

- [ ] Manual verification (documentation consistency review)
- [ ] AI review record

Not applicable:

- [x] Reason: documentation-only task; there are no application tests.

```bash
python3 scripts/ai_review_records.py validate
```

## Documentation

Update:

- `docs/adr/0014-prophet-and-model-selection.md` (new)
- `docs/adr/0007-predictions-forecasting-domain.md`
- `docs/adr/0011-prediction-intervals.md`
- `docs/architecture/overview.md`
- `docs/architecture/domains/FORECASTING.md`

## Notes For AI Agent

- Do not change code in this task.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-061A/`.
- Report all changed files and every verification command run.
