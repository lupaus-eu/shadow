"""Durable PostgreSQL work queues (ADR-019; from Yearclock ``work_queue.py``, 6848e72).

Rows are claimed with ``FOR UPDATE SKIP LOCKED``, so several workers never take
the same row. A row claimed but never finished (a crashed worker) becomes
claimable again after the claim timeout; its attempts count keeps growing, so
the caller can fail it eventually.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import SQLColumnExpression

from app.platform.models import BackgroundJob, OutboxMessage, QueueStatus

QueueRecord = OutboxMessage | BackgroundJob


def claim_timeout() -> timedelta:
    raw = os.getenv("QUEUE_CLAIM_TIMEOUT_SECONDS", "900")
    try:
        seconds = int(raw)
    except ValueError:
        raise ValueError(
            f"QUEUE_CLAIM_TIMEOUT_SECONDS must be an integer, got {raw!r}"
        ) from None
    if seconds < 1:
        raise ValueError("QUEUE_CLAIM_TIMEOUT_SECONDS must be at least 1")
    return timedelta(seconds=seconds)


@dataclass(frozen=True)
class OutboxMessageDraft:
    topic: str
    payload: dict[str, Any]
    idempotency_key: str


@dataclass(frozen=True)
class BackgroundJobDraft:
    job_type: str
    payload: dict[str, Any]
    idempotency_key: str


def _current_tenant_id(session: Session) -> UUID | None:
    return session.scalar(
        text("SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid")
    )


def enqueue_outbox_message(session: Session, draft: OutboxMessageDraft) -> UUID:
    """Queue a message; a repeated key (within the tenant) returns the existing id."""
    tenant_id = _current_tenant_id(session)
    inserted_id = session.scalar(
        insert(OutboxMessage)
        .values(
            id=uuid4(),
            tenant_id=tenant_id,
            topic=draft.topic,
            payload=draft.payload,
            idempotency_key=draft.idempotency_key,
        )
        .on_conflict_do_nothing(constraint="uq_outbox_messages_tenant_key")
        .returning(OutboxMessage.id)
    )
    if inserted_id is not None:
        return inserted_id
    return session.scalars(
        select(OutboxMessage.id).where(
            OutboxMessage.idempotency_key == draft.idempotency_key,
            OutboxMessage.tenant_id.is_not_distinct_from(tenant_id),
        )
    ).one()


def enqueue_background_job(session: Session, draft: BackgroundJobDraft) -> UUID:
    """Queue a job; a repeated key (within the tenant) returns the existing id."""
    tenant_id = _current_tenant_id(session)
    inserted_id = session.scalar(
        insert(BackgroundJob)
        .values(
            id=uuid4(),
            tenant_id=tenant_id,
            job_type=draft.job_type,
            payload=draft.payload,
            idempotency_key=draft.idempotency_key,
        )
        .on_conflict_do_nothing(constraint="uq_background_jobs_tenant_key")
        .returning(BackgroundJob.id)
    )
    if inserted_id is not None:
        return inserted_id
    return session.scalars(
        select(BackgroundJob.id).where(
            BackgroundJob.idempotency_key == draft.idempotency_key,
            BackgroundJob.tenant_id.is_not_distinct_from(tenant_id),
        )
    ).one()


def _claim_next(
    session: Session,
    model: type[OutboxMessage] | type[BackgroundJob],
    *,
    topic: str | None = None,
) -> QueueRecord | None:
    tenant_id = _current_tenant_id(session)
    stale_before = func.now() - claim_timeout()
    statement = (
        select(model)
        .where(
            or_(
                and_(
                    model.status == QueueStatus.PENDING.value,
                    model.available_time <= func.now(),
                ),
                and_(
                    model.status == QueueStatus.PROCESSING.value,
                    model.claimed_time <= stale_before,
                ),
            )
        )
        .order_by(model.available_time, model.created_time, model.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if tenant_id is not None:
        statement = statement.where(model.tenant_id == tenant_id)
    if topic is not None:
        if model is not OutboxMessage:
            raise ValueError("topic filtering is only supported for outbox messages")
        statement = statement.where(OutboxMessage.topic == topic)

    record = session.scalars(statement).first()
    if record is None:
        return None

    record.status = QueueStatus.PROCESSING.value
    record.attempts += 1
    record.claimed_time = func.now()
    record.last_error = None
    session.flush()
    return record


def claim_next_outbox_message(
    session: Session, *, topic: str | None = None
) -> OutboxMessage | None:
    record = _claim_next(session, OutboxMessage, topic=topic)
    if record is None or isinstance(record, OutboxMessage):
        return record
    raise TypeError("expected an outbox message")


def claim_next_background_job(session: Session) -> BackgroundJob | None:
    record = _claim_next(session, BackgroundJob)
    if record is None or isinstance(record, BackgroundJob):
        return record
    raise TypeError("expected a background job")


def _require_processing(record: QueueRecord) -> None:
    if record.status != QueueStatus.PROCESSING.value:
        raise ValueError("queue record must be claimed before its state can change")


def complete_queue_record(record: QueueRecord) -> None:
    _require_processing(record)
    record.status = QueueStatus.COMPLETED.value
    record.claimed_time = None
    record.last_error = None


def retry_queue_record(
    record: QueueRecord,
    *,
    error: str,
    available_time: datetime | SQLColumnExpression[datetime],
) -> None:
    _require_processing(record)
    record.status = QueueStatus.PENDING.value
    record.available_time = available_time
    record.claimed_time = None
    record.last_error = error


def fail_queue_record(record: QueueRecord, *, error: str) -> None:
    _require_processing(record)
    record.status = QueueStatus.FAILED.value
    record.claimed_time = None
    record.last_error = error
