from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import RequestContext, transaction_session
from app.platform import jobs, worker
from app.platform.models import BackgroundJob
from app.platform.work_queue import BackgroundJobDraft, enqueue_background_job

Factory = sessionmaker[Session]


def test_worker_runs_due_schedulers_once_per_interval_and_drains_jobs(
    schema_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    done: list[str] = []

    def record(session: Session, job: BackgroundJob, now: datetime) -> None:
        done.append(job.idempotency_key)

    monkeypatch.setattr(jobs, "HANDLERS", {"demo": record})

    def scheduler(factory: Factory, now: datetime) -> int:
        with transaction_session(factory, RequestContext()) as session:
            enqueue_background_job(
                session, BackgroundJobDraft("demo", {}, f"demo:{now.date()}")
            )
        return 1

    monkeypatch.setattr(jobs, "SCHEDULERS", [scheduler])
    instance = worker.Worker(
        schema_session_factory, schedule_interval=timedelta(hours=1)
    )
    now = datetime.now(UTC) + timedelta(seconds=1)
    assert instance.run_once(now) is True
    assert (
        instance.run_once(now + timedelta(minutes=5)) is False
    )  # scheduler not due again
    assert done == [f"demo:{now.date()}"]
    assert (
        instance.run_once(now + timedelta(hours=2)) is False
    )  # same key: already completed
    with schema_session_factory() as session:
        assert session.query(BackgroundJob).count() == 1


def test_run_once_flag_drains_the_queue_and_returns(
    schema_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    done: list[int] = []

    def record(session: Session, job: BackgroundJob, now: datetime) -> None:
        done.append(1)

    monkeypatch.setattr(jobs, "HANDLERS", {"demo": record})
    monkeypatch.setattr(jobs, "SCHEDULERS", [])
    with transaction_session(schema_session_factory, RequestContext()) as session:
        for index in range(3):
            enqueue_background_job(session, BackgroundJobDraft("demo", {}, f"k{index}"))
    worker.Worker(schema_session_factory).run(once=True)
    assert len(done) == 3


def test_health_check_reports_database_reachability(
    schema_session_factory: Factory,
) -> None:
    assert worker.worker_is_healthy(schema_session_factory) is True


def test_unreachable_database_is_unhealthy() -> None:
    from sqlalchemy import create_engine

    engine = create_engine("postgresql+psycopg://nobody@127.0.0.1:1/none")
    assert worker.worker_is_healthy(sessionmaker(bind=engine)) is False
