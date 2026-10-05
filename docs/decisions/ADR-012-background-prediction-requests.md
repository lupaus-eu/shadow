# ADR-012: Durable Background Prediction Requests

Status: Accepted; implementation pending TASK-057B through TASK-057E

Date: 2026-09-08

---

# Amendment

Amended by ADR-014: Forecasting adds a sixth result kind, `prophet`, with
per-version model selection, and raises the persisted-point limit to 110,000.
ADR-014 also amends the child stop procedure: each calculation child runs in
its own process group that the supervisor signals as a whole, and each child
gets a private temporary directory that the supervisor removes after reaping
it. The five-second cancellation bound and every other decision here are
unchanged.

---

# Context

Forecasting currently calculates a complete prediction version synchronously in
the authenticated create request. The work is bounded, but model fitting can
still outlive an HTTP request and prevents the user from continuing in the
Predictions workspace. The synchronous restriction in ADR-007 intentionally
avoided job infrastructure at the time; it must now be replaced by a durable,
auditable execution model without changing the established prediction
algorithms, source isolation, interval semantics, eligibility handling, work
limits, or immutable saved-version contract.

A background execution must remain safe when source data changes, a browser
goes away, a worker stops, or a user cancels work while it is calculating.

# Decision

## Scope And Supersession

This ADR supersedes only ADR-007's synchronous execution restriction and its
prohibition on a queue, worker and progress polling. It does not change the
five result kinds, deterministic configuration, scenario-owned observation
policy in ADR-009, derived-result policy in ADR-010, prediction-interval policy
in ADR-011, expected model-ineligibility behavior, resource limits, or
immutable completed prediction versions.

The accepted architecture is not runtime behavior yet. TASK-057B introduces
detached snapshot preparation and calculation boundaries; TASK-057C introduces
the schema, APIs and worker; TASK-057D introduces the UI; and TASK-057E wires
the worker into supported runtimes and completes operational QA.

## Ownership And Persistent Request

Forecasting owns a mutable `prediction_requests` record in addition to its
existing immutable prediction version, target, result and point records. A
request has a stable request key, organisation, requested prediction name,
format-identified immutable input/configuration snapshot, lifecycle state,
submission/start/finish timestamps, submitting user, cancellation actor and
time when applicable, worker ownership identity, user-safe failure information,
and an optional reference to its completed prediction version.

Existing saved versions remain as they are. No historical request is invented
for them. A request is history even after it is terminal; it is never deleted
by this feature.

The input snapshot is frozen from one consistent submission-time database read
and contains everything calculation and audit output need: target-scenario
identity; metric names, stable keys and units; permitted effective observations
and their provenance; historical and future explanatory features; date grids;
eligibility and safe reasons; cutoff and seasonal settings; selected interval
level and model configuration; derived formulas; and every formula-referenced
metric key and short name. The calculator receives only this detached,
serializable snapshot and previously calculated normal results for derived
targets. It never rereads live source rows. Source edits, soft deletion, formula
changes and short-name changes after acceptance cannot alter the request.

## Queue, Ordering And Worker Exclusivity

PostgreSQL is the durable queue; no broker, task framework, scheduler, retry
protocol, priority or reordering is introduced. Accepted queued requests survive
API and worker restarts. One separate prediction-worker service runs from the
existing backend image and existing dependencies. It is not started by FastAPI.

The worker takes a PostgreSQL advisory lock for exclusive global calculation
ownership. A worker that cannot hold that lock performs no calculation. While
holding it, the worker claims exactly one eligible queued request at a time in
submission timestamp order, with the stable request identifier as the tie
breaker. Claiming is atomic and uses a short transaction; no transaction spans
model fitting. This provides global FIFO execution even if two worker instances
start.

Each claimed calculation runs in its own supervised child process. The child
uses detached inputs and returns detached results only; it does not access queue
state or publish a version. The supervisor is the sole owner of request-state
checks, child lifecycle, result publication and terminal state changes. It
checks worker ownership and cancellation at least once per second. On stop or
cancellation it terminates the child, waits at most two seconds, force-kills if
needed, and reaps it before finalizing the request. Healthy local verification
must demonstrate cancellation within five seconds. Child output is isolated per
request and all partial output is discarded.

## Lifecycle, Cancellation And Recovery

The only request states are `queued`, `running`, `cancelling`, `completed`,
`cancelled`, and `failed`.

```text
queued ----claim----> running ----publish----> completed
  |                     |
  | cancel              | cancel
  v                     v
cancelled            cancelling ----child stopped----> cancelled

running ----unexpected error / lost ownership----> failed
```

- A queued cancellation is atomic and immediately becomes `cancelled`; it is
  never claimable afterwards.
- A cancellation of running work becomes `cancelling`; the supervisor stops
  and reaps its child, discards output, then marks it `cancelled`.
- Repeated cancellation is idempotent: terminal requests are unchanged and a
  cancelling request remains cancelling until its supervisor finalizes it.
- Expected model ineligibility and interval unavailability remain normal data
  inside a successfully completed immutable version, not failed requests.
- An unexpected calculation error, child crash or publication error leaves no
  partial version and marks the request `failed` with safe failure information.

Publication and cancellation are serialized in one short database transaction
under the request's current worker ownership. If cancellation is accepted first,
publication is forbidden and no version is saved. If complete version
persistence and the `completed` request transition commit first, completion
wins and a later cancellation returns `completed`. A worker that has lost
ownership cannot publish.

On worker startup, interrupted `running` requests become visibly `failed`, and
abandoned `cancelling` requests become `cancelled`; neither is retried
automatically. Queued requests remain queued. On graceful shutdown or ownership
loss, the supervisor stops and reaps its child and does not publish stale work.
Browser navigation, reload, logout, session expiry, request aborts and polling
cleanup never cancel already accepted work.

## Name Admission And Publication

A non-blank prediction name is reserved case-insensitively per organisation by
every `queued`, `running` and `cancelling` request, and permanently by every
completed immutable prediction version. `cancelled` and `failed` request
history releases its name for a new request. Name admission and final
publication are serialized per organisation and enforced by database
constraints/indexes so concurrent submission, cancellation and publication
cannot create duplicate active or completed names. A case-insensitive duplicate
uses the existing user-safe conflict response.

## API And Authorization Contract

The existing organisation-scoped preflight remains synchronous. The existing
creation endpoint accepts the same payload but queues validated frozen inputs
and returns `202 Accepted`, a request summary and a `Location` status URL;
it does not calculate in the HTTP request. Saved prediction-version list and
detail contracts remain unchanged.

TASK-057C defines the route inventory under
`/api/v1/organisations/{organisation_key}`:

| Method and path | Contract |
| --- | --- |
| `POST /predictions` | Queue a request; return `202 Accepted`, summary and status location. |
| `GET /prediction-requests` | All active requests plus the 50 most recently finished requests. |
| `GET /prediction-requests/{request_key}` | One current request summary. |
| `POST /prediction-requests/{request_key}/cancel` | Idempotently cancel queued/running work and return its resulting summary. |

A summary exposes the request key, prediction name, state, submission/start/
finish timestamps, safe failure information and nullable completed prediction
ID (the existing public prediction key). It never exposes the snapshot, worker
ownership or credentials. Every
lookup is organisation-scoped. Existing business authorization remains: both
consultants and administrators may inspect or cancel another user's request.
Authenticated mutations retain exact Origin and CSRF checks, and submission and
cancellation retain their respective actor attribution.

## User Experience

The current organisation's Predictions tab shows state-only request progress:
all active requests and the 50 recently finished records returned by the API.
It polls summaries every two seconds while the tab is visible, including while
idle so other users' requests appear. It refreshes on visibility and prevents
overlapping or stale polls. It shows `Queued`, `Calculating prediction values`,
`Stopping`, `Completed`, `Cancelled`, or `Failed`, with safe failure reasons.

There are no percentages, work counters, estimates, global workspace
indicators, automatic retries, result deletion or request-history pruning.
Queued work can be removed from the queue and running work can be stopped;
both preserve request history and never delete a saved prediction. Completion
refreshes the existing saved-version library. Browser-side fetch abortion only
stops the browser request, never accepted server work.

## Runtime And Release Contract

API, frontend and worker require coordinated release because prediction creation
changes from a completed-version response to `202 Accepted` request acceptance.
The worker starts only after the existing successful migration gate, runs from
the same backend image as API and migration job, has no public port and needs
database/worker settings but no OIDC credentials. It uses its own health check
and restart policy; it is distinct from the local Authentik worker. TASK-057E
implements the Compose, image, health, shutdown and deployment documentation.

Production rollout remains a separately human-approved action. Rollback never
automatically runs down migrations; operational handling of pending requests is
documented and verified by TASK-057E.

# Consequences

Benefits:

- accepted work is durable and independent of an HTTP request or browser;
- completed versions remain immutable, auditable and all-or-nothing;
- cancellation and publication have a deterministic, observable outcome; and
- a single PostgreSQL-backed worker avoids new infrastructure and parallel model
  contention.

Costs and constraints:

- prediction names may remain reserved while work is active;
- one global worker deliberately serializes all organisations' calculations;
- interrupted work is visible but requires manual resubmission; and
- API, UI, worker and deployment updates must be released together.

# Implementation Rules

- TASK-057B must preserve existing synchronous HTTP behavior while making the
  frozen detached calculation boundary available.
- TASK-057C must implement request persistence, PostgreSQL locking, worker,
  APIs, state transitions and tests without adding dependencies or Compose
  wiring.
- TASK-057D must implement only the state-only current-tab experience.
- TASK-057E must add runtime wiring and end-to-end QA; it must not deploy to
  production without separate human approval.
- Do not synthesize request history for existing versions, add automatic
  retries, relax source isolation, or delete saved versions.

# References

- `docs/decisions/ADR-002-database-migrations.md`
- `docs/decisions/ADR-003-coolify-deployment.md`
- `docs/decisions/ADR-004-authentication.md`
- `docs/decisions/ADR-005-production-only-environments.md`
- `docs/decisions/ADR-007-predictions-forecasting-domain.md`
- `docs/decisions/ADR-009-scenario-owned-prediction-inputs.md`
- `docs/decisions/ADR-010-derived-metrics.md`
- `docs/decisions/ADR-011-prediction-intervals.md`
- `docs/decisions/ADR-014-prophet-and-model-selection.md`
- `docs/domains/FORECASTING.md`
- `tasks/TASK-057A-background-predictions-architecture.md`
