import warnings
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol, cast

import pytest
from auth_helpers import authenticate_test_client
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.org_states.models import (
    DerivedMetricEquation,
    Scenario,
    Timeserie,
    TimeserieValue,
)
from app.api.v1.org_twin_structure.models import Metamodel
from app.api.v1.predictions.models import (
    PredictionModelResult,
    PredictionPoint,
    PredictionRequest,
    PredictionTarget,
    PredictionVersion,
)
from app.api.v1.predictions.schemas import PredictionCreateRequest
from app.api.v1.predictions.snapshots import (
    PredictionCalculation,
    PredictionInputSnapshot,
    SnapshotFeaturePeriod,
    SnapshotObservation,
)
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app


class _TestResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


_TEST_SESSION_FACTORIES: dict[int, sessionmaker[Session]] = {}


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        session.add(Metamodel(version=1))
        session.commit()
    return factory


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app()

    def override_get_db_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as test_client:
        _TEST_SESSION_FACTORIES[id(test_client)] = session_factory
        authenticate_test_client(test_client, session_factory)
        try:
            yield test_client
        finally:
            _TEST_SESSION_FACTORIES.pop(id(test_client), None)
    app.dependency_overrides.clear()


def _create_completed_prediction(
    client: TestClient, url: str, *, json: dict[str, object]
) -> _TestResponse:
    """Submit through the public API, then emulate a successful worker cycle."""
    from app.api.v1.predictions import service

    accepted = client.post(url, json=json)
    assert accepted.status_code == 202
    factory = _TEST_SESSION_FACTORIES[id(client)]
    with factory() as session:
        request = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == accepted.json()["id"]
            )
        )
        assert request is not None
        snapshot = PredictionInputSnapshot.model_validate(request.input_snapshot)
    calculation = service.calculate_prediction(snapshot)
    now = datetime.now(UTC)
    with factory() as session:
        request = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == accepted.json()["id"]
            )
        )
        assert request is not None
        version = service.persist_prediction(session, snapshot, calculation)
        request.state = "completed"
        request.start_time = now
        request.finish_time = now
        request.completed_prediction_version_id = version.prediction_version_id
        session.commit()
    response = client.get(
        f"/api/v1/organisations/{snapshot.organisation_key}/predictions/"
        f"{snapshot.prediction_key}"
    )
    response.status_code = 201
    return response


def _create_organisation(client: TestClient, name: str = "Forecast Org") -> str:
    response = client.post("/api/v1/organisations", json={"name": name})
    assert response.status_code == 201
    return str(response.json()["id"])


def _create_target_and_metrics(client: TestClient, organisation_key: str) -> str:
    scenario = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "Plan"},
    )
    assert scenario.status_code == 201
    target_key = str(scenario.json()["id"])
    response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/timeseries",
        json={
            "id": "revenue",
            "name": "Revenue",
            "unit": "EUR",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    )
    assert response.status_code == 201
    values = [
        {"date": "2025-01-01", "value": 10},
        {"date": "2025-02-01", "value": 20},
        {"date": "2025-03-01", "value": 30},
        {"date": "2025-04-01", "value": 40},
    ]
    response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/timeseries/revenue/values",
        json={"values": values},
    )
    assert response.status_code == 200
    return target_key


def _prediction_payload(target_key: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "targetScenarioIds": [target_key],
        "startDate": "2025-05-01",
        "endDate": "2025-06-30",
        "cutoffMode": "asOfStart",
        "manualSeasonalPeriods": {"revenue": 2},
    }
    payload.update(overrides)
    return payload


def _create_model_ready_target(client: TestClient) -> tuple[str, str]:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    values = [
        {
            "date": f"2024-{month:02d}-01",
            "value": float(100 + month * 3),
        }
        for month in range(1, 13)
    ]
    replacement = client.patch(
        (
            f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/"
            "timeseries/revenue/values"
        ),
        json={"values": values},
    )
    assert replacement.status_code == 200
    return organisation_key, target_key


def test_create_enqueues_frozen_request_and_exposes_status_apis(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.v1.predictions import service

    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)

    def must_not_calculate(_: object) -> object:
        raise AssertionError("HTTP submission must not fit prediction models")

    monkeypatch.setattr(service, "calculate_prediction", must_not_calculate)
    accepted = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="Queued forecast"),
    )

    assert accepted.status_code == 202
    summary = accepted.json()
    assert summary == {
        "id": summary["id"],
        "name": "Queued forecast",
        "state": "queued",
        "submittedTime": summary["submittedTime"],
        "startTime": None,
        "finishTime": None,
        "failureCode": None,
        "failureReason": None,
        "completedPredictionId": None,
    }
    assert accepted.headers["location"] == (
        f"/api/v1/organisations/{organisation_key}/prediction-requests/"
        f"{summary['id']}"
    )
    with session_factory() as session:
        request = session.scalar(select(PredictionRequest))
        assert request is not None
        assert request.submitted_by == 0
        assert request.input_snapshot["name"] == "Queued forecast"
        assert session.scalar(select(PredictionVersion)) is None

    listed = client.get(
        f"/api/v1/organisations/{organisation_key}/prediction-requests"
    )
    detailed = client.get(accepted.headers["location"])
    assert listed.status_code == 200 and listed.json() == [summary]
    assert detailed.status_code == 200 and detailed.json() == summary


def test_request_cancellation_is_idempotent_scoped_and_releases_name(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    accepted = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="Reusable"),
    )
    assert accepted.status_code == 202
    request_key = accepted.json()["id"]
    duplicate = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="REUSABLE"),
    )
    assert duplicate.status_code == 409

    cancelled = client.post(
        f"/api/v1/organisations/{organisation_key}/prediction-requests/"
        f"{request_key}/cancel"
    )
    repeated = client.post(
        f"/api/v1/organisations/{organisation_key}/prediction-requests/"
        f"{request_key}/cancel"
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert cancelled.json()["finishTime"] is not None
    assert repeated.json() == cancelled.json()
    with session_factory() as session:
        request = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == request_key
            )
        )
        assert request is not None and request.cancelled_by == 0

    reusable = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="reusable"),
    )
    assert reusable.status_code == 202
    reusable_key = reusable.json()["id"]
    with session_factory() as session:
        running = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == reusable_key
            )
        )
        assert running is not None
        running.state = "running"
        running.start_time = datetime.now(UTC)
        running.worker_id = "test-worker"
        session.commit()
    stopping = client.post(
        f"/api/v1/organisations/{organisation_key}/prediction-requests/"
        f"{reusable_key}/cancel"
    )
    repeated_stopping = client.post(
        f"/api/v1/organisations/{organisation_key}/prediction-requests/"
        f"{reusable_key}/cancel"
    )
    assert stopping.status_code == 200 and stopping.json()["state"] == "cancelling"
    assert repeated_stopping.json() == stopping.json()

    other_organisation = _create_organisation(client, "Request isolation org")
    assert (
        client.get(
            f"/api/v1/organisations/{other_organisation}/prediction-requests/"
            f"{request_key}"
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/organisations/{other_organisation}/prediction-requests/"
            f"{request_key}/cancel"
        ).status_code
        == 404
    )


def test_request_list_includes_all_active_and_only_50_recently_finished(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    active = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="Active"),
    )
    assert active.status_code == 202
    base_time = datetime.now(UTC)
    with session_factory() as session:
        active_request = session.scalar(select(PredictionRequest))
        assert active_request is not None
        session.add_all(
            PredictionRequest(
                prediction_request_key=f"finished-{index}",
                organisation_id=active_request.organisation_id,
                name=f"Finished {index}",
                input_snapshot={},
                state="failed",
                submitted_time=base_time + timedelta(seconds=index),
                start_time=base_time + timedelta(seconds=index),
                finish_time=base_time + timedelta(seconds=index),
                submitted_by=0,
                failure_code="FAILED",
                failure_reason="Safe reason.",
            )
            for index in range(55)
        )
        session.commit()

    response = client.get(
        f"/api/v1/organisations/{organisation_key}/prediction-requests"
    )
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 51
    assert rows[0]["id"] == active.json()["id"]
    assert [row["id"] for row in rows[1:]] == [
        f"finished-{index}" for index in range(54, 4, -1)
    ]


@pytest.mark.parametrize("role", ["consultant", "admin"])
def test_both_business_roles_can_inspect_and_cancel_another_users_request(
    client: TestClient,
    session_factory: sessionmaker[Session],
    role: str,
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    accepted = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name=f"Shared {role}"),
    )
    assert accepted.status_code == 202
    request_key = accepted.json()["id"]

    authenticate_test_client(
        client,
        session_factory,
        user_id=1,
        role=role,
        raw_session_id="r" * 43,
        csrf_token=f"{role}-csrf",
    )
    assert (
        client.get(
            f"/api/v1/organisations/{organisation_key}/prediction-requests/"
            f"{request_key}"
        ).status_code
        == 200
    )
    cancelled = client.post(
        f"/api/v1/organisations/{organisation_key}/prediction-requests/"
        f"{request_key}/cancel"
    )
    assert cancelled.status_code == 200 and cancelled.json()["state"] == "cancelled"
    with session_factory() as session:
        request = session.scalar(
            select(PredictionRequest).where(
                PredictionRequest.prediction_request_key == request_key
            )
        )
        assert request is not None
        assert request.submitted_by == 0 and request.cancelled_by == 1
def test_preflight_is_read_only_and_create_persists_target_scenario_history(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)

    preflight = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions/preflight",
        json=_prediction_payload(target_key),
    )
    assert preflight.status_code == 200
    assert preflight.json()["metrics"] == [
        {
            "scenarioId": target_key,
            "metricId": "revenue",
            "status": "eligible",
            "reason": None,
            "seasonalPeriod": 2,
            "seasonalPeriodSource": "manual",
            "requiresManualSeasonalPeriod": False,
        }
    ]
    with session_factory() as session:
        assert session.scalar(select(PredictionVersion)) is None

    created = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="May forecast"),
    )
    assert created.status_code == 201
    detail = created.json()
    assert detail["name"] == "May forecast"
    assert detail["confidenceLevel"] == 80
    assert detail["modelConfiguration"]["predictionIntervals"] == {
        "confidenceLevel": 80,
        "mlforecast": {"method": "conformal_error", "nWindows": 3, "h": 1},
        "sarima": {"method": "native_forecast_result", "alpha": 0.2},
    }
    results = {result["kind"]: result for result in detail["targets"][0]["results"]}
    assert [point["value"] for point in results["naive"]["points"]] == [40.0, 40.0]
    assert [point["value"] for point in results["average"]["points"]] == [25.0, 25.0]
    assert [point["value"] for point in results["seasonal_naive"]["points"]] == [
        30.0,
        40.0,
    ]
    assert results["mlforecast"]["status"] == "ineligible"
    assert results["sarima"]["status"] == "ineligible"
    assert all(
        result["predictionIntervalStatus"] == "not_applicable"
        and all(
            point["lowerBound"] is None and point["upperBound"] is None
            for point in result["points"]
        )
        for kind, result in results.items()
        if kind in {"naive", "seasonal_naive", "average"}
    )

    listed = client.get(f"/api/v1/organisations/{organisation_key}/predictions")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == detail["id"]
    assert listed.json()[0]["confidenceLevel"] == 80

    with session_factory() as session:
        target = session.scalar(select(PredictionTarget))
        assert target is not None
        assert target.created_by == 0
        assert target.source_snapshot["observationPolicy"] == "targetScenarioOnly"
        result = session.scalar(select(PredictionModelResult))
        point = session.scalar(select(PredictionPoint))
        assert result is not None and result.created_by == 0
        assert point is not None and point.created_by == 0


def test_create_prediction_persists_derived_target_without_seasonal_source(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    timeseries_path = (
        f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/timeseries"
    )
    short_name = client.patch(
        f"{timeseries_path}/revenue/short-name",
        json={"shortName": "revenue"},
    )
    assert short_name.status_code == 200
    derived = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/derived-metrics",
        json={"name": "Double revenue", "unit": "EUR", "formula": "revenue * 2"},
    )
    assert derived.status_code == 201

    created = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="Derived forecast"),
    )

    assert created.status_code == 201
    targets = {item["metricId"]: item for item in created.json()["targets"]}
    assert targets[derived.json()["id"]]["seasonalPeriod"] is None
    assert targets[derived.json()["id"]]["seasonalPeriodSource"] is None
    assert all(
        result["predictionIntervalStatus"] == "not_applicable"
        and all(
            point["lowerBound"] is None and point["upperBound"] is None
            for point in result["points"]
        )
        for result in targets[derived.json()["id"]]["results"]
    )


def test_snapshot_round_trip_detaches_normal_and_derived_calculation_from_sources(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    from app.api.v1.predictions import service as predictions_service

    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    timeseries_path = (
        f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/timeseries"
    )
    assert (
        client.patch(
            f"{timeseries_path}/revenue/short-name",
            json={"shortName": "revenue"},
        ).status_code
        == 200
    )
    derived = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/"
        f"{target_key}/derived-metrics",
        json={"name": "Double revenue", "unit": "EUR", "formula": "revenue * 2"},
    )
    assert derived.status_code == 201
    payload = PredictionCreateRequest.model_validate(
        _prediction_payload(target_key, name="Detached forecast")
    )

    with session_factory() as preparation_session:
        snapshot = predictions_service.prepare_prediction_snapshot(
            preparation_session, organisation_key, payload, actor_user_id=0
        )
    restored = PredictionInputSnapshot.model_validate_json(
        snapshot.model_dump_json(by_alias=True)
    )
    assert restored == snapshot

    with session_factory() as mutation_session:
        source = mutation_session.scalar(
            select(Timeserie).where(Timeserie.timeserie_key == "revenue")
        )
        equation = mutation_session.scalar(select(DerivedMetricEquation))
        assert source is not None and equation is not None
        latest_value = mutation_session.scalar(
            select(TimeserieValue)
            .where(TimeserieValue.timeserie_id == source.timeserie_id)
            .order_by(TimeserieValue.date.desc())
        )
        assert latest_value is not None
        source.short_name = "changed_name"
        source.deleted_time = datetime.now(UTC)
        latest_value.value = {"value": 9999}
        equation.formula = "changed_name * 999"
        mutation_session.commit()

    calculation = predictions_service.calculate_prediction(restored)
    restored_calculation = PredictionCalculation.model_validate_json(
        calculation.model_dump_json(by_alias=True)
    )
    assert restored_calculation == calculation
    with session_factory() as publication_session:
        detail = predictions_service.publish_prediction(
            publication_session, restored, restored_calculation
        )

    targets = {item.metric_id: item for item in detail.targets}
    normal_results = {item.kind: item for item in targets["revenue"].results}
    derived_results = {
        item.kind: item for item in targets[str(derived.json()["id"])].results
    }
    assert [point.value for point in normal_results["naive"].points] == [40.0, 40.0]
    assert [point.value for point in derived_results["naive"].points] == [80.0, 80.0]
    normal_source = cast(dict[str, Any], targets["revenue"].source_snapshot)
    assert normal_source["effectiveObservations"][-1] == {
        "date": "2025-04-01",
        "value": 40.0,
        "source": "targetScenario",
    }
    derived_source = cast(
        dict[str, Any], targets[str(derived.json()["id"])].source_snapshot
    )
    assert derived_source["derivedFormula"] == "revenue * 2"
    assert derived_source["referencedMetrics"] == [
        {"id": "revenue", "shortName": "revenue"}
    ]


def test_publication_failure_rolls_back_the_complete_prediction_version(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.v1.predictions import service as predictions_service

    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    payload = PredictionCreateRequest.model_validate(
        _prediction_payload(target_key, name="Rollback forecast")
    )
    with session_factory() as preparation_session:
        snapshot = predictions_service.prepare_prediction_snapshot(
            preparation_session, organisation_key, payload, actor_user_id=0
        )
    calculation = predictions_service.calculate_prediction(snapshot)
    original_save = predictions_service._save_result  # pyright: ignore[reportPrivateUsage]
    calls = 0

    def fail_during_publication(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected publication failure")
        original_save(*args, **kwargs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(predictions_service, "_save_result", fail_during_publication)
    with session_factory() as publication_session:
        with pytest.raises(RuntimeError, match="injected publication failure"):
            predictions_service.publish_prediction(
                publication_session, snapshot, calculation
            )

    with session_factory() as verification_session:
        assert verification_session.scalar(select(PredictionVersion)) is None
        assert verification_session.scalar(select(PredictionTarget)) is None
        assert verification_session.scalar(select(PredictionModelResult)) is None
        assert verification_session.scalar(select(PredictionPoint)) is None


def test_unexpected_detached_calculation_failure_leaves_no_partial_version(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.v1.predictions import service as predictions_service

    organisation_key, target_key = _create_model_ready_target(client)
    payload = PredictionCreateRequest.model_validate(
        _prediction_payload(
            target_key,
            name="Calculation failure",
            startDate="2025-01-01",
            endDate="2025-02-28",
        )
    )
    with session_factory() as preparation_session:
        snapshot = predictions_service.prepare_prediction_snapshot(
            preparation_session, organisation_key, payload, actor_user_id=0
        )

    def fail_calculation(row: object, confidence_level: int) -> object:
        del row, confidence_level
        raise RuntimeError("injected calculation failure")

    monkeypatch.setattr(predictions_service, "_mlforecast_result", fail_calculation)
    with pytest.raises(RuntimeError, match="injected calculation failure"):
        predictions_service.calculate_prediction(snapshot)

    with session_factory() as verification_session:
        assert verification_session.scalar(select(PredictionVersion)) is None
        assert verification_session.scalar(select(PredictionTarget)) is None


def test_prediction_rejects_duplicate_name_and_cross_organisation_target(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    payload = _prediction_payload(target_key, name="Forecast")
    assert (
        _create_completed_prediction(
            client,
            f"/api/v1/organisations/{organisation_key}/predictions", json=payload
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/v1/organisations/{organisation_key}/predictions",
            json=_prediction_payload(target_key, name="forecast"),
        ).status_code
        == 409
    )

    other_organisation = _create_organisation(client, "Other Forecast Org")
    cross_organisation = client.post(
        f"/api/v1/organisations/{other_organisation}/predictions/preflight",
        json=_prediction_payload(target_key),
    )
    assert cross_organisation.status_code == 404


@pytest.mark.parametrize("confidence_level", [50, 99])
def test_prediction_accepts_confidence_level_boundaries(
    client: TestClient, confidence_level: int
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)

    preflight = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions/preflight",
        json=_prediction_payload(target_key, confidenceLevel=confidence_level),
    )
    assert preflight.status_code == 200
    created = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(
            target_key,
            name=f"Level {confidence_level}",
            confidenceLevel=confidence_level,
        ),
    )
    assert created.status_code == 201
    assert created.json()["confidenceLevel"] == confidence_level


@pytest.mark.parametrize("confidence_level", [49, 100, 80.0, "80"])
def test_prediction_rejects_invalid_confidence_levels(
    client: TestClient, confidence_level: object
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)

    response = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions/preflight",
        json=_prediction_payload(target_key, confidenceLevel=confidence_level),
    )
    assert response.status_code == 422


def test_mlforecast_selected_levels_produce_distinct_complete_bounds(
    client: TestClient,
) -> None:
    organisation_key, target_key = _create_model_ready_target(client)

    versions: list[dict[str, Any]] = []
    with warnings.catch_warnings(record=True) as caught_warnings:
        warnings.simplefilter("always")
        for confidence_level in (50, 99):
            response = _create_completed_prediction(
                client,
                f"/api/v1/organisations/{organisation_key}/predictions",
                json=_prediction_payload(
                    target_key,
                    name=f"MLForecast level {confidence_level}",
                    confidenceLevel=confidence_level,
                    startDate="2025-01-01",
                    endDate="2025-02-28",
                ),
            )
            assert response.status_code == 201
            versions.append(cast(dict[str, Any], response.json()))

    assert not any(
        "Prediction intervals are calculated using 1-step ahead cross-validation"
        in str(warning.message)
        for warning in caught_warnings
    )

    bounds_by_level: list[list[tuple[float | None, float | None]]] = []
    for version in versions:
        targets = cast(list[dict[str, Any]], version["targets"])
        results = {
            item["kind"]: item
            for item in cast(list[dict[str, Any]], targets[0]["results"])
        }
        result = results["mlforecast"]
        assert result["predictionIntervalStatus"] == "available"
        points = cast(list[dict[str, float | None]], result["points"])
        bounds_by_level.append(
            [(point["lowerBound"], point["upperBound"]) for point in points]
        )
    assert bounds_by_level[0] != bounds_by_level[1]


def test_preflight_rejects_candidate_pair_limit_before_history_preparation(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    with session_factory() as session:
        scenario = session.scalar(
            select(Scenario).where(Scenario.scenario_key == target_key)
        )
        assert scenario is not None
        session.add_all(
            Timeserie(
                scenario_id=scenario.scenario_id,
                timeserie_key=f"metric-{index}",
                name=f"Metric {index}",
                unit="EUR",
                time_unit="month",
                value_unit="number",
            )
            for index in range(50)
        )
        session.commit()

    response = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions/preflight",
        json=_prediction_payload(target_key),
    )
    assert response.status_code == 422
    assert "50 forecast candidate pair limit" in response.json()["detail"]


def test_as_of_start_excludes_observations_at_or_after_first_period(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    replacement = client.patch(
        (
            f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/"
            "timeseries/revenue/values"
        ),
        json={
            "values": [
                {"date": "2025-01-01", "value": 10},
                {"date": "2025-02-01", "value": 20},
                {"date": "2025-03-01", "value": 30},
                {"date": "2025-04-01", "value": 400},
            ]
        },
    )
    assert replacement.status_code == 200
    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(
            target_key,
            name="Cutoff",
            startDate="2025-03-01",
            endDate="2025-04-30",
        ),
    )
    assert response.status_code == 201
    results = {item["kind"]: item for item in response.json()["targets"][0]["results"]}
    assert [point["value"] for point in results["naive"]["points"]] == [20.0, 20.0]


def test_as_of_start_uses_first_generated_period_for_unaligned_ranges(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    replacement = client.patch(
        (
            f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/"
            "timeseries/revenue/values"
        ),
        json={
            "values": [
                {"date": "2025-01-01", "value": 10},
                {"date": "2025-02-01", "value": 20},
                {"date": "2025-03-01", "value": 30},
                {"date": "2025-04-01", "value": 40},
                {"date": "2025-05-01", "value": 500},
            ]
        },
    )
    assert replacement.status_code == 200

    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(
            target_key,
            name="Unaligned cutoff",
            startDate="2025-05-15",
            endDate="2025-06-30",
        ),
    )
    assert response.status_code == 201
    results = {item["kind"]: item for item in response.json()["targets"][0]["results"]}
    assert [point["date"] for point in results["naive"]["points"]] == ["2025-06-01"]
    assert [point["value"] for point in results["naive"]["points"]] == [500.0]


def test_target_scenario_values_are_the_only_observed_history(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    replacement = client.patch(
        (
            f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/"
            "timeseries/revenue/values"
        ),
        json={
            "values": [
                {"date": "2025-01-01", "value": 100},
                {"date": "2025-02-01", "value": 200},
                {"date": "2025-03-01", "value": 300},
                {"date": "2025-04-01", "value": 400},
            ]
        },
    )
    assert replacement.status_code == 200

    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="Possible past"),
    )
    assert response.status_code == 201
    target = response.json()["targets"][0]
    results = {result["kind"]: result for result in target["results"]}
    assert [point["value"] for point in results["naive"]["points"]] == [400.0, 400.0]
    assert [point["value"] for point in results["average"]["points"]] == [250.0, 250.0]
    assert target["sourceSnapshot"]["effectiveObservations"][-1] == {
        "date": "2025-04-01",
        "value": 400.0,
        "source": "targetScenario",
    }
    assert target["sourceSnapshot"]["observationPolicy"] == "targetScenarioOnly"
    assert "realityScenarioId" not in target


def test_reality_is_a_prediction_target_with_its_own_history(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries",
        json={
            "id": "revenue",
            "name": "Revenue",
            "unit": "EUR",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    )
    assert response.status_code == 201
    response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries/revenue/values",
        json={
            "values": [
                {"date": "2025-01-01", "value": 10},
                {"date": "2025-02-01", "value": 20},
                {"date": "2025-03-01", "value": 30},
                {"date": "2025-04-01", "value": 40},
            ]
        },
    )
    assert response.status_code == 200

    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload("reality", name="Reality forecast"),
    )

    assert response.status_code == 201
    target = response.json()["targets"][0]
    assert target["scenarioId"] == "reality"
    assert [
        observation["source"]
        for observation in target["sourceSnapshot"]["effectiveObservations"]
    ] == ["targetScenario"] * 4


def test_all_current_scenario_uses_only_target_data_and_rejects_legacy_cutoff(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    other = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios",
        json={"name": "Other plan"},
    )
    assert other.status_code == 201
    other_key = other.json()["id"]
    response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/{other_key}/timeseries",
        json={
            "id": "revenue",
            "name": "Revenue",
            "unit": "EUR",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    )
    assert response.status_code == 201
    response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/{other_key}/timeseries/revenue/values",
        json={
            "values": [
                {"date": "2025-01-01", "value": 1000},
                {"date": "2025-02-01", "value": 2000},
                {"date": "2025-03-01", "value": 3000},
                {"date": "2025-04-01", "value": 4000},
            ]
        },
    )
    assert response.status_code == 200

    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(
            target_key,
            name="All current target",
            startDate="2025-03-01",
            endDate="2025-04-30",
            cutoffMode="allCurrentScenario",
        ),
    )
    assert response.status_code == 201
    results = {item["kind"]: item for item in response.json()["targets"][0]["results"]}
    assert [point["value"] for point in results["naive"]["points"]] == [40.0, 40.0]
    assert [point["value"] for point in results["average"]["points"]] == [25.0, 25.0]

    legacy = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions/preflight",
        json=_prediction_payload(target_key, cutoffMode="allCurrentReality"),
    )
    assert legacy.status_code == 422


def test_forked_timeserie_history_is_independently_forecastable(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    response = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries",
        json={
            "id": "revenue",
            "name": "Revenue",
            "unit": "EUR",
            "timeUnit": "month",
            "valueUnit": "number",
        },
    )
    assert response.status_code == 201
    response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries/revenue/values",
        json={
            "values": [
                {"date": "2025-01-01", "value": 10},
                {"date": "2025-02-01", "value": 20},
                {"date": "2025-03-01", "value": 30},
                {"date": "2025-04-01", "value": 40},
            ]
        },
    )
    assert response.status_code == 200
    state = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/org-states",
        json={"name": "Forecast source", "targetDate": "2025-04-01"},
    )
    assert state.status_code == 201
    fork = client.post(
        f"/api/v1/organisations/{organisation_key}/scenarios/copy",
        json={
            "sourceScenarioId": "reality",
            "sourceOrgStateId": state.json()["id"],
            "name": "Forecast fork",
        },
    )
    assert fork.status_code == 201
    fork_key = fork.json()["id"]

    prediction = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(fork_key, name="Fork forecast"),
    )
    assert prediction.status_code == 201
    assert prediction.json()["targets"][0]["status"] == "eligible"

    response = client.patch(
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries/revenue/values",
        json={"values": [{"date": "2025-01-01", "value": 999}]},
    )
    assert response.status_code == 200
    rerun = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(fork_key, name="Fork forecast after source edit"),
    )
    assert rerun.status_code == 201
    results = {item["kind"]: item for item in rerun.json()["targets"][0]["results"]}
    assert [point["value"] for point in results["naive"]["points"]] == [40.0, 40.0]


def test_sarima_nonconvergence_is_saved_without_discarding_mlforecast(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    values = [
        {
            "date": f"2024-{month:02d}-01",
            "value": float(100 + month * 3),
        }
        for month in range(1, 13)
    ]
    replacement = client.patch(
        (
            f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/"
            "timeseries/revenue/values"
        ),
        json={"values": values},
    )
    assert replacement.status_code == 200
    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(
            target_key,
            name="Model run",
            startDate="2025-01-01",
            endDate="2025-02-28",
        ),
    )
    assert response.status_code == 201
    results = {item["kind"]: item for item in response.json()["targets"][0]["results"]}
    assert results["mlforecast"]["status"] == "available", results["mlforecast"]
    assert len(results["mlforecast"]["points"]) == 2
    assert results["mlforecast"]["crossValidationStatus"] == "available"
    assert results["mlforecast"]["crossValidationMae"] is not None
    assert results["mlforecast"]["predictionIntervalStatus"] == "available"
    assert all(
        point["lowerBound"] <= point["value"] <= point["upperBound"]
        for point in results["mlforecast"]["points"]
    )
    assert results["sarima"] == {
        "kind": "sarima",
        "status": "ineligible",
        "reason": "SARIMA fitting did not converge.",
        "predictionIntervalStatus": "unavailable",
        "predictionIntervalReason": "SARIMA fitting did not converge.",
        "crossValidationStatus": "not_applicable",
        "crossValidationMae": None,
        "configuration": results["sarima"]["configuration"],
        "points": [],
    }


def test_non_finite_mlforecast_values_are_saved_as_ineligible(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1.predictions import service as predictions_service

    organisation_key, target_key = _create_model_ready_target(client)

    def non_finite_mlforecast(row: object, confidence_level: int) -> object:
        del row, confidence_level
        return predictions_service._GeneratedResult(  # pyright: ignore[reportPrivateUsage]
            [float("nan"), float("nan")],
            "available",
            None,
            "available",
            1.0,
            "available",
            None,
            [(0.0, 1.0), (0.0, 1.0)],
        )

    monkeypatch.setattr(
        predictions_service,
        "_mlforecast_result",
        non_finite_mlforecast,
    )  # pyright: ignore[reportPrivateUsage]
    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(
            target_key,
            name="Non-finite MLForecast values",
            startDate="2025-01-01",
            endDate="2025-02-28",
        ),
    )
    assert response.status_code == 201
    results = {item["kind"]: item for item in response.json()["targets"][0]["results"]}
    assert results["mlforecast"] == {
        "kind": "mlforecast",
        "status": "ineligible",
        "reason": "MLForecast generated non-finite forecast values.",
        "predictionIntervalStatus": "unavailable",
        "predictionIntervalReason": "MLForecast generated non-finite forecast values.",
        "crossValidationStatus": "unavailable",
        "crossValidationMae": None,
        "configuration": results["mlforecast"]["configuration"],
        "points": [],
    }


def test_non_finite_mlforecast_mae_is_saved_as_ineligible(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1.predictions import service as predictions_service

    organisation_key, target_key = _create_model_ready_target(client)

    def non_finite_mlforecast(row: object, confidence_level: int) -> object:
        del row, confidence_level
        return predictions_service._GeneratedResult(  # pyright: ignore[reportPrivateUsage]
            [1.0, 1.0],
            "available",
            None,
            "available",
            float("nan"),
            "available",
            None,
            [(0.0, 2.0), (0.0, 2.0)],
        )

    monkeypatch.setattr(
        predictions_service,
        "_mlforecast_result",
        non_finite_mlforecast,
    )  # pyright: ignore[reportPrivateUsage]
    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(
            target_key,
            name="Non-finite MLForecast MAE",
            startDate="2025-01-01",
            endDate="2025-02-28",
        ),
    )
    assert response.status_code == 201
    results = {item["kind"]: item for item in response.json()["targets"][0]["results"]}
    assert results["mlforecast"] == {
        "kind": "mlforecast",
        "status": "ineligible",
        "reason": "MLForecast generated a non-finite cross-validation MAE.",
        "predictionIntervalStatus": "unavailable",
        "predictionIntervalReason": (
            "MLForecast generated a non-finite cross-validation MAE."
        ),
        "crossValidationStatus": "unavailable",
        "crossValidationMae": None,
        "configuration": results["mlforecast"]["configuration"],
        "points": [],
    }


def test_non_finite_sarima_values_are_saved_as_ineligible(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1.predictions import service as predictions_service

    organisation_key, target_key = _create_model_ready_target(client)

    def non_finite_sarima(row: object, confidence_level: int) -> object:
        del row, confidence_level
        return predictions_service._GeneratedResult(  # pyright: ignore[reportPrivateUsage]
            [float("nan"), float("nan")],
            "available",
            None,
            "not_applicable",
            None,
            "available",
            None,
            [(0.0, 1.0), (0.0, 1.0)],
        )

    monkeypatch.setattr(
        predictions_service,
        "_sarima_result",
        non_finite_sarima,
    )  # pyright: ignore[reportPrivateUsage]
    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(
            target_key,
            name="Non-finite SARIMA values",
            startDate="2025-01-01",
            endDate="2025-02-28",
        ),
    )
    assert response.status_code == 201
    results = {item["kind"]: item for item in response.json()["targets"][0]["results"]}
    assert results["sarima"] == {
        "kind": "sarima",
        "status": "ineligible",
        "reason": "SARIMA generated non-finite forecast values.",
        "predictionIntervalStatus": "unavailable",
        "predictionIntervalReason": "SARIMA generated non-finite forecast values.",
        "crossValidationStatus": "unavailable",
        "crossValidationMae": None,
        "configuration": results["sarima"]["configuration"],
        "points": [],
    }


def test_sarima_uses_native_prediction_bounds_and_selected_seasonal_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.v1.predictions import service as predictions_service

    captured: dict[str, object] = {}

    class FakeForecastResult:
        predicted_mean = [1.0]

        def conf_int(self, *, alpha: float) -> list[tuple[float, float]]:
            captured["alpha"] = alpha
            return [(0.5, 1.5)]

    class FakeFittedModel:
        mle_retvals = {"converged": True}

        def forecast(self, periods: int, exog: object) -> list[float]:
            del exog
            return [1.0] * periods

        def get_forecast(self, periods: int, exog: object) -> FakeForecastResult:
            del periods, exog
            return FakeForecastResult()

    class FakeSarimax:
        def __init__(
            self,
            *args: object,
            seasonal_order: tuple[int, int, int, int],
            **kwargs: object,
        ) -> None:
            del args, kwargs
            captured["seasonal_order"] = seasonal_order

        def fit(self, **kwargs: object) -> FakeFittedModel:
            del kwargs
            return FakeFittedModel()

    monkeypatch.setattr("statsmodels.tsa.statespace.sarimax.SARIMAX", FakeSarimax)
    history_dates = [date(2024, month, 1) for month in range(1, 9)]
    prepared_target = predictions_service._PreparedTarget  # pyright: ignore[reportPrivateUsage]
    sarima_result = predictions_service._sarima_result  # pyright: ignore[reportPrivateUsage]
    row = prepared_target(
        scenarioInternalId=1,
        scenarioKey="scenario",
        scenarioName="Scenario",
        metricKey="metric",
        metricName="Metric",
        timeUnit="month",
        unit=None,
        status="eligible",
        reason=None,
        seasonalPeriod=2,
        seasonalPeriodSource="manual",
        observations=[
            SnapshotObservation(date=day, value=float(index))
            for index, day in enumerate(history_dates, start=1)
        ],
        historyPeriods=[
            SnapshotFeaturePeriod(date=day, features={}) for day in history_dates
        ],
        predictionPeriods=[SnapshotFeaturePeriod(date=date(2025, 1, 1), features={})],
    )

    result = sarima_result(row, 80)
    assert result.values == [1.0]
    assert result.prediction_interval_status == "available"
    assert result.bounds == [(0.5, 1.5)]
    assert captured["seasonal_order"] == (1, 0, 0, 2)
    assert captured["alpha"] == pytest.approx(0.2)


def test_interval_failure_preserves_valid_model_points(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.v1.predictions import service as predictions_service

    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)

    def interval_unavailable(row: object, confidence_level: int) -> object:
        del row, confidence_level
        return predictions_service._GeneratedResult(  # pyright: ignore[reportPrivateUsage]
            [10.0, 11.0],
            "available",
            None,
            "available",
            1.0,
            "unavailable",
            "MLForecast prediction interval is unavailable.",
        )

    monkeypatch.setattr(predictions_service, "_mlforecast_result", interval_unavailable)  # pyright: ignore[reportPrivateUsage]
    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(
            target_key,
            name="Interval unavailable",
        ),
    )

    assert response.status_code == 201
    result = {item["kind"]: item for item in response.json()["targets"][0]["results"]}[
        "mlforecast"
    ]
    assert result["status"] == "available"
    assert result["predictionIntervalStatus"] == "unavailable"
    assert result["predictionIntervalReason"] == (
        "MLForecast prediction interval is unavailable."
    )
    assert [point["value"] for point in result["points"]] == [10.0, 11.0]
    assert all(
        point["lowerBound"] is None and point["upperBound"] is None
        for point in result["points"]
    )


def test_missing_target_scenario_period_is_saved_as_normal_ineligibility(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    with session_factory() as session:
        target_scenario = session.scalar(
            select(Scenario).where(Scenario.scenario_key == target_key)
        )
        assert target_scenario is not None
        timeserie = session.scalar(
            select(Timeserie).where(
                Timeserie.scenario_id == target_scenario.scenario_id
            )
        )
        assert timeserie is not None
        missing = session.scalar(
            select(TimeserieValue).where(
                TimeserieValue.timeserie_id == timeserie.timeserie_id,
                TimeserieValue.date == date(2025, 2, 1),
            )
        )
        assert missing is not None
        missing.deleted_time = missing.created_time
        session.commit()
    response = _create_completed_prediction(
        client,
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="Gap"),
    )
    assert response.status_code == 201
    target = response.json()["targets"][0]
    assert target["status"] == "ineligible"
    assert "not contiguous" in target["reason"]
    assert all(result["status"] == "ineligible" for result in target["results"])
