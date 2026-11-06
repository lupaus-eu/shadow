from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import BackgroundJob, OutboxMessage, QueueStatus

QueueRecord = OutboxMessage | BackgroundJob


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


def _current_organization_id(session: Session) -> UUID | None:
    return session.scalar(
        text(
            """
            SELECT NULLIF(
                current_setting('app.current_organization_id', true),
                ''
            )::uuid
            """
        )
    )


def enqueue_outbox_message(session: Session, draft: OutboxMessageDraft) -> UUID:
    message_id = uuid4()
    inserted_id = session.scalar(
        insert(OutboxMessage)
        .values(
            id=message_id,
            organization_id=_current_organization_id(session),
            topic=draft.topic,
            payload=draft.payload,
            idempotency_key=draft.idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(OutboxMessage.id)
    )
    if inserted_id is not None:
        return inserted_id

    return session.scalars(
        select(OutboxMessage.id).where(
            OutboxMessage.idempotency_key == draft.idempotency_key
        )
    ).one()


def enqueue_background_job(session: Session, draft: BackgroundJobDraft) -> UUID:
    job_id = uuid4()
    inserted_id = session.scalar(
        insert(BackgroundJob)
        .values(
            id=job_id,
            organization_id=_current_organization_id(session),
            job_type=draft.job_type,
            payload=draft.payload,
            idempotency_key=draft.idempotency_key,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(BackgroundJob.id)
    )
    if inserted_id is not None:
        return inserted_id

    return session.scalars(
        select(BackgroundJob.id).where(
            BackgroundJob.idempotency_key == draft.idempotency_key
        )
    ).one()


def _claim_next(
    session: Session,
    model: type[OutboxMessage] | type[BackgroundJob],
    *,
    topic: str | None = None,
) -> QueueRecord | None:
    organization_id = _current_organization_id(session)
    statement = (
        select(model)
        .where(
            model.status == QueueStatus.PENDING.value,
            model.available_at <= func.now(),
        )
        .order_by(model.available_at, model.created_at, model.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if organization_id is not None:
        statement = statement.where(model.organization_id == organization_id)
    if topic is not None:
        if model is not OutboxMessage:
            raise ValueError("topic filtering is only supported for outbox messages")
        statement = statement.where(OutboxMessage.topic == topic)

    record = session.scalars(statement).first()
    if record is None:
        return None

    record.status = QueueStatus.PROCESSING.value
    record.attempts += 1
    record.claimed_at = datetime.now(UTC)
    record.last_error = None
    session.flush()
    return record


def claim_next_outbox_message(
    session: Session,
    *,
    topic: str | None = None,
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
    record.claimed_at = None
    record.last_error = None


def retry_queue_record(
    record: QueueRecord,
    *,
    error: str,
    available_at: datetime,
) -> None:
    _require_processing(record)
    record.status = QueueStatus.PENDING.value
    record.available_at = available_at
    record.claimed_at = None
    record.last_error = error


def fail_queue_record(record: QueueRecord, *, error: str) -> None:
    _require_processing(record)
    record.status = QueueStatus.FAILED.value
    record.claimed_at = None
    record.last_error = error
