"""PostgreSQL-backed background jobs (ADR-0024).

The scheduler enumerates Organizations with due work under the read-only
``enumerate`` worker scope and enqueues one idempotent job per Organization.
Each job then runs in its own Organization's RLS context.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database import RequestContext, transaction_session
from app.models import BackgroundJob, Organization, OrganizationStatus
from app.lifecycle import organization_deletion_window, purge_deleted_content, purge_organization
from app.legal_announcements import ANNOUNCE_JOB, announce_document
from app.mcp_server.calls import READ_LOG_JOB, cleanup_read_log
from app.notifications import CLEANUP_JOB, cleanup_notifications
from app.work_queue import (
    BackgroundJobDraft,
    claim_next_background_job,
    complete_queue_record,
    enqueue_background_job,
    fail_queue_record,
    retry_queue_record,
)

MAX_JOB_ATTEMPTS = 5

JobHandler = Callable[[Session, BackgroundJob, datetime], None]


def retry_delay(attempts: int) -> timedelta:
    """Bounded exponential backoff: 1, 2, 4, 8 … minutes, at most one hour."""
    return timedelta(minutes=min(2 ** max(attempts - 1, 0), 60))


PURGE_JOB = "content.purge"
ORGANIZATION_PURGE_JOB = "organization.purge"

HANDLERS: dict[str, JobHandler] = {PURGE_JOB: purge_deleted_content, ORGANIZATION_PURGE_JOB: purge_organization, CLEANUP_JOB: cleanup_notifications, READ_LOG_JOB: cleanup_read_log, ANNOUNCE_JOB: announce_document}


def schedule_purge_jobs(session_factory: sessionmaker[Session], *, today: date) -> int:
    """Enqueue one purge job per active Organization, once per day."""
    with transaction_session(session_factory, RequestContext(worker_scope="enumerate")) as session:
        organization_ids = session.scalars(select(Organization.id).where(Organization.status == OrganizationStatus.ACTIVE.value)).all()
    for organization_id in organization_ids:
        with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
            enqueue_background_job(session, BackgroundJobDraft(job_type=PURGE_JOB, payload={}, idempotency_key=f"{PURGE_JOB}:{organization_id}:{today.isoformat()}"))
    return len(organization_ids)


def schedule_notification_cleanup_jobs(session_factory: sessionmaker[Session], *, today: date) -> int:
    """Enqueue one notification cleanup per active Organization, once per day."""
    with transaction_session(session_factory, RequestContext(worker_scope="enumerate")) as session:
        organization_ids = session.scalars(select(Organization.id).where(Organization.status == OrganizationStatus.ACTIVE.value)).all()
    for organization_id in organization_ids:
        with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
            enqueue_background_job(session, BackgroundJobDraft(job_type=CLEANUP_JOB, payload={}, idempotency_key=f"{CLEANUP_JOB}:{organization_id}:{today.isoformat()}"))
    return len(organization_ids)


def schedule_mcp_read_log_cleanup_jobs(session_factory: sessionmaker[Session], *, today: date) -> int:
    """Enqueue one cleanup of old successful MCP read calls per active Organization, once per day."""
    with transaction_session(session_factory, RequestContext(worker_scope="enumerate")) as session:
        organization_ids = session.scalars(select(Organization.id).where(Organization.status == OrganizationStatus.ACTIVE.value)).all()
    for organization_id in organization_ids:
        with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
            enqueue_background_job(session, BackgroundJobDraft(job_type=READ_LOG_JOB, payload={}, idempotency_key=f"{READ_LOG_JOB}:{organization_id}:{today.isoformat()}"))
    return len(organization_ids)


def schedule_organization_purge_jobs(session_factory: sessionmaker[Session], *, now: datetime) -> int:
    """Enqueue one purge per Pending Deletion Organization whose window has ended."""
    cutoff = now - organization_deletion_window()
    with transaction_session(session_factory, RequestContext(worker_scope="enumerate")) as session:
        due = session.execute(
            select(Organization.id, Organization.deletion_requested_at)
            .where(Organization.status == OrganizationStatus.PENDING_DELETION.value)
            .where(Organization.deletion_requested_at <= cutoff)
        ).all()
    for organization_id, requested_at in due:
        with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
            enqueue_background_job(session, BackgroundJobDraft(job_type=ORGANIZATION_PURGE_JOB, payload={}, idempotency_key=f"{ORGANIZATION_PURGE_JOB}:{organization_id}:{requested_at.isoformat()}"))
    return len(due)


def run_one_background_job(
    session_factory: sessionmaker[Session],
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    handlers: dict[str, JobHandler] | None = None,
    organization_id: UUID | None = None,
) -> bool:
    """Claim and run one due job, optionally for one Organization; False when none is due."""
    handlers = handlers or HANDLERS
    with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
        job = claim_next_background_job(session)
        if job is None:
            return False
        job_id, organization_id, job_type, attempts = job.id, job.organization_id, job.job_type, job.attempts
    try:
        handler = handlers.get(job_type)
        if handler is None:
            raise LookupError(f"no handler for job type {job_type}")
        with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
            record = session.get(BackgroundJob, job_id)
            handler(session, record, now())
            complete_queue_record(record)
    except Exception as error:  # noqa: BLE001 - every failure must be recorded
        _record_failure(session_factory, job_id, organization_id, attempts, error, now())
    return True


def _record_failure(session_factory: sessionmaker[Session], job_id: UUID, organization_id: UUID | None, attempts: int, error: Exception, now: datetime) -> None:
    summary = f"{type(error).__name__}: {error}"[:500]
    with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
        record = session.get(BackgroundJob, job_id)
        if record is None:
            return
        if attempts >= MAX_JOB_ATTEMPTS:
            fail_queue_record(record, error=summary)
        else:
            retry_queue_record(record, error=summary, available_at=now + retry_delay(attempts))
