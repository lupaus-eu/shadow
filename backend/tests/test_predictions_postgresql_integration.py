# pyright: reportPrivateUsage=false

import os
import threading
import time
import uuid
from collections.abc import Generator
from datetime import UTC, date, datetime
from urllib.parse import quote

import psycopg
import pytest
from fastapi import HTTPException
from psycopg import sql
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.org_states.models import Event, Scenario, Timeserie, TimeserieValue
from app.api.v1.organisations.models import Organisation
from app.api.v1.predictions.models import (
    PredictionModelResult,
    PredictionPoint,
    PredictionRequest,
    PredictionVersion,
)
from app.api.v1.predictions.schemas import PredictionCreateRequest
from app.api.v1.users.models import User
from app.core.config import Settings, get_sqlalchemy_database_url
from app.core.migrations import UpCommand, execute_command

TEST_DATABASE_ENV = "MIGRATION_TEST_DATABASE_URL"


def _blocked_calculation(_: str, sender: object) -> None:
    del sender
    time.sleep(60)


def _crashed_calculation(_: str, sender: object) -> None:
    del sender
    raise RuntimeError("deliberate child crash")


@pytest.fixture
def prediction_postgresql_session_factory() -> Generator[
    sessionmaker[Session], None, None
]:
    base_url = os.getenv(TEST_DATABASE_ENV)
    if base_url is None:
        pytest.skip(f"{TEST_DATABASE_ENV} is not configured")

    schema_name = f"prediction_test_{uuid.uuid4().hex}"
    with psycopg.connect(base_url, autocommit=True) as connection:
        connection.execute(
            sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
        )
    separator = "&" if "?" in base_url else "?"
    schema_url = f"{base_url}{separator}options={quote(f'-csearch_path={schema_name}')}"
    execute_command(UpCommand(), database_url=schema_url)
    settings = Settings(DATABASE_URL=schema_url)
    engine = create_engine(get_sqlalchemy_database_url(settings))
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    try:
        yield factory
    finally:
        engine.dispose()
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema_name))
            )


def test_preparation_uses_one_repeatable_read_snapshot_during_source_edit(
    prediction_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.main import app

    del app

    from app.api.v1.predictions import service

    factory = prediction_postgresql_session_factory
    with factory() as fixture_session:
        user = User(name="Forecast Tester", email="forecast@test.local", role="admin")
        fixture_session.add(user)
        fixture_session.flush()
        organisation = Organisation(
            organisation_key="snapshot-org",
            name="Snapshot Org",
            created_by=user.user_id,
        )
        fixture_session.add(organisation)
        fixture_session.flush()
        scenario = Scenario(
            organisation_id=organisation.organisation_id,
            scenario_key="plan",
            name="Plan",
            created_by=user.user_id,
        )
        fixture_session.add(scenario)
        fixture_session.flush()
        metric = Timeserie(
            scenario_id=scenario.scenario_id,
            timeserie_key="revenue",
            name="Revenue",
            time_unit="month",
            value_unit="number",
            created_by=user.user_id,
        )
        fixture_session.add(metric)
        fixture_session.flush()
        fixture_session.add_all(
            TimeserieValue(
                timeserie_id=metric.timeserie_id,
                date=date(2025, month, 1),
                value={"value": month * 10},
                created_by=user.user_id,
            )
            for month in range(1, 5)
        )
        fixture_session.commit()
        actor_user_id = user.user_id
        scenario_id = scenario.scenario_id

    original_target_history = service._target_history

    def edit_after_history_read(
        read_session: Session,
        target_metric: Timeserie,
        payload: PredictionCreateRequest,
        first_period: date,
    ) -> list[service.Observation]:
        history = original_target_history(
            read_session, target_metric, payload, first_period
        )
        with factory() as writer:
            writer.add(
                Event(
                    scenario_id=scenario_id,
                    event_key="concurrent-event",
                    name="Concurrent event",
                    target_date=date(2025, 5, 10),
                    created_by=actor_user_id,
                )
            )
            writer.commit()
        return history

    monkeypatch.setattr(service, "_target_history", edit_after_history_read)
    payload = PredictionCreateRequest(
        targetScenarioIds=["plan"],
        startDate=date(2025, 5, 1),
        endDate=date(2025, 6, 30),
        cutoffMode="asOfStart",
        manualSeasonalPeriods={"revenue": 2},
        name="Consistent snapshot",
    )
    with factory() as request_session:
        snapshot = service.prepare_prediction_snapshot(
            request_session,
            "snapshot-org",
            payload,
            actor_user_id=actor_user_id,
        )

    target = snapshot.targets[0]
    assert [item.features["eventCount"] for item in target.prediction_periods] == [
        0.0,
        0.0,
    ]


def _seed_worker_request(
    factory: sessionmaker[Session], *, name: str
) -> tuple[str, int]:
    from app.api.v1.predictions import service

    with factory() as fixture_session:
        user = fixture_session.scalar(select(User).where(User.email == "worker@test"))
        if user is None:
            user = User(name="Worker Tester", email="worker@test", role="admin")
            fixture_session.add(user)
            fixture_session.flush()
            organisation = Organisation(
                organisation_key="worker-org",
                name="Worker Org",
                created_by=user.user_id,
            )
            fixture_session.add(organisation)
            fixture_session.flush()
            scenario = Scenario(
                organisation_id=organisation.organisation_id,
                scenario_key="plan",
                name="Plan",
                created_by=user.user_id,
            )
            fixture_session.add(scenario)
            fixture_session.flush()
            metric = Timeserie(
                scenario_id=scenario.scenario_id,
                timeserie_key="revenue",
                name="Revenue",
                time_unit="month",
                value_unit="number",
                created_by=user.user_id,
            )
            fixture_session.add(metric)
            fixture_session.flush()
            fixture_session.add_all(
                TimeserieValue(
                    timeserie_id=metric.timeserie_id,
                    date=date(2025, month, 1),
                    value={"value": month * 10},
                    created_by=user.user_id,
                )
                for month in range(1, 5)
            )
            fixture_session.commit()
        actor_id = user.user_id
    payload = PredictionCreateRequest(
        targetScenarioIds=["plan"],
        startDate=date(2025, 5, 1),
        endDate=date(2025, 6, 30),
        cutoffMode="asOfStart",
        manualSeasonalPeriods={"revenue": 2},
        name=name,
    )
    with factory() as request_session:
        summary = service.enqueue_prediction(
            request_session, "worker-org", payload, actor_id
        )
    return summary.id, actor_id


def test_worker_owns_global_lock_claims_fifo_and_publishes_frozen_snapshot(
    prediction_postgresql_session_factory: sessionmaker[Session],
) -> None:
    from app.api.v1.predictions.worker import (
        WORKER_ADVISORY_LOCK,
        PredictionWorker,
        worker_is_healthy,
    )

    factory = prediction_postgresql_session_factory
    first_key, _ = _seed_worker_request(factory, name="First")
    second_key, _ = _seed_worker_request(factory, name="Second")
    engine = factory.kw["bind"]
    assert engine is not None
    with factory() as session:
        latest_value = session.scalar(
            select(TimeserieValue).order_by(TimeserieValue.date.desc())
        )
        assert latest_value is not None
        latest_value.value = {"value": 9999}
        session.commit()

    with engine.connect() as owner:
        assert owner.scalar(
            text("SELECT pg_try_advisory_lock(:key)"),
            {"key": WORKER_ADVISORY_LOCK},
        )
        assert worker_is_healthy(engine)
        assert not PredictionWorker(engine).run(once=True)
        owner.execute(
            text("SELECT pg_advisory_unlock(:key)"),
            {"key": WORKER_ADVISORY_LOCK},
        )

    assert PredictionWorker(engine).run(once=True)
    with factory() as session:
        first = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == first_key
            )
        )
        second = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == second_key
            )
        )
        assert first is not None and first.state == "completed"
        assert first.completed_prediction_version_id is not None
        assert second is not None and second.state == "queued"
        version = session.get(
            PredictionVersion, first.completed_prediction_version_id
        )
        assert version is not None and version.created_by == first.submitted_by
        point = session.scalar(
            select(PredictionPoint)
            .join(PredictionModelResult)
            .where(PredictionModelResult.result_kind == "naive")
            .order_by(PredictionPoint.date)
        )
        assert point is not None and point.value == 40.0


def test_concurrent_name_admission_allows_only_one_case_variant(
    prediction_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.v1.predictions import service

    factory = prediction_postgresql_session_factory
    seed_key, actor_id = _seed_worker_request(factory, name="Seed")
    with factory() as session:
        service.cancel_prediction_request(session, "worker-org", seed_key, actor_id)
    barrier = threading.Barrier(2)
    original_lock = service._lock_prediction_names

    def synchronized_lock(session: Session, organisation_id: int) -> None:
        barrier.wait(timeout=5)
        original_lock(session, organisation_id)

    monkeypatch.setattr(service, "_lock_prediction_names", synchronized_lock)
    outcomes: list[str | int] = []

    def submit(name: str) -> None:
        payload = PredictionCreateRequest(
            targetScenarioIds=["plan"],
            startDate=date(2025, 5, 1),
            endDate=date(2025, 6, 30),
            cutoffMode="asOfStart",
            manualSeasonalPeriods={"revenue": 2},
            name=name,
        )
        try:
            with factory() as session:
                outcomes.append(
                    service.enqueue_prediction(
                        session, "worker-org", payload, actor_id
                    ).state
                )
        except HTTPException as exc:
            outcomes.append(exc.status_code)

    threads = [
        threading.Thread(target=submit, args=("Concurrent",)),
        threading.Thread(target=submit, args=("CONCURRENT",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
        assert not thread.is_alive()
    assert sorted(outcomes, key=str) == [409, "queued"]


def test_worker_child_crash_and_publication_failure_leave_no_partial_version(
    prediction_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.v1.predictions import service
    from app.api.v1.predictions.worker import PredictionWorker

    factory = prediction_postgresql_session_factory
    crashed_key, _ = _seed_worker_request(factory, name="Crash")
    engine = factory.kw["bind"]
    assert engine is not None
    assert PredictionWorker(engine, child_target=_crashed_calculation).run(once=True)
    with factory() as session:
        crashed = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == crashed_key
            )
        )
        assert crashed is not None and crashed.state == "failed"
        assert crashed.failure_code == "CALCULATION_PROCESS_FAILED"
        assert session.scalar(select(PredictionVersion)) is None

    publication_key, _ = _seed_worker_request(factory, name="Publication")

    def fail_publication(*_: object) -> object:
        raise RuntimeError("deliberate publication failure")

    monkeypatch.setattr(service, "persist_prediction", fail_publication)
    assert PredictionWorker(engine).run(once=True)
    with factory() as session:
        publication = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == publication_key
            )
        )
        assert publication is not None and publication.state == "failed"
        assert publication.failure_code == "PUBLICATION_FAILED"
        assert session.scalar(select(PredictionVersion)) is None
        assert session.scalar(select(PredictionModelResult)) is None
        assert session.scalar(select(PredictionPoint)) is None


def test_worker_promptly_cancels_and_reaps_a_blocked_child(
    prediction_postgresql_session_factory: sessionmaker[Session],
) -> None:
    from app.api.v1.predictions import service
    from app.api.v1.predictions.worker import PredictionWorker

    factory = prediction_postgresql_session_factory
    request_key, actor_id = _seed_worker_request(factory, name="Blocked")
    engine = factory.kw["bind"]
    assert engine is not None
    worker = PredictionWorker(engine, child_target=_blocked_calculation)
    thread = threading.Thread(target=lambda: worker.run(once=True))
    started = time.monotonic()
    thread.start()
    deadline = started + 5
    state: str | None = None
    while time.monotonic() < deadline:
        with factory() as session:
            state = session.scalar(
                select(PredictionRequest.state).where(
                    PredictionRequest.prediction_request_key == request_key
                )
            )
        if state == "running":
            break
        time.sleep(0.05)
    assert state == "running"

    with factory() as session:
        summary = service.cancel_prediction_request(
            session, "worker-org", request_key, actor_id
        )
    assert summary.state == "cancelling"
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert time.monotonic() - started < 5
    with factory() as session:
        request = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == request_key
            )
        )
        assert request is not None and request.state == "cancelled"
        assert request.worker_id is None
        assert session.scalar(select(PredictionVersion)) is None


@pytest.mark.parametrize("first_operation", ["cancel", "publish"])
def test_cancellation_and_publication_commit_order_determines_terminal_state(
    prediction_postgresql_session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    first_operation: str,
) -> None:
    from app.api.v1.predictions import service
    from app.api.v1.predictions.snapshots import PredictionInputSnapshot
    from app.api.v1.predictions.worker import PredictionWorker

    factory = prediction_postgresql_session_factory
    request_key, actor_id = _seed_worker_request(
        factory, name=f"Race {first_operation}"
    )
    with factory() as session:
        request = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == request_key
            )
        )
        assert request is not None
        snapshot = PredictionInputSnapshot.model_validate(request.input_snapshot)
        request.state = "running"
        request.start_time = datetime.now(UTC)
        request.worker_id = f"race-worker-{first_operation}"
        request_id = request.prediction_request_id
        session.commit()
    calculation = service.calculate_prediction(snapshot)

    first_locked = threading.Event()
    second_waiting = threading.Event()
    release_first = threading.Event()
    original_lock = service._lock_prediction_names

    def coordinated_lock(session: Session, organisation_id: int) -> None:
        operation = threading.current_thread().name
        if operation != first_operation:
            second_waiting.set()
        original_lock(session, organisation_id)
        if operation == first_operation:
            first_locked.set()
            assert release_first.wait(timeout=5)

    monkeypatch.setattr(service, "_lock_prediction_names", coordinated_lock)
    outcomes: dict[str, str] = {}
    errors: list[BaseException] = []

    def cancel() -> None:
        try:
            with factory() as session:
                outcomes["cancel"] = service.cancel_prediction_request(
                    session, "worker-org", request_key, actor_id
                ).state
        except BaseException as exc:
            errors.append(exc)

    def publish() -> None:
        engine = factory.kw["bind"]
        assert engine is not None
        worker = PredictionWorker(
            engine, worker_id=f"race-worker-{first_operation}"
        )
        try:
            with engine.connect() as lock_connection:
                worker._lock_connection = lock_connection
                outcomes["publish"] = worker._publish(
                    request_id, snapshot, calculation
                )
        except BaseException as exc:
            errors.append(exc)
        finally:
            worker._lock_connection = None

    operations = {"cancel": cancel, "publish": publish}
    second_operation = "publish" if first_operation == "cancel" else "cancel"
    first = threading.Thread(target=operations[first_operation], name=first_operation)
    second = threading.Thread(
        target=operations[second_operation], name=second_operation
    )
    first.start()
    assert first_locked.wait(timeout=5)
    second.start()
    assert second_waiting.wait(timeout=5)
    release_first.set()
    first.join(timeout=10)
    second.join(timeout=10)
    assert not first.is_alive() and not second.is_alive() and not errors

    with factory() as session:
        request = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == request_key
            )
        )
        assert request is not None
        versions = session.scalars(select(PredictionVersion)).all()
        if first_operation == "cancel":
            assert outcomes == {"cancel": "cancelling", "publish": "cancelled"}
            assert request.state == "cancelled"
            assert request.completed_prediction_version_id is None
            assert versions == []
        else:
            assert outcomes == {"publish": "completed", "cancel": "completed"}
            assert request.state == "completed"
            assert request.completed_prediction_version_id is not None
            assert len(versions) == 1


@pytest.mark.filterwarnings(
    "ignore:transaction already deassociated from connection:sqlalchemy.exc.SAWarning"
)
def test_lost_worker_ownership_stops_child_and_prevents_stale_publication(
    prediction_postgresql_session_factory: sessionmaker[Session],
) -> None:
    from app.api.v1.predictions.worker import PredictionWorker

    factory = prediction_postgresql_session_factory
    request_key, _ = _seed_worker_request(factory, name="Ownership loss")
    engine = factory.kw["bind"]
    assert engine is not None
    worker = PredictionWorker(engine, child_target=_blocked_calculation)
    errors: list[BaseException] = []

    def run_worker() -> None:
        try:
            worker.run(once=True)
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_worker)
    thread.start()
    deadline = time.monotonic() + 5
    state: str | None = None
    while time.monotonic() < deadline:
        with factory() as session:
            state = session.scalar(
                select(PredictionRequest.state).where(
                    PredictionRequest.prediction_request_key == request_key
                )
            )
        if state == "running" and worker._lock_connection is not None:
            break
        time.sleep(0.05)
    assert state == "running" and worker._lock_connection is not None
    worker._lock_connection.close()
    thread.join(timeout=5)
    assert not thread.is_alive() and errors
    with factory() as session:
        request = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == request_key
            )
        )
        assert request is not None and request.state == "running"
        assert session.scalar(select(PredictionVersion)) is None

    assert PredictionWorker(engine).run(once=True)
    with factory() as session:
        request = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == request_key
            )
        )
        assert request is not None and request.state == "failed"
        assert request.failure_code == "WORKER_INTERRUPTED"
        assert session.scalar(select(PredictionVersion)) is None


def test_worker_recovers_abandoned_requests_without_retry(
    prediction_postgresql_session_factory: sessionmaker[Session],
) -> None:
    from app.api.v1.predictions.worker import PredictionWorker

    factory = prediction_postgresql_session_factory
    running_key, actor_id = _seed_worker_request(factory, name="Interrupted")
    cancelling_key, _ = _seed_worker_request(factory, name="Stopping")
    now = datetime.now(UTC)
    with factory() as session:
        running = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == running_key
            )
        )
        cancelling = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == cancelling_key
            )
        )
        assert running is not None and cancelling is not None
        running.state = "running"
        running.start_time = now
        running.worker_id = "abandoned"
        cancelling.state = "cancelling"
        cancelling.start_time = now
        cancelling.worker_id = "abandoned"
        cancelling.cancelled_by = actor_id
        cancelling.cancellation_time = now
        session.commit()

    engine = factory.kw["bind"]
    assert engine is not None
    assert PredictionWorker(engine).run(once=True)
    with factory() as session:
        running = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == running_key
            )
        )
        cancelling = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == cancelling_key
            )
        )
        assert running is not None and running.state == "failed"
        assert running.failure_code == "WORKER_INTERRUPTED"
        assert cancelling is not None and cancelling.state == "cancelled"
        assert session.scalar(select(PredictionVersion)) is None
