import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import RequestContext, transaction_session
from app.platform import jobs
from app.platform.jobs import (
    MAX_JOB_ATTEMPTS,
    JobHandler,
    register_job_handler,
    register_scheduler,
    retry_delay,
    run_one_background_job,
    run_schedulers,
)
from app.platform.models import BackgroundJob, OutboxMessage, QueueStatus
from app.platform.work_queue import (
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

Factory = sessionmaker[Session]
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def _enqueue_job(
    factory: Factory, key: str = "k1", *, tenant: UUID | None = None
) -> UUID:
    with transaction_session(factory, RequestContext(tenant_id=tenant)) as session:
        return enqueue_background_job(
            session, BackgroundJobDraft("demo.run", {"n": 1}, key)
        )


def _job(factory: Factory, job_id: UUID) -> dict[str, object]:
    with factory() as session:
        job = session.get(BackgroundJob, job_id)
        assert job is not None
        return {
            "status": job.status,
            "attempts": job.attempts,
            "error": job.last_error,
            "available": job.available_time,
            "claimed": job.claimed_time,
        }


def test_enqueue_is_idempotent_and_records_the_tenant(
    schema_session_factory: Factory,
) -> None:
    tenant = uuid4()
    first = _enqueue_job(schema_session_factory, "same", tenant=tenant)
    again = _enqueue_job(schema_session_factory, "same", tenant=tenant)
    assert first == again
    with schema_session_factory() as session:
        job = session.get(BackgroundJob, first)
        assert job is not None and job.tenant_id == tenant
        assert (job.status, job.attempts) == ("pending", 0)


def test_claim_complete_lifecycle(schema_session_factory: Factory) -> None:
    job_id = _enqueue_job(schema_session_factory)
    with transaction_session(schema_session_factory, RequestContext()) as session:
        job = claim_next_background_job(session)
        assert job is not None and job.id == job_id
        assert (job.status, job.attempts) == ("processing", 1)
        assert job.claimed_time is not None
        complete_queue_record(job)
    assert _job(schema_session_factory, job_id)["status"] == "completed"
    with transaction_session(schema_session_factory, RequestContext()) as session:
        assert claim_next_background_job(session) is None


def test_retry_and_fail_require_a_claim_and_delay_the_next_claim(
    schema_session_factory: Factory,
) -> None:
    job_id = _enqueue_job(schema_session_factory)
    with transaction_session(schema_session_factory, RequestContext()) as session:
        record = session.get(BackgroundJob, job_id)
        assert record is not None
        with pytest.raises(ValueError, match="claimed"):
            fail_queue_record(record, error="x")
        job = claim_next_background_job(session)
        assert job is not None
        retry_queue_record(
            job, error="boom", available_time=datetime.now(UTC) + timedelta(hours=1)
        )
    assert _job(schema_session_factory, job_id)["status"] == "pending"
    with transaction_session(schema_session_factory, RequestContext()) as session:
        assert claim_next_background_job(session) is None


def test_two_claimers_never_take_the_same_row(schema_session_factory: Factory) -> None:
    first = _enqueue_job(schema_session_factory, "a")
    second = _enqueue_job(schema_session_factory, "b")
    claimed: list[UUID] = []
    with transaction_session(schema_session_factory, RequestContext()) as one:
        job_one = claim_next_background_job(one)
        assert job_one is not None
        claimed.append(job_one.id)
        # A second worker, while the first transaction is still open.
        with transaction_session(schema_session_factory, RequestContext()) as two:
            job_two = claim_next_background_job(two)
            assert job_two is not None
            claimed.append(job_two.id)
            assert claim_next_background_job(two) is None
    assert sorted(claimed) == sorted([first, second])


def test_parallel_workers_drain_every_job_exactly_once(
    schema_session_factory: Factory,
) -> None:
    ids = {_enqueue_job(schema_session_factory, f"p{i}") for i in range(12)}
    seen: list[UUID] = []
    lock = threading.Lock()

    def work() -> None:
        while True:
            with transaction_session(
                schema_session_factory, RequestContext()
            ) as session:
                job = claim_next_background_job(session)
                if job is None:
                    return
                with lock:
                    seen.append(job.id)
                complete_queue_record(job)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(seen) == sorted(ids)


def test_a_stale_claim_is_taken_again_and_counts_the_attempt(
    schema_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("QUEUE_CLAIM_TIMEOUT_SECONDS", "60")
    job_id = _enqueue_job(schema_session_factory)
    with transaction_session(schema_session_factory, RequestContext()) as session:
        assert claim_next_background_job(session) is not None
    with transaction_session(schema_session_factory, RequestContext()) as session:
        assert claim_next_background_job(session) is None  # still fresh
    with schema_session_factory.begin() as session:
        session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == job_id)
            .values(claimed_time=datetime.now(UTC) - timedelta(minutes=5))
        )
    with transaction_session(schema_session_factory, RequestContext()) as session:
        job = claim_next_background_job(session)
        assert job is not None and job.attempts == 2
        complete_queue_record(job)


def test_tenant_context_limits_the_claim_to_that_tenant(
    schema_session_factory: Factory,
) -> None:
    mine, other = uuid4(), uuid4()
    _enqueue_job(schema_session_factory, "other", tenant=other)
    mine_id = _enqueue_job(schema_session_factory, "mine", tenant=mine)
    with transaction_session(
        schema_session_factory, RequestContext(tenant_id=mine)
    ) as session:
        job = claim_next_background_job(session)
        assert job is not None and job.id == mine_id
        assert claim_next_background_job(session) is None


def test_outbox_claim_filters_by_topic_and_stores_the_provider_id(
    schema_session_factory: Factory,
) -> None:
    with transaction_session(schema_session_factory, RequestContext()) as session:
        enqueue_outbox_message(session, OutboxMessageDraft("a", {"x": 1}, "ob-a"))
        wanted = enqueue_outbox_message(
            session, OutboxMessageDraft("b", {"x": 2}, "ob-b")
        )
        assert (
            enqueue_outbox_message(session, OutboxMessageDraft("b", {}, "ob-b"))
            == wanted
        )
    with transaction_session(schema_session_factory, RequestContext()) as session:
        message = claim_next_outbox_message(session, topic="b")
        assert message is not None and message.id == wanted
        message.provider_message_id = "provider-1"
        complete_queue_record(message)
    with schema_session_factory() as session:
        stored = session.get(OutboxMessage, wanted)
        assert stored is not None
        assert (stored.status, stored.provider_message_id) == (
            "completed",
            "provider-1",
        )


@pytest.mark.parametrize(
    "column, value",
    [
        ("status", "'weird'"),
        ("payload", "'[]'::jsonb"),
        ("job_type", "' '"),
        ("idempotency_key", "repeat('k', 201)"),
        ("attempts", "-1"),
    ],
)
def test_table_constraints_reject_invalid_rows(
    schema_session_factory: Factory, column: str, value: str
) -> None:
    values = {
        "id": "gen_random_uuid()",
        "job_type": "'t'",
        "payload": "'{}'::jsonb",
        "idempotency_key": "'k'",
    }
    values[column] = value
    with pytest.raises(IntegrityError):
        with schema_session_factory.begin() as session:
            session.execute(
                text(
                    f"INSERT INTO background_jobs ({', '.join(values)}) "
                    f"VALUES ({', '.join(values.values())})"
                )
            )


def _handlers(handler: JobHandler) -> dict[str, JobHandler]:
    return {"demo.run": handler}


def test_a_job_runs_in_its_tenant_context_and_completes(
    schema_session_factory: Factory,
) -> None:
    tenant = uuid4()
    job_id = _enqueue_job(schema_session_factory, tenant=tenant)
    seen: dict[str, object] = {}

    def handler(session: Session, job: BackgroundJob, now: datetime) -> None:
        seen["tenant"] = session.scalar(
            text("SELECT current_setting('app.current_tenant_id')")
        )
        seen["role"] = session.scalar(text("SELECT current_user"))
        seen["payload"] = job.payload
        seen["now"] = now

    assert run_one_background_job(
        schema_session_factory, now=lambda: NOW, handlers=_handlers(handler)
    )
    assert seen == {
        "tenant": str(tenant),
        "role": "shadow_app",
        "payload": {"n": 1},
        "now": NOW,
    }
    assert _job(schema_session_factory, job_id)["status"] == "completed"
    assert not run_one_background_job(
        schema_session_factory, handlers=_handlers(handler)
    )


def test_a_failing_job_is_retried_with_backoff_then_failed(
    schema_session_factory: Factory,
) -> None:
    job_id = _enqueue_job(schema_session_factory)
    calls: list[int] = []

    def handler(session: Session, job: BackgroundJob, now: datetime) -> None:
        calls.append(job.attempts)
        raise RuntimeError("boom")

    state: dict[str, object] = {}
    for attempt in range(1, MAX_JOB_ATTEMPTS + 1):
        with schema_session_factory.begin() as session:  # make it due again
            session.execute(
                update(BackgroundJob)
                .where(BackgroundJob.id == job_id)
                .values(available_time=datetime.now(UTC) - timedelta(seconds=1))
            )
        assert run_one_background_job(
            schema_session_factory, now=lambda: NOW, handlers=_handlers(handler)
        )
        state = _job(schema_session_factory, job_id)
        assert state["attempts"] == attempt
        assert state["error"] == "RuntimeError: boom"
        if attempt < MAX_JOB_ATTEMPTS:
            assert state["status"] == "pending"
            assert state["available"] == NOW + retry_delay(attempt)
    assert state["status"] == "failed"
    assert calls == list(range(1, MAX_JOB_ATTEMPTS + 1))


def test_a_job_with_no_handler_is_retried_not_lost(
    schema_session_factory: Factory,
) -> None:
    job_id = _enqueue_job(schema_session_factory)
    assert run_one_background_job(schema_session_factory, handlers={})
    state = _job(schema_session_factory, job_id)
    assert state["status"] == "pending" and "no handler" in str(state["error"])


def test_a_job_claimed_too_many_times_is_failed_without_running(
    schema_session_factory: Factory,
) -> None:
    job_id = _enqueue_job(schema_session_factory)
    with schema_session_factory.begin() as session:
        session.execute(
            update(BackgroundJob)
            .where(BackgroundJob.id == job_id)
            .values(attempts=MAX_JOB_ATTEMPTS)
        )
    ran: list[bool] = []

    def handler(session: Session, job: BackgroundJob, now: datetime) -> None:
        ran.append(True)

    assert run_one_background_job(schema_session_factory, handlers=_handlers(handler))
    assert not ran
    assert _job(schema_session_factory, job_id)["status"] == QueueStatus.FAILED.value


def test_handler_registry_rejects_duplicates_and_scheduler_failures_are_isolated(
    schema_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jobs, "HANDLERS", {})
    monkeypatch.setattr(jobs, "SCHEDULERS", [])

    def noop(session: Session, job: BackgroundJob, now: datetime) -> None:
        return None

    register_job_handler("x", noop)
    with pytest.raises(ValueError, match="already"):
        register_job_handler("x", noop)

    def broken(_factory: Factory, _now: datetime) -> int:
        raise RuntimeError("no")

    def working(_factory: Factory, _now: datetime) -> int:
        return 2

    register_scheduler(broken)
    register_scheduler(working)
    assert run_schedulers(schema_session_factory, NOW) == 2


def test_retry_delay_is_bounded_exponential() -> None:
    delays: Callable[[int], timedelta] = retry_delay
    assert [delays(n) for n in (1, 2, 3)] == [timedelta(minutes=m) for m in (1, 2, 4)]
    assert delays(50) == timedelta(minutes=60)
