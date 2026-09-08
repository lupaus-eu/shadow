# TASK-057E Prediction Worker Runtime Integration And QA

## Source Plan

Approved plan: "Background Prediction Requests", accepted for task creation on
2026-09-07. Run one durable PostgreSQL-backed prediction worker from the same
backend image as the API and migration job, with coordinated application release.

Dependencies: [TASK-057A](TASK-057A-background-predictions-architecture.md),
[TASK-057B](TASK-057B-snapshot-based-prediction-calculation.md),
[TASK-057C](TASK-057C-durable-prediction-requests-worker.md), and
[TASK-057D](TASK-057D-prediction-request-ui.md).
Task creation does not implement runtime changes or authorize deployment.

## Goal

Wire the implemented worker into supported local and release runtimes, prove
queue/cancellation behavior end to end, and document operations and coordinated
rollout. Complete local and disposable-environment verification without a
production deployment.

## Requirements

- Add a prediction worker service to local, shared release, production, and
  Coolify Compose configurations. Keep it distinct from the existing local
  Authentik worker.
- Run the worker entrypoint from TASK-057C using the same immutable backend
  image as the API/migration services in production. Preserve non-root execution,
  release image identity, and provider portability. Add no dependencies or broker.
- Supply database and worker configuration without OIDC credentials, browser
  session secrets, public domains, or published worker ports.
- Replace the backend image's HTTP health check for this service with the
  worker-specific check. Configure automatic restart and child-process cleanup
  on shutdown; ensure container grace periods permit the specified termination
  and reap behavior.
- Require successful release migrations before starting either API or worker.
  Preserve the frontend's existing backend-health startup gate. Ensure local
  documented migration/start commands also start the worker against a ready
  schema; update Make workflows if their service selection requires it.
- Update Compose validation, release-image identity checks, migration-failure
  checks, and relevant CI scripts to include the worker. Existing assertions
  currently expect only migration/backend/frontend services and must be revised.
- Verify the worker can start with database/worker settings alone and that
  an unhealthy worker is observable through its dedicated health check and safe
  lifecycle logs. Logs must not include input snapshots or credentials.
- Verify automatic container restart preserves queued work and uses TASK-057C's
  interrupted-request recovery without automatic calculation retries. Starting
  a second worker must not permit concurrent prediction execution.
- Document coordinated API/frontend/worker rollout because the create response
  changes. Preserve saved predictions and deploy only up migrations through the
  existing release job. Document rollback's treatment of pending requests;
  application rollback must not automatically run down migrations.
- Complete manual browser QA against the assembled local runtime and record
  actual outcomes, including any unavailable environment checks. Do not claim
  that standard Compose parsing proves Coolify-specific provider behavior.

## Acceptance Criteria

- [ ] Local, production, and Coolify manifests include the prediction worker
      with correct image identity, entrypoint, settings, and service isolation.
- [ ] Worker startup does not require API OIDC credentials or expose a port.
- [ ] Migration failure prevents both API and worker startup; the existing
      frontend/backend health relationship still holds.
- [ ] The production worker image runs as non-root, reports its own health,
      restarts appropriately, and reaps its calculation process on shutdown.
- [ ] A local browser can submit several named predictions, see FIFO queued
      work and one calculating request, and continue using saved comparisons.
- [ ] Queued removal prevents execution; running Stop terminates a deliberately
      blocked calculation within five seconds under healthy local conditions.
- [ ] Cancelled/failed requests publish no partial version and their names are
      reusable; completion updates the saved-version library.
- [ ] Reload/navigation, source edits after submission, and worker restart
      preserve the accepted snapshot and lifecycle semantics.
- [ ] Duplicate worker startup cannot calculate concurrently; interrupted
      calculations fail visibly without retries while queued requests survive.
- [ ] Runtime/data/lifecycle diagrams and operational documentation match the
      assembled implementation, with corresponding generated SVGs.
- [ ] Backend/frontend, PostgreSQL, image, and Compose checks pass locally/CI
      where available; no production deployment or merge is performed.

## Out Of Scope

- New queue architecture, forecasting algorithms, API behavior, or UI features.
- Broker services, horizontal concurrency, automatic retries, schedules,
  third-party monitoring, or changed authentication trust boundaries.
- Production deployment, production failure injection, manual production SQL,
  merging PRs, or representing local QA as production approval.

## Implementation Notes

Read `AGENTS.md`, `ARCHITECTURE.md`, ADR-002 through ADR-005 and ADR-012,
`docs/LOCAL-DEVELOPMENT.md`, `docs/DEPLOYMENT.md`, `docs/TESTING.md`,
`docs/diagrams/README.md`, and the worker contract from TASK-057C.

Relevant runtime surfaces are `backend/Dockerfile`, local/release/production/
Coolify Compose manifests, `Makefile`, `.github/workflows/ci.yml`, and existing
scripts under `.github/scripts/`. Reuse their disposable-environment approach
and exact image identity checks. Treat application/worker availability and
container cleanup as operational checks, not reasons to loosen API auth.

## Testing

Required: backend and frontend checks; disposable PostgreSQL queue/migration
integration tests; production image and Compose validation; real worker
shutdown/restart/cancellation tests; manual browser QA; diagram generation.

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
cd ../frontend
pnpm lint
pnpm test
pnpm build
cd ..
bash .github/scripts/verify-production-compose.sh
docker compose --profile docs build diagram-renderer
docker compose --profile docs run --rm diagram-renderer
docker compose --profile docs run --rm diagram-renderer -tsvg -o generated data-logical-model.puml
python3 scripts/ai_review_records.py validate
```

Run PostgreSQL tests with the disposable configuration documented in
`docs/TESTING.md`. Build the production backend/frontend images and run the
updated release migration-failure and worker smoke checks using the existing
CI/documented environment setup. Explicitly render other changed diagram
sources. Report skipped provider/manual checks separately from passing checks.

Not applicable: production smoke/deployment in this implementation task; those
follow only a separately human-approved release under the existing runbook.

## Documentation

Update `AGENTS.md` runtime summary where needed, `ARCHITECTURE.md`,
`docs/LOCAL-DEVELOPMENT.md`, `docs/DEPLOYMENT.md`, `docs/TESTING.md`, relevant
README usage/commands, and architecture/lifecycle PlantUML sources and SVGs.
Document worker startup/health/logs, interrupted-request recovery, manual
resubmission with reusable names, coordinated release, and rollback handling.
Keep physical/logical data diagrams consistent with TASK-057C's schema.

## Notes For AI Agent

- Implement only this integration/QA scope when separately requested.
- Add no dependency and do not deploy or merge into main.
- Use disposable databases for destructive/failure tests, never production.
- Record eventual Step 13 reviews under `docs/ai-reviews/TASK-057E/` according
  to `docs/AI-REVIEW-RECORDS.md` and validate them.
- Report changed files, checks, actual manual results, and remaining release
  prerequisites without claiming an unperformed production rollout.
