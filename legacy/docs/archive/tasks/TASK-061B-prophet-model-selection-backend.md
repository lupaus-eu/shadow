# TASK-061B Prophet And Model Selection Backend

## Source Plan

Approved plan: "Prophet model + per-run model selection in Predictions".
This task implements the backend part of ADR-014 (TASK-061A).

## Goal

Add Prophet as a sixth Forecasting result kind, and let each prediction request
choose which result kinds are calculated and persisted. Existing clients and
already-queued requests must keep working.

## Requirements

### Dependency

- Add `prophet>=1.1.6,<2` to `backend/pyproject.toml` (approved with the plan).
- Regenerate `backend/uv.lock`.
- Verify that `uv sync --frozen --no-dev` installs a prebuilt wheel, with
  CmdStan bundled, on the `python:3.12-slim` production stage
  (`backend/Dockerfile`). It must work without compilers.

### Result kinds

- Add `"prophet"` to `RESULT_KINDS` (`backend/app/api/v1/predictions/service.py`)
  and to the `ResultKind` Literal (`snapshots.py`).
- Add one constant for interval-capable kinds: `mlforecast`, `sarima` and
  `prophet`.
- Replace the inline `kind in ("mlforecast", "sarima")` checks with that
  constant.
- Add a display name for Prophet next to the existing kind display names.

### Migration

- Add `db/migrations/016_add_prophet_result_kind.sql` and
  `016_add_prophet_result_kind.down.sql`.
- The up migration recreates the `prediction_model_results.result_kind` CHECK
  so it includes `'prophet'`.
- The down migration first deletes `prophet` result rows and their points, then
  restores the five-kind CHECK.

### Request and snapshot

- Add `modelKinds: list[ResultKind]` to `PredictionRequestBase` in `schemas.py`.
  It must be non-empty with no duplicates. When it is omitted, it defaults to
  all of `RESULT_KINDS`.
- Add `model_kinds` (alias `modelKinds`, the stored JSON key) to
  `PredictionInputSnapshot`. When the key is missing, it defaults to the legacy
  five kinds, so queued `shadow.prediction-input.v1` snapshots calculate
  exactly as before.
- Make `prepare_prediction_snapshot` copy the selection into the snapshot.

### Calculation and persistence

- Make `_calculate_normal_result_set` calculate only the selected kinds.
  Unselected models must never be fitted.
- Make `_calculate_derived_result_set` iterate only the selected kinds.
- In `persist_prediction`, the expected kinds are the snapshot's kinds.
- Raise `MAX_POINTS` from 100,000 to 110,000 (ADR-014), and make the estimate
  use the number of selected kinds.
- `_model_configuration` records `modelKinds`, the `prophet` section and
  `predictionIntervals.prophet` with exactly the keys in ADR-014's "Recorded
  Configuration" table.

### Prophet result

Implement `_prophet_result(row, confidence_level)` following ADR-014:

- Use lazy imports and silence the `cmdstanpy` and `prophet` loggers.
- Build `ds`/`y` plus the known-feature regressors, dropping zero-variance
  features.
- Set seasonality by time unit and fit with MAP and `fit(..., seed=41)`.
- Call `numpy.random.seed(41)` immediately before every Prophet `predict`,
  including each cross-validation window.
- Use native intervals at the selected level. Every point must satisfy
  `lower <= value <= upper`.
- Compute the 3-window CV MAE.
- Return an `ineligible` result when there are fewer than 12 observations
  ("Prophet needs at least 12 contiguous observations.") or an expected fit
  failure occurs ("Prophet cannot fit this metric."). Expected failures are
  `ValueError` and the `RuntimeError` raised by `cmdstanpy`. Never interpolate
  exception text into a reason.
- A target that is not eligible (for example, it needs a manual seasonal
  period) keeps the existing target-level behavior: every selected kind,
  Prophet included, is ineligible with the target's reason.

### Worker child process

Implement ADR-014's child stop procedure in `worker.py`:

- The supervisor creates a private temporary directory under `/tmp` for each
  child and passes its path as an extra `ChildTarget` argument. Do not change
  the supervisor's `os.environ`.
- The calculation child calls `os.setsid()` as the first action of its entry
  function. Right after that, before any model import or temporary-file use, it
  sets `TMPDIR` and `MPLCONFIGDIR` to the given path and sets
  `tempfile.tempdir = None`.
- `_stop_child` sends `SIGTERM` to the child directly (`child.terminate()`) and
  to process group `child.pid` (`os.killpg(child.pid, ...)`), waits at most
  `TERMINATION_GRACE_SECONDS`, then sends `SIGKILL` the same two ways, and
  reaps the child. Never use `os.getpgid(child.pid)`. Ignore
  `ProcessLookupError` from `os.killpg`.
- After reaping the child on every outcome, including a child that exited or
  crashed on its own (the plain `child.join()` path), send
  `os.killpg(child.pid, SIGKILL)` and ignore `ProcessLookupError`. Only then
  remove the temporary directory, tolerating errors
  (`shutil.rmtree(..., ignore_errors=True)`).
- Update the injected test child targets for the new `ChildTarget` signature,
  and test a stop that happens before the child has called `os.setsid()` and a
  child that crashes while a grandchild process in its group is still
  running.

### Runtime

- Check how much of the production worker's `/tmp` tmpfs CmdStan uses
  (`docker-compose.production.yml`, currently 64 MB with `read_only: true`).
  Raise it if needed; 256 MB is proposed. The local `docker-compose.yml`
  worker has no tmpfs and is not read-only; leave it as it is.
- Check whether worker health-check timing needs a change because of Prophet's
  import time.
- Record the measured image size difference in this task.

### Runtime Measurements

Measured 2026-10-05 on the local x86_64 Docker Engine, with
`docker build -f backend/Dockerfile --target production` for the branch base
commit and for this change:

- Production backend image: 572,464,175 bytes before, 692,760,329 bytes after,
  an increase of 120,296,154 bytes (about 115 MiB, +21%). `uv sync --frozen
  --no-dev` installed the prebuilt `prophet-1.5.0` manylinux wheel with bundled
  CmdStan; `cmdstanpy` is 1.3.0. No compiler was needed.
- Under `read_only`, `cap_drop: [ALL]`, `no-new-privileges` and uid 10001,
  the image imports `prophet` (about 2.7 s) and the real calculation child
  completes Prophet with available points, intervals and CV MAE for a daily
  target (730 observations, 366 periods) and a monthly target.
- `/tmp`: input JSON is deleted after each fit, but `cmdstanpy` keeps each fit's
  output directory until the child exits. The child's private directory grows
  by about 0.96 MB per Prophet target (four fits) at the 10,000-observation
  limit, so 50 such targets need about 48 MB, which is too close to 64 MB. The
  worker tmpfs is raised to 256 MB in `docker-compose.production.yml`.
- Stopping the real calculation child during a 10,000-observation Prophet fit
  in the image leaves no process in its group and removes its private
  directory (0.01 s after the stop).
- Worker health check: `python -m app.api.v1.predictions.worker health-check`
  does not import Prophet or pandas; the worker module import takes 1.6-1.8 s
  in both images. Health-check timing is unchanged.
- Prophet fit time depends on data. A 10,000-observation daily target takes
  about 57 s (four fits). Short monthly histories with ADR-014's fixed yearly
  seasonality can take 3-13 s per fit (for example 24 or 36 monthly
  observations).

## Acceptance Criteria

- [x] A request without `modelKinds` produces all six kinds, Prophet included.
- [x] A request with a subset persists only those kinds. That includes subsets
      without baselines and subsets with only baselines.
- [x] An empty `modelKinds`, duplicates or an unknown kind is rejected with 422.
- [x] On a sufficiently long series, Prophet returns available points, complete
      ordered intervals at the selected level and a CV MAE.
- [x] Prophet is `ineligible` on short history or on a handled fit failure, and
      the other kinds in the version are unaffected.
- [x] Derived metrics work with a subset of kinds.
- [x] A legacy snapshot without `model_kinds` is calculated and persisted with
      the five legacy kinds.
- [x] `model_configuration` records `modelKinds` and the Prophet settings with
      the keys defined in ADR-014.
- [x] The point limit is 110,000 and counts only selected kinds; a request at
      50 pairs × 366 periods with all six kinds passes.
- [x] Prophet fit failures produce the fixed reason and never contain
      exception text; a `cmdstanpy` `RuntimeError` makes only Prophet
      ineligible.
- [x] Two identical requests produce identical Prophet points and bounds.
- [x] Cancelling or stopping during a Prophet fit leaves no running CmdStan
      process and no per-child temporary directory, within five seconds.
- [x] A calculation child that crashes on its own leaves no running process
      from its group and no per-child temporary directory.
- [x] Migration 016 runs up and down in a disposable PostgreSQL environment.
- [x] The production image builds, imports `prophet` and completes a Prophet
      fit under `read_only: true` with the configured `/tmp` tmpfs.

## Out Of Scope

- Frontend changes (TASK-061C).
- Prophet holidays, MCMC sampling and user-tunable hyperparameters.
- Changes to the other models' algorithms or configuration.
- A new worker, queue or service.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0002-database-migrations.md
docs/adr/0007-predictions-forecasting-domain.md
docs/adr/0011-prediction-intervals.md
docs/adr/0012-background-prediction-requests.md
docs/adr/0014-prophet-and-model-selection.md
docs/architecture/domains/FORECASTING.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
db/migrations/README.md
docs/operations/testing.md
```

- Model `_prophet_result` on `_mlforecast_result` and `_sarima_result`. Reuse
  `_known_features`, the existing interval validation and the existing
  `_GeneratedResult` and `_calculated_result` helpers. Do not copy
  `_mlforecast_result`'s exception-text reason; Prophet reasons are fixed
  strings (ADR-014).
- The worker runs the calculation in a spawned child process without DB
  access. Prophet must not need network access or write outside `/tmp`.
- Run migrations only with `backend/migrate.py`.

## Testing

Required:

- [x] Backend tests (`backend/tests/test_predictions_api.py`)
- [x] Integration tests (`test_predictions_postgresql_integration.py` and the
      migration tests)
- [x] Manual verification (production image import and fit)
- [x] Lint
- [x] Typecheck

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
python3 scripts/ai_review_records.py validate
```

## Documentation

Update:

- `docs/architecture/domains/FORECASTING.md`, if implementation details need clarifying
- `docs/architecture/data/DATA-MODEL.md`
- `docs/architecture/data/DATABASE.md`
- `db/migrations/README.md`
- the relevant `docs/architecture/diagrams/*.puml` files and their generated SVGs, if they
  list result kinds
- `docs/architecture/diagrams/component-forecasting-prediction-requests.puml` and
  `docs/architecture/diagrams/state-forecasting-prediction-request.puml` and their generated
  SVGs: describe the child process-group stop and the per-child temporary
  directory

## Notes For AI Agent

- Do not start until TASK-061A and ADR-014 are accepted.
- Do not implement TASK-061C's UI in this task.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-061B/`.
- Report all changed files and every verification command run.
