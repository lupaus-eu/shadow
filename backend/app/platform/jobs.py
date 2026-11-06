"""PostgreSQL-backed background jobs (ADR-019; from Yearclock ``jobs.py``, 6848e72).

Features register a handler per job type and, when work must be created on a
timer, a scheduler. The worker claims one due job at a time and runs it in its
own transaction under the job's tenant context; a failure is recorded and the
job retried with backoff until it has used its attempts.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import RequestContext, transaction_session
from app.platform.models import BackgroundJob, QueueStatus
from app.platform.work_queue import (
    claim_next_background_job,
    complete_queue_record,
    fail_queue_record,
    retry_queue_record,
)

LOGGER = logging.getLogger("shadow.worker")
MAX_JOB_ATTEMPTS = 5

JobHandler = Callable[[Session, BackgroundJob, datetime], None]
Scheduler = Callable[[sessionmaker[Session], datetime], int]

HANDLERS: dict[str, JobHandler] = {}
SCHEDULERS: list[Scheduler] = []


def register_job_handler(job_type: str, handler: JobHandler) -> None:
    if job_type in HANDLERS:
        raise ValueError(f"job type {job_type!r} already has a handler")
    HANDLERS[job_type] = handler


def register_scheduler(scheduler: Scheduler) -> None:
    SCHEDULERS.append(scheduler)


def run_schedulers(session_factory: sessionmaker[Session], now: datetime) -> int:
    """Run every registered scheduler; a failing one does not stop the others."""
    created = 0
    for scheduler in tuple(SCHEDULERS):
        try:
            created += scheduler(session_factory, now)
        except Exception:  # noqa: BLE001 - one broken scheduler must not stop the worker
            LOGGER.exception(
                "scheduler %s failed", getattr(scheduler, "__name__", scheduler)
            )
    return created


def retry_delay(attempts: int) -> timedelta:
    """Bounded exponential backoff: 1, 2, 4, 8 … minutes, at most one hour."""
    return timedelta(minutes=min(2 ** max(attempts - 1, 0), 60))


def run_one_background_job(
    session_factory: sessionmaker[Session],
    *,
    now: Callable[[], datetime] | None = None,
    handlers: dict[str, JobHandler] | None = None,
    tenant_id: UUID | None = None,
) -> bool:
    """Claim and run one due job, optionally for one tenant; False when none is due.

    ``now`` (a clock for tests) is used for the handler and for scheduling a
    retry; without it retries are scheduled on the database clock, the same
    clock that decides when a row is due.
    """
    handlers = HANDLERS if handlers is None else handlers
    with transaction_session(
        session_factory, RequestContext(tenant_id=tenant_id)
    ) as session:
        job = claim_next_background_job(session)
        if job is None:
            return False
        job_id, job_tenant_id = job.id, job.tenant_id
        job_type, attempts = job.job_type, job.attempts
        if attempts > MAX_JOB_ATTEMPTS:
            # Claimed again after a crash too many times: give up without running.
            LOGGER.warning(
                "job %s (%s) failed: claimed too many times", job_id, job_type
            )
            fail_queue_record(job, error="claim timed out too many times")
            return True
    try:
        handler = handlers.get(job_type)
        if handler is None:
            raise LookupError(f"no handler for job type {job_type}")
        with transaction_session(
            session_factory, RequestContext(tenant_id=job_tenant_id)
        ) as session:
            # The row lock keeps a long-running job from being claimed again as
            # stale; only a crashed worker's row (no lock) is taken over.
            record = lock_own_claim(session, job_id, attempts)
            if record is None:
                return True
            handler(session, record, (now or _utc_now)())
            complete_queue_record(record)
    except Exception as error:  # noqa: BLE001 - every failure must be recorded
        LOGGER.warning(
            "job %s (%s) failed on attempt %d: %s",
            job_id,
            job_type,
            attempts,
            type(error).__name__,
        )
        _record_failure(session_factory, job_id, job_tenant_id, attempts, error, now)
    return True


def _utc_now() -> datetime:
    return datetime.now(UTC)


def lock_own_claim(
    session: Session, job_id: UUID, attempts: int
) -> BackgroundJob | None:
    """Lock the row and return it only while this worker's claim still holds."""
    record = session.get(BackgroundJob, job_id, with_for_update=True)
    if (
        record is None
        or record.status != QueueStatus.PROCESSING.value
        or record.attempts != attempts
    ):
        return None
    return record


def _record_failure(
    session_factory: sessionmaker[Session],
    job_id: UUID,
    tenant_id: UUID | None,
    attempts: int,
    error: Exception,
    now: Callable[[], datetime] | None,
) -> None:
    summary = f"{type(error).__name__}: {error}"[:500]
    with transaction_session(
        session_factory, RequestContext(tenant_id=tenant_id)
    ) as session:
        record = lock_own_claim(session, job_id, attempts)
        if record is None:
            return
        if attempts >= MAX_JOB_ATTEMPTS:
            fail_queue_record(record, error=summary)
            return
        delay = retry_delay(attempts)
        retry_queue_record(
            record,
            error=summary,
            available_time=now() + delay if now is not None else func.now() + delay,
        )
