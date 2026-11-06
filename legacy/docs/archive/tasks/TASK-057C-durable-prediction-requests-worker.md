# TASK-057C Durable Prediction Requests And Worker

## Source Plan

Approved plan: "Background Prediction Requests", accepted for task creation on
2026-09-07. Confirmed choices are a PostgreSQL queue, one globally active
calculation, submission-time inputs, prompt cancellation, reusable names after
failure/cancellation, and no automatic retries.

Dependencies: [TASK-057A](TASK-057A-background-predictions-architecture.md) and
[TASK-057B](TASK-057B-snapshot-based-prediction-calculation.md).
[TASK-057D](TASK-057D-prediction-request-ui.md) consumes this API;
[TASK-057E](TASK-057E-prediction-worker-runtime-qa.md) wires its runtime.
Task creation does not implement these changes.

## Goal

Persist validated prediction requests, calculate them in a supervised worker,
and expose reliable status and cancellation APIs. Preserve completed versions
and publish new versions only after successful whole-request calculation.

## Requirements

### Persistence and submission

- Add a Forecasting-owned `prediction_requests` table and SQLAlchemy model
  with stable request key, organisation, prediction name, immutable input and
  configuration snapshot, lifecycle state, submission/start/finish timestamps,
  submitter, cancellation actor/time, worker ownership, safe failure reason,
  and optional completed-version reference.
- Add paired migrations using the next unused linear migration number. Preserve
  all saved prediction versions and their owned rows in both directions; do not
  backfill request records for old versions or repeat ADR-011's data reset.
  Document that down removes request history and requires stopped workers.
- Enforce valid states, ownership/link relationships, and case-insensitive
  active-name uniqueness with database constraints/indexes. Index active queue
  ordering and organisation request-list queries.
- Use TASK-057B to validate and snapshot submission inputs without model fitting.
  Commit the queued request before returning `202 Accepted`. Keep preflight
  synchronous and preserve existing validation, work limits, and eligibility.
- Reserve names for queued, running, and cancelling requests, and permanently
  for saved versions. Serialize name admission and final publication per
  organisation so no concurrency window permits duplicate active/completed
  names. Cancelled/failed history does not block reuse; duplicate names return
  the existing user-safe conflict behavior.

### Public API

Paths below are relative to `/api/v1/organisations/{organisation_key}`.

| Method and path | Contract |
| --- | --- |
| `POST /predictions` | Existing payload; `202 Accepted` with request summary and a `Location` status URL. No calculation in the HTTP request. |
| `GET /prediction-requests` | All active requests plus the 50 most recently finished requests for the organisation. |
| `GET /prediction-requests/{request_key}` | Current request summary, including completed prediction ID when available. |
| `POST /prediction-requests/{request_key}/cancel` | Idempotent cancellation returning the resulting request summary. |

- Return request ID, prediction name, state, submission/start/finish timestamps,
  safe failure information, and nullable completed prediction ID. Keep internal
  snapshots, worker ownership, and credentials out of summaries. Use existing
  camel-case API conventions.
- Preserve prediction preflight and saved-version list/detail contracts.
- Scope every request lookup to its organisation. Use existing active-user
  business authorization: consultants and administrators may inspect/cancel
  another user's requests. Keep mutation CSRF/Origin validation and audit actors.
- Missing or incorrectly scoped requests return not found. Cancellation of
  queued work returns `cancelled`; running work becomes `cancelling`; repeated
  calls return the current state. Terminal requests remain unchanged.

### Execution, cancellation, and recovery

- Add a standalone worker module runnable from the backend image, separate from
  FastAPI startup. Use existing dependencies and database configuration without
  requiring OIDC credentials or weakening API authentication configuration.
- Hold a database advisory lock for exclusive worker ownership. Atomically
  claim requests in submission order with a stable identifier tie-breaker.
  Use short transactions; do not hold a request transaction during model fitting.
- Run each calculation in a separate child process using only detached inputs
  and results. The supervisor alone accesses queue state and publishes results.
  Give each request isolated process communication and cleanup so killing a
  child cannot corrupt the next request or leave a blocked supervisor.
- Check work and cancellation every second. Stop sends termination, force-kills
  after a two-second grace period if necessary, and reaps the child before
  marking the request cancelled. Discard all partial output.
- Atomically save the complete version and mark its request completed, retaining
  the submitting actor on saved output. Serialize this commit against cancel:
  cancellation accepted first forbids publication; committed completion wins
  over subsequent cancellation. Never expose partial saved versions.
- Treat expected model ineligibility and interval unavailability as existing
  successful-version behavior. Unexpected errors, child crash, and publication
  failure result in a safe failed request with no version.
- Queued work survives restarts. Recover abandoned running requests as failed
  and abandoned cancelling requests as cancelled before claiming new work.
  Do not retry automatically. Stop child processes on worker shutdown or lost
  ownership and prevent stale workers from publishing.
- Work continues independently of browser navigation, logout, and session
  expiry. No browser abort signal cancels an accepted request.
- Provide worker health-check support for TASK-057E and safe lifecycle/failure
  logs using request identifiers, without logging snapshots or personal data.

## Acceptance Criteria

- [ ] Submission persists a discoverable queued request before returning and
      never calls model fitting in the HTTP request.
- [ ] Migration up/down preserves existing saved predictions; constraints and
      indexes enforce the documented lifecycle and name reservation.
- [ ] Concurrent submissions/publication cannot reserve duplicate names;
      failed and cancelled names are reusable.
- [ ] One global calculation runs even when two worker instances start;
      eligible queued requests are claimed in submission order.
- [ ] Queue/list/detail/cancel APIs enforce organisation lookup, business
      authorization, CSRF/Origin checks, and submitter/cancellation audit actors.
- [ ] Queued cancellation prevents execution. A blocked running model stops
      within five seconds under healthy local conditions without partial output.
- [ ] Repeated cancellation and cancellation/publication races are deterministic.
- [ ] Worker/child crash, restart, shutdown, ownership loss, and persistence
      failure cannot publish duplicate/partial versions or trigger retries.
- [ ] Queued requests survive restarts; abandoned active requests receive the
      documented terminal state and release reusable names.
- [ ] Saved prediction API/model behavior remains covered by regression tests.
- [ ] No frontend, Compose wiring, broker, or new dependency is added.

## Out Of Scope

- Predictions UI and polling; TASK-057D owns these.
- Compose, image wiring, rollout, and release checks; TASK-057E owns these.
- Parallel calculation, scheduling, priorities, automatic retries/resubmission,
  progress counters, result deletion, or automatic history pruning.

## Implementation Notes

Read `AGENTS.md`, `docs/architecture/overview.md`, ADR-002 through ADR-005, ADR-007 through
ADR-012, `docs/architecture/domains/FORECASTING.md`, `docs/architecture/data/DATA-MODEL.md`,
`docs/architecture/data/DATABASE.md`, `db/migrations/README.md`, `docs/operations/testing.md`, and
`docs/architecture/diagrams/README.md`.

Reuse the snapshot/calculation boundaries from TASK-057B and existing auth
dependencies. Locking/transaction tests must use PostgreSQL; SQLite API tests
cannot prove queue exclusivity or name/cancellation races. Document the worker
entrypoint, required database settings, and health-check contract for TASK-057E.

## Testing

Required: backend unit/API tests; disposable PostgreSQL migration, locking,
snapshot, and transaction-race tests; real child-process cancellation/crash
tests; lint; typecheck; changed diagram generation.

Cover every acceptance criterion, list limits, route isolation, both business
roles, missing/revoked sessions, incorrect CSRF/Origin, name case variants,
completed-version preservation, source mutation after enqueue, interrupted
execution, and loss of ownership. Verify prompt cancellation using a deliberately
blocked child rather than timing a naturally fast model.

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Supply `MIGRATION_TEST_DATABASE_URL` pointing to disposable PostgreSQL when
running migration and queue integration tests, following `docs/operations/testing.md`.
Ensure the normal CI PostgreSQL test invocation discovers these tests.

Not applicable: frontend checks and full Compose smoke, owned by downstream
tasks. A skipped PostgreSQL test suite does not satisfy integration acceptance.

## Documentation

Update Forecasting/API and worker behavior, logical/physical data documentation,
migration inventory, reusable testing guidance, physical/logical PlantUML
sources and matching SVGs, and any affected lifecycle diagram. Retain the
distinction between implemented backend support and deployment wiring pending
TASK-057E.

## Notes For AI Agent

- Implement only when requested after TASK-057A/B. Add no dependencies.
- Preserve all existing saved predictions; never modify production data manually.
- Do not silently fall back to in-process FastAPI background tasks.
- Record eventual Step 13 reviews under `docs/ai-reviews/TASK-057C/` and run
  `python3 scripts/ai_review_records.py validate` from the repository root.
- Report changed files and all checks, including skipped integration checks.
