# Background workers

## Runtime

Background workers are Python processes in the backend codebase. They use the same application services, SQLAlchemy models, database transactions, tenant context, and configuration as FastAPI.

Workers run as separate containers built from the backend image with a worker-specific command. They do not run inside FastAPI request processes.

## Queue

PostgreSQL stores outbox and background-job records.

- Workers atomically claim available work using row locking and skip already-claimed rows.
- Claims are committed before external network calls so database transactions are not held open during delivery.
- Jobs carry an idempotency key, attempt count, next-attempt timestamp, and last error summary.
- Transient failures use bounded exponential backoff.
- Exhausted jobs move to a failed state for operator inspection and replay.
- Graceful shutdown stops new claims and finishes or releases current work safely.

## Implemented jobs

The worker loop (`backend/app/worker.py`) delivers Invitation email from the
outbox (topic `organization.invitation`) and runs background jobs through
`backend/app/jobs.py`:

- Every `WORKER_SCHEDULE_INTERVAL_SECONDS` (default 3600) the scheduler
  enumerates active Organizations that have a Series and enqueues one
  `recurrence.materialize` job per Organization per day. The idempotency key
  `recurrence.materialize:{organization}:{date}` prevents duplicates.
- A job runs in its Organization's RLS context and materializes every Series
  through the Organization's today plus `RECURRENCE_BUFFER_DAYS` (default 366).
- The scheduler also enqueues one `content.purge` job per active
  Organization per day, which purges Events and Yearclocks deleted longer
  ago than `DELETED_CONTENT_RETENTION_DAYS` (default 30).
- It also enqueues one `organization.purge` job per Pending Deletion
  Organization older than `ORGANIZATION_DELETION_RETENTION_DAYS` (default
  30), keyed by the Organization and its deletion request time.
- Each scheduler pass (hourly by default) also enqueues one `notifications.summary` job per active Organization whose local time has reached 08:00, keyed by the Organization and its local date; the job queues the due Summaries (see `docs/architecture/email.md`). The send time is therefore 08:00 plus up to `WORKER_SCHEDULE_INTERVAL_SECONDS`.
- Besides Invitation email the worker sends `notification` outbox messages (notification email) the same way.
- It also enqueues `legal.announce` jobs (ADR-0041): for each published legal document version that is not yet in
  `legal_announcements`, one job per active Organization keyed by Organization, document, and version, and then
  records the announcement. The job notifies the Organization's Owners (`legal_document_published`, in the app and
  by mandatory email) unless the Organization has already accepted that version. A failed job retries like the
  others and shows in the operator console.
- It also enqueues one `notifications.cleanup` job per active Organization per
  day, which deletes notifications older than `NOTIFICATION_RETENTION_DAYS`
  (default 90) under the worker scope `notifications`.
- About once a minute the worker expires due Support Access grants.
- A failing job is retried with backoff of 1, 2, 4, 8 … minutes (at most one
  hour) and marked `failed` after five attempts, with a short error summary.

Materialization locks the Series row before inserting, so concurrent workers
and requests never race the unique `(series_id, series_date)` constraint.

## First-release uses

Planned uses beyond those above:

- Scaleway Transactional Email for outbox topics other than Invitations
- retryable Stripe webhook follow-up work
- scheduled Organization deletion purge

Event reminders and date-based notification jobs are outside the first release.

## Deferred infrastructure

Redis, Celery, and a separate message broker are not used in the first release. They may be introduced if PostgreSQL job throughput or scheduling requirements become insufficient.
