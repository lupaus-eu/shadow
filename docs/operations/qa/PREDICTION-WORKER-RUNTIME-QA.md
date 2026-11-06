# Prediction Worker Runtime QA

This checklist records TASK-057E local runtime evidence. Use only disposable or
local development data. It does not authorize production deployment, failure
injection, down migrations or Coolify changes.

Architecture amendment: [ADR-013](../../adr/0013-shared-entra-local-https-deployment.md)
replaces the platform and local identity target with UpCloud/Compose, direct
Caddy TLS and direct Entra. The TASK-057E procedures/results below are preserved
historical evidence for the earlier runtime, not verification of the new design.
TASK-059G/E provides equivalent Compose and worker checks; old unavailable
Coolify checks are not gates for the new deployment and must not be marked passed.
On 2026-09-28 TASK-059E reran `.github/scripts/verify-production-worker.sh`
(non-root start, health, isolation, exclusivity, restart, shutdown and safe
logs) against a migrated disposable PostgreSQL 18 database, and the disposable
runtime harness verified exactly one healthy worker after first install,
releases, rollback and daemon restart. See
[UPCLOUD-RUNBOOK-QA.md](UPCLOUD-RUNBOOK-QA.md). F ran the production
prediction-flow smoke under the [runbook](../../runbooks/production.md#7-narrow-production-smoke)
for the first release; see
[FIRST-PRODUCTION-ROLLOUT.md](FIRST-PRODUCTION-ROLLOUT.md#8-narrow-production-smoke-7).

## Preconditions

- Run `make dev-up` so migration 015 and the development seed complete before
  API, prediction worker and frontend startup.
- Trust the local application CA and use `https://app.localhost`.
- Use non-sensitive synthetic prediction names. Never paste snapshots,
  credentials, cookies, CSRF tokens or personal data into this record.
- Keep a terminal ready for `docker compose --env-file .env --env-file .env.entra.local ps prediction-worker` and
  credential-safe worker logs.

## Browser And Runtime Procedure

Record pass/fail and concise evidence for each item:

1. Sign in as a seeded active user, open one organisation's Predictions tab and
   confirm saved comparisons remain selectable.
2. Submit at least three uniquely named predictions close together. Confirm one
   shows `Calculating prediction values`, the others remain FIFO `Queued`, and
   the rest of the saved-prediction UI remains usable.
3. Remove a queued request. Confirm it becomes `Cancelled`, is never calculated,
   publishes no version, and its name can be submitted again.
4. Press Stop for a running browser request and confirm it reaches `Cancelled`
   with no saved partial version. Separately run the disposable PostgreSQL
   deliberately-blocked-child test and require termination/reaping within five
   seconds. Do not add a debug-only blocking path to the shipped UI or worker.
5. Confirm a failed request publishes no version and its name is reusable.
   Confirm a completed request appears in the saved-version library.
6. Submit work, navigate away/reload/log out, return, and confirm accepted work
   continued independently of the browser.
7. Submit work, edit its source values after acceptance, and confirm the
   completed audit/result uses the accepted snapshot. Use the automated frozen-
   snapshot test as the exact data-level evidence.
8. While a request is queued, restart `prediction-worker`; confirm the queued
   request survives and later runs. Interrupt a deliberately blocked running
   request by restarting its worker; confirm it becomes visibly `Failed`, is not
   retried, and its name can be resubmitted manually.
9. Start a second worker from the same image and database. Confirm it exits
   because ownership is already held and never creates a second calculating
   request.
10. Confirm the normal worker is healthy through its dedicated check, has no
    published port, and its logs contain request identifiers/lifecycle messages
    but no input snapshots or credentials. Confirm the worker-specific health
    command returns nonzero without a lock-owning worker.

## TASK-057E Execution Record — 2026-09-09

Environment: Codex workspace `/home/j/workspace/reflector/shadow`, branch
`feature/TASK-057E-prediction-worker-runtime-qa`.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Portable production Compose parsing and assertions | Pass | `.github/scripts/verify-production-compose.sh` completed and asserted migration/API/worker/frontend topology, isolation, settings and gates. |
| Coolify standard fields and release identity | Pass | After excluding the provider-only `exclude_from_hc` field, standard Compose parsing confirmed migration/API/worker share the exact backend image and frontend uses the matching frontend image. |
| Local Compose/Auth configuration assertions | Pass | `scripts/verify-local-authentik-config.sh` completed and asserted the distinct database-only worker service. |
| Local worker container runtime | Pass | An isolated Compose project built the dev worker and started it healthy with database-only settings against a freshly migrated disposable schema; it exposed no port and stopped cleanly. The isolated project and volumes were removed afterwards. |
| Backend checks | Pass | Ruff passed; pytest passed 390 tests with 28 PostgreSQL-dependent skips in the normal run; pyright reported zero errors. The skipped worker/database cases passed separately below. |
| Frontend checks | Pass | ESLint passed; Vitest passed 223 tests in 19 files; the TypeScript/Vite production build passed. Commands used the repository-pinned pnpm 10.12.1 through Corepack because the host-global pnpm 11 rejected an unrelated ignored build script. |
| Production backend/frontend image builds | Pass | Both production targets built as `shadow-backend:task057e-local` and `shadow-frontend:task057e-local`. |
| Disposable PostgreSQL queue/migration integration | Pass | 26 tests passed, including FIFO ownership, frozen snapshots, blocked-child cancellation/shutdown reaping, publication races, recovery and queued work continuation by a new worker. |
| Production worker image lifecycle smoke (items 9–10) | Pass | `.github/scripts/verify-production-worker.sh` passed against the built image and a migrated disposable PostgreSQL container: non-root/database-only startup, no port binding, dedicated health failure/success, duplicate exclusion, automatic restart, shutdown and safe lifecycle logs. |
| Migration-failure startup gate | Pass | `.github/scripts/verify-release-compose-failure.sh` returned nonzero for corrupted disposable history and confirmed API, worker and frontend never started. |
| Production frontend ingress/security smoke | Pass | `.github/scripts/verify-production-frontend.sh` passed against the built frontend image. |
| Diagram generation | Pass | Runtime, forecasting component, lifecycle, logical-data and physical-schema PlantUML sources rendered successfully. |
| Local assembled application and browser items 1–8 | Unavailable | The existing local development database has migration 015 checksum drift; `migrate.py up` failed closed. The database was preserved without reset or manual SQL, and no interactive browser facility was available to this agent. No browser result is claimed. |
| Coolify provider parsing/behavior | Unavailable | No Coolify resource/provider was available. Standard Compose parsing is not evidence for Coolify-specific `exclude_from_hc` behavior. |
| Production deployment/smoke | Not run (out of scope) | TASK-057E does not authorize production deployment. |

Browser execution detail for this record:

| Item | Outcome | Actual result |
| --- | --- | --- |
| 1. Login and saved comparisons | Unavailable | Application startup was blocked before browser execution. |
| 2. Multiple names, FIFO and one calculating | Unavailable | Application startup was blocked before browser execution. |
| 3. Queued removal and name reuse | Unavailable | Application startup was blocked before browser execution. |
| 4. Running Stop and no partial version | Unavailable | Browser path was unavailable; the separate deliberately blocked PostgreSQL test passed within five seconds. |
| 5. Failed/completed publication and name behavior | Unavailable | Browser path was unavailable; failure/publication PostgreSQL tests passed. |
| 6. Reload, navigation and logout | Unavailable | Application startup was blocked before browser execution. |
| 7. Source edits after acceptance | Unavailable | Browser path was unavailable; the frozen-snapshot PostgreSQL test passed. |
| 8. Worker restart and visible recovery | Unavailable | Browser visibility was unavailable; queued continuation, interrupted recovery and container restart tests passed separately. |

The migration drift above was later resolved without resetting the local
database. The automated retry below supersedes only the unavailable local
runtime result; it does not retroactively claim browser or provider evidence.

## TASK-057E Automated Retry Record — 2026-09-09

Environment: Codex workspace `/home/j/workspace/reflector/shadow`, branch
`feature/TASK-057E-prediction-worker-runtime-qa`, Docker Compose 5.1.0.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Current migration 015 and assembled startup | Pass | The preserved local history ended at migration 014. `make dev-up` applied the current migration 015 and completed seed/startup. The recorded checksum matches `db/migrations/015_create_prediction_requests.sql` (`5878f748103942020e1ccdc3871f2fb86eda3e50ab180e2f4c1962a4515c9905`), and the prediction-request queue index exists. |
| Local assembled application | Pass | Backend health returned `{"status":"ok"}`, the frontend returned HTTP 200, and backend, frontend and `prediction-worker` remained running. The worker reported healthy through its dedicated health check. |
| Local worker isolation and safe logs (items 9–10) | Pass | The worker had no host port binding, had only database/base-image environment names rather than API auth/session/public-origin settings, ran with init and `unless-stopped`, and emitted ownership/recovery lifecycle logs without database URLs, OIDC secrets or input snapshots. |
| Duplicate ownership and missing-owner health (items 9–10) | Pass | A second worker against the assembled database exited nonzero with the expected ownership-held result. After stopping the owner, the worker-specific health command returned nonzero. The primary worker then started healthy again. |
| Automatic restart | Pass | Terminating the worker process caused the container to restart automatically; it returned to healthy with restart count 1 and emitted a new ownership/recovery lifecycle pair. |
| Backend checks | Pass | Ruff passed; pytest passed 390 tests with 28 PostgreSQL-dependent skips in the normal run; pyright reported zero errors. |
| Frontend checks | Pass | ESLint passed; Vitest passed 223 tests in 19 files; the TypeScript/Vite production build passed with the repository-pinned pnpm through Corepack. |
| Disposable PostgreSQL queue/migration integration | Pass | 26 tests passed, including ownership/FIFO, frozen snapshots, cancellation and child reaping, publication races, interrupted recovery and queued continuation. |
| Production Compose and local configuration assertions | Pass | `.github/scripts/verify-production-compose.sh` and `scripts/verify-local-authentik-config.sh` passed; shell syntax and AI-review record validation also passed. |
| Production image rebuilds | Pass | The current checkout built as `shadow-backend:task057e-local` and `shadow-frontend:task057e-local`. |
| Production worker image lifecycle smoke | Pass | `.github/scripts/verify-production-worker.sh` passed against a newly migrated disposable PostgreSQL instance: non-root startup, database-only settings, no port binding, health, duplicate exclusion, restart, shutdown and safe logs. |
| Migration-failure startup gate | Pass | Corrupted disposable migration history made the migration container exit 1, and backend, worker and frontend remained unstarted. The harness now reads the migration container exit code directly because Compose 5.1.0 returned zero from the top-level `up --exit-code-from migration` invocation despite reporting the service failure. |
| Production frontend ingress/security smoke | Pass | `.github/scripts/verify-production-frontend.sh` passed against the rebuilt frontend image. |
| Coolify provider parsing/behavior | Unavailable | No Coolify resource/provider was available. Standard Compose assertions are not evidence for provider-specific `exclude_from_hc` behavior. |
| Production deployment/smoke | Not run (out of scope) | TASK-057E does not authorize production deployment. |

Manual browser handoff for the assembled local application 2026-09-10:

| Item | Outcome | Human evidence |
| --- | --- | --- |
| 1. Login and saved comparisons | Pass | Saved comparisons available |
| 2. Multiple names, FIFO and one calculating | Pass | FIFO and one calculating |
| 3. Queued removal and name reuse | Pass | Removed queued request becomes `Cancelled`, is never calculated, publishes no version, and its name can be submitted again.  |
| 4. Running Stop and no partial version | Pass | Running request changed Calculating → Stopping → Cancelled; no saved version appeared for “QA stop 2026-09-10”. The blocked-child cancellation/reaping test passed separately within five seconds. |
| 5. Failed/completed publication and name behavior | Pass | Failed request publishes no version and its name is reusable. Completed request appears in the saved-version library. Automated failure/publication tests passed separately. |
| 6. Reload, navigation and logout | Pass | Accepted work continued independently of the browser. |
| 7. Source edits after acceptance | Pass | The frozen-snapshot PostgreSQL test passed automatically. The completed audit/result manually verified to use the accepted snapshot. |
| 8. Worker restart and visible recovery | Pass | Queued continuation, interrupted recovery and container restart passed automatically; browser-visible behavior as expected. |

The local application is ready at `http://app.localhost:5173` for browser items
1–8. Append the human outcomes without converting the unavailable Coolify check
to pass based on standard Compose parsing. Run the manifest through Coolify only
as part of a separately approved rollout workflow.

## TASK-057E Manual QA Finding Follow-up — 2026-09-10

Browser item 2 initially failed: three accepted requests remained `queued` and
none became `running`. The standalone worker raised SQLAlchemy
`NoReferencedTableError` while flushing its claim because its import path had
not registered the Users model table referenced by
`prediction_requests.submitted_by` and `cancelled_by`. API startup and the
PostgreSQL integration module both imported the Users model through other paths,
which masked the worker-entrypoint defect in prior automated runs.

The worker now explicitly registers the Users table without importing FastAPI
or API authentication configuration. A fresh-interpreter regression resolves
the `submitted_by` foreign key through the same standalone module import. After
restarting the bind-mounted local worker, all three preserved queued requests
were claimed and completed, and the worker remained healthy. No request
snapshot was inspected or printed.

Follow-up verification:

| Check | Outcome | Evidence |
| --- | --- | --- |
| Standalone metadata regression | Pass | `tests/test_prediction_worker.py` passed in a fresh Python interpreter and resolved `prediction_requests.submitted_by` to the registered `users.user_id` table. |
| Backend checks | Pass | Ruff passed; pytest passed 391 tests with 28 expected PostgreSQL skips; pyright reported zero errors. |
| Disposable PostgreSQL integration | Pass | All 26 migration and prediction-worker tests passed against an isolated PostgreSQL container. A discarded attempt against the normal local database correctly could not acquire the database-wide worker advisory lock while the local worker was running and is not counted as test evidence. |
| Rebuilt production worker image | Pass | The rebuilt `shadow-backend:task057e-local` image passed the fresh-process metadata assertion and `.github/scripts/verify-production-worker.sh` lifecycle smoke against freshly migrated disposable PostgreSQL. |
| Local queued-request recovery | Pass | The three requests preserved during the failure reached `completed`; the worker returned healthy and continued holding global ownership. |
| Browser item 2 rerun | Pass | The human rerun confirmed one visible `Calculating prediction values` request and FIFO `Queued` requests after the standalone model-registration fix. |

The local application and corrected worker remain running for the remaining
browser checks.
