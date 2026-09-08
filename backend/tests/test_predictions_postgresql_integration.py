# pyright: reportPrivateUsage=false

import os
import uuid
from collections.abc import Generator
from datetime import date
from urllib.parse import quote

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.org_states.models import Event, Scenario, Timeserie, TimeserieValue
from app.api.v1.organisations.models import Organisation
from app.api.v1.predictions.schemas import PredictionCreateRequest
from app.api.v1.users.models import User
from app.core.config import Settings, get_sqlalchemy_database_url
from app.core.migrations import UpCommand, execute_command

TEST_DATABASE_ENV = "MIGRATION_TEST_DATABASE_URL"


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
