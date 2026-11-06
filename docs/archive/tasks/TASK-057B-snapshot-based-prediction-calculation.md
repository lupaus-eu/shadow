# TASK-057B Snapshot-Based Prediction Calculation

## Source Plan

Approved plan: "Background Prediction Requests", accepted for task creation on
2026-09-07. This task provides calculation isolation for background execution.

Dependency: [TASK-057A](TASK-057A-background-predictions-architecture.md) and its
accepted ADR-012. [TASK-057C](TASK-057C-durable-prediction-requests-worker.md)
depends on this refactor. Task creation does not authorize implementation now.

## Goal

Separate prediction input preparation, calculation, and result persistence so
the worker can calculate from detached, serializable inputs without accessing
live source data. Preserve existing synchronous behavior until TASK-057C
switches the create route to queue submission.

## Requirements

- Refactor the existing Forecasting service into explicit preparation,
  calculation, and publication boundaries, reusing existing model helpers.
- Prepare the request from one consistent database read snapshot. Capture all
  information calculation and audit output need: scenario identity, metric
  names/keys/units, effective observations and provenance, historical and future
  explanatory features, date grids, eligibility/reasons, seasonality, cutoff,
  confidence level, deterministic model configuration, and creator attribution.
- Detach calculation inputs from SQLAlchemy sessions and ORM instances. Use an
  explicit validated, serializable internal structure suitable for persistence
  and child-process execution, with snapshot format identification.
- Capture derived formulas and each referenced metric's stable key and short
  name at submission. Replace the current calculation-time `Timeserie` lookup
  with snapshot-based resolution and already calculated source results.
- Calculate normal results before dependent derived results. Preserve existing
  missing/unavailable/invalid-source behavior and scenario isolation.
- Make calculation consume only the prepared snapshot and return detached
  results. It must neither query source tables nor commit saved versions.
- Persist existing version/target/result/point structures from the prepared
  inputs and calculated output in a single transaction. Keep all-or-nothing
  rollback on unexpected calculation or persistence failure.
- Retain preflight and synchronous create response contracts in this task;
  exercise the new boundaries through the existing create service until
  TASK-057C replaces HTTP calculation with enqueueing.
- Preserve all five result kinds, deterministic settings, interval methods,
  cross-validation metadata, source and input audit snapshots, and current
  pair/period/history/point limits. Do not change dependency manifests or locks.

## Acceptance Criteria

- [ ] Prepared inputs survive serialization/deserialization with all data
      necessary to reproduce normal and derived results and audit snapshots.
- [ ] Calculation works after the preparation session is closed and performs
      no source database reads or writes.
- [ ] Source edits or soft deletion after preparation cannot alter calculated
      values, derived-reference resolution, or saved provenance.
- [ ] Formula and referenced short-name changes after preparation cannot
      change the prepared prediction's result.
- [ ] Existing representative forecast values, intervals, eligibility,
      confidence defaults/bounds, and resource limits remain covered.
- [ ] Expected model/interval limitations retain their current semantics;
      unexpected failure leaves no partial version.
- [ ] Existing preflight, create, list, and detail HTTP contracts are unchanged.
- [ ] No queue, worker, schema migration, frontend change, or dependency is added.

## Out Of Scope

- Durable request storage, queue APIs, cancellation, worker supervision, or
  process transport; these belong to TASK-057C.
- New model behavior, tuning, metrics, progress reporting, or revised limits.
- Frontend and deployment changes; TASK-057D and TASK-057E own those areas.

## Implementation Notes

Read `AGENTS.md`, `docs/architecture/overview.md`, ADR-007 through ADR-012,
`docs/architecture/domains/FORECASTING.md`, `docs/architecture/domains/ORG_STATES.md`,
`docs/architecture/domains/ORG_TWIN_STRUCTURE.md`, `docs/architecture/data/DATA-MODEL.md`,
`docs/architecture/data/DATABASE.md`, and `docs/operations/testing.md`.

Primary implementation is `backend/app/api/v1/predictions/service.py` and its
existing model/schema helpers. Introduce internal modules where needed to keep
the boundaries reviewable. Existing API behavior remains the regression
baseline; do not turn internal snapshot types into new public response fields.

## Testing

Required: backend unit/API tests, snapshot round-trip and detached-calculation
tests, disposable PostgreSQL verification of consistent preparation during
source edits, lint, and typecheck.

Cover numeric and derived targets, independent scenario histories, short-name
mapping, deleted/changed source rows, intervals and expected failures, and
transaction-wide rollback. Use deterministic fixtures and existing numeric
tolerances rather than tests that merely mirror the new structure.

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Run PostgreSQL-dependent tests with the disposable database configuration from
`docs/operations/testing.md`; a skipped integration module is not evidence of passing it.

Not applicable: frontend checks, Compose checks, and migration round trips,
because this task changes none of those surfaces.

## Documentation

Update Forecasting implementation guidance and `docs/operations/testing.md` for the
reusable snapshot/calculation harness where needed. Keep runtime status
synchronous until TASK-057C. Update affected diagrams and SVGs if the refactor
changes documented component boundaries.

## Notes For AI Agent

- Implement only after the architecture prerequisite is accepted and this task
  is requested. Do not implement downstream queue or UI work.
- Add regression tests for changed application code; add no dependencies.
- Record each eventual Step 13 review under `docs/ai-reviews/TASK-057B/` and run
  `python3 scripts/ai_review_records.py validate` from the repository root.
- Report changed files and all verification performed.
