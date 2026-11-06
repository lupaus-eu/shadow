from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, text

from app.database import (
    RequestContext,
    create_database_engine,
    create_session_factory,
    transaction_session,
)
from app.work_queue import (
    BackgroundJobDraft,
    OutboxMessageDraft,
    claim_next_background_job,
    claim_next_outbox_message,
    complete_queue_record,
    enqueue_background_job,
    enqueue_outbox_message,
    fail_queue_record,
    retry_queue_record,
)
from app.models import BackgroundJob, OutboxMessage


def test_outbox_and_background_jobs_are_idempotent(database_url: str) -> None:
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    context = RequestContext(organization_id=uuid4())
    outbox_draft = OutboxMessageDraft(
        topic="foundation.email",
        payload={"message": "ready"},
        idempotency_key=f"outbox-{uuid4()}",
    )
    job_draft = BackgroundJobDraft(
        job_type="foundation.verify",
        payload={"check": "database"},
        idempotency_key=f"job-{uuid4()}",
    )

    with transaction_session(session_factory, context) as session:
        outbox_id = enqueue_outbox_message(session, outbox_draft)
        job_id = enqueue_background_job(session, job_draft)

    with transaction_session(session_factory, context) as session:
        duplicate_outbox_id = enqueue_outbox_message(session, outbox_draft)
        duplicate_job_id = enqueue_background_job(session, job_draft)

    assert duplicate_outbox_id == outbox_id
    assert duplicate_job_id == job_id

    with engine.connect() as connection:
        outbox = connection.execute(
            text(
                """
                SELECT organization_id, status, attempts, payload
                FROM outbox_messages
                WHERE id = :id
                """
            ),
            {"id": outbox_id},
        ).one()
        job = connection.execute(
            text(
                """
                SELECT organization_id, status, attempts, payload
                FROM background_jobs
                WHERE id = :id
                """
            ),
            {"id": job_id},
        ).one()

    assert outbox._mapping == {
        "organization_id": context.organization_id,
        "status": "pending",
        "attempts": 0,
        "payload": {"message": "ready"},
    }
    assert job._mapping == {
        "organization_id": context.organization_id,
        "status": "pending",
        "attempts": 0,
        "payload": {"check": "database"},
    }


def test_claims_are_atomic_and_queue_records_have_a_retry_lifecycle(
    database_url: str,
) -> None:
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    context = RequestContext(organization_id=uuid4())

    with transaction_session(session_factory, context) as session:
        outbox_id = enqueue_outbox_message(
            session,
            OutboxMessageDraft(
                topic="foundation.email",
                payload={"message": "claim me"},
                idempotency_key=f"outbox-claim-{uuid4()}",
            ),
        )
        job_id = enqueue_background_job(
            session,
            BackgroundJobDraft(
                job_type="foundation.verify",
                payload={"check": "claim me"},
                idempotency_key=f"job-claim-{uuid4()}",
            ),
        )

    with transaction_session(session_factory, context) as first_session:
        claimed_outbox = claim_next_outbox_message(first_session)
        assert claimed_outbox is not None
        assert claimed_outbox.id == outbox_id
        assert claimed_outbox.status == "processing"
        assert claimed_outbox.attempts == 1
        assert claimed_outbox.claimed_at is not None

        with transaction_session(session_factory, context) as competing_session:
            assert claim_next_outbox_message(competing_session) is None

        retry_at = datetime.now(UTC) + timedelta(minutes=5)
        retry_queue_record(
            claimed_outbox,
            error="temporary delivery error",
            available_at=retry_at,
        )

    with transaction_session(session_factory, context) as session:
        assert claim_next_outbox_message(session) is None
        retried_outbox = session.get(OutboxMessage, outbox_id)
        assert retried_outbox is not None
        assert retried_outbox.status == "pending"
        assert retried_outbox.claimed_at is None
        assert retried_outbox.last_error == "temporary delivery error"
        assert retried_outbox.available_at == retry_at

        claimed_job = claim_next_background_job(session)
        assert claimed_job is not None
        assert claimed_job.id == job_id
        fail_queue_record(claimed_job, error="permanent processing error")

    with transaction_session(session_factory, context) as session:
        failed_job = session.scalar(
            select(BackgroundJob).where(BackgroundJob.id == job_id)
        )
        assert failed_job is not None
        assert failed_job.status == "failed"
        assert failed_job.last_error == "permanent processing error"
        assert failed_job.claimed_at is None

        retried_outbox = session.get(OutboxMessage, outbox_id)
        assert retried_outbox is not None
        retried_outbox.available_at = datetime.now(UTC) - timedelta(seconds=1)

    with transaction_session(session_factory, context) as session:
        claimed_outbox = claim_next_outbox_message(session)
        assert claimed_outbox is not None
        assert claimed_outbox.attempts == 2
        complete_queue_record(claimed_outbox)

    with transaction_session(session_factory, context) as session:
        completed_outbox = session.get(OutboxMessage, outbox_id)
        assert completed_outbox is not None
        assert completed_outbox.status == "completed"
        assert completed_outbox.claimed_at is None
