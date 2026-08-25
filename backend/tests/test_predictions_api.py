from collections.abc import Iterator
from datetime import date

import pytest
from auth_helpers import authenticate_test_client
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.org_states.models import Scenario, Timeserie, TimeserieValue
from app.api.v1.org_twin_structure.models import Metamodel
from app.api.v1.predictions.models import (
    PredictionModelResult,
    PredictionPoint,
    PredictionTarget,
    PredictionVersion,
)
from app.core.database import get_db_session
from app.core.models import Base
from app.main import create_app


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
        authenticate_test_client(test_client, session_factory)
        yield test_client
    app.dependency_overrides.clear()


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
    for scenario_key in ("reality", target_key):
        response = client.post(
            f"/api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries",
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
        f"/api/v1/organisations/{organisation_key}/scenarios/reality/timeseries/revenue/values",
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
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
            "timeseries/revenue/values"
        ),
        json={"values": values},
    )
    assert replacement.status_code == 200
    return organisation_key, target_key


def test_preflight_is_read_only_and_create_persists_reality_baselines(
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

    created = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="May forecast"),
    )
    assert created.status_code == 201
    detail = created.json()
    assert detail["name"] == "May forecast"
    results = {result["kind"]: result for result in detail["targets"][0]["results"]}
    assert [point["value"] for point in results["naive"]["points"]] == [40.0, 40.0]
    assert [point["value"] for point in results["average"]["points"]] == [25.0, 25.0]
    assert [point["value"] for point in results["seasonal_naive"]["points"]] == [
        30.0,
        40.0,
    ]
    assert results["mlforecast"]["status"] == "ineligible"
    assert results["sarima"]["status"] == "ineligible"

    listed = client.get(f"/api/v1/organisations/{organisation_key}/predictions")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == detail["id"]

    with session_factory() as session:
        target = session.scalar(select(PredictionTarget))
        assert target is not None
        assert target.created_by == 0
        assert (
            target.source_snapshot["observationPolicy"]
            == "targetScenarioOverridesReality"
        )
        result = session.scalar(select(PredictionModelResult))
        point = session.scalar(select(PredictionPoint))
        assert result is not None and result.created_by == 0
        assert point is not None and point.created_by == 0


def test_prediction_rejects_duplicate_name_and_cross_organisation_target(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    payload = _prediction_payload(target_key, name="Forecast")
    assert (
        client.post(
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


def test_preflight_rejects_candidate_pair_limit_before_history_preparation(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    with session_factory() as session:
        scenarios = {
            scenario.scenario_key: scenario
            for scenario in session.scalars(
                select(Scenario).where(
                    Scenario.scenario_key.in_(("reality", target_key))
                )
            )
        }
        session.add_all(
            Timeserie(
                scenario_id=scenarios[scenario_key].scenario_id,
                timeserie_key=f"metric-{index}",
                name=f"Metric {index}",
                unit="EUR",
                time_unit="month",
                value_unit="number",
            )
            for scenario_key in ("reality", target_key)
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
        json={"values": [{"date": "2025-04-01", "value": 400}]},
    )
    assert replacement.status_code == 200
    response = client.post(
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
        json={"values": [{"date": "2025-05-01", "value": 500}]},
    )
    assert replacement.status_code == 200

    response = client.post(
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


def test_target_scenario_values_override_reality_observations(
    client: TestClient,
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    replacement = client.patch(
        (
            f"/api/v1/organisations/{organisation_key}/scenarios/{target_key}/"
            "timeseries/revenue/values"
        ),
        json={"values": [{"date": "2025-04-01", "value": 400}]},
    )
    assert replacement.status_code == 200

    response = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="Possible past"),
    )
    assert response.status_code == 201
    target = response.json()["targets"][0]
    results = {result["kind"]: result for result in target["results"]}
    assert [point["value"] for point in results["naive"]["points"]] == [400.0, 400.0]
    assert [point["value"] for point in results["average"]["points"]] == [115.0, 115.0]
    assert target["sourceSnapshot"]["effectiveObservations"][-1] == {
        "date": "2025-04-01",
        "value": 400.0,
        "source": "targetScenario",
    }


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
            f"/api/v1/organisations/{organisation_key}/scenarios/reality/"
            "timeseries/revenue/values"
        ),
        json={"values": values},
    )
    assert replacement.status_code == 200
    response = client.post(
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
    assert results["sarima"] == {
        "kind": "sarima",
        "status": "ineligible",
        "reason": "SARIMA fitting did not converge.",
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

    def non_finite_mlforecast(
        row: object,
    ) -> tuple[list[float], str, str | None, str, float | None]:
        del row
        return [float("nan"), float("nan")], "available", None, "available", 1.0

    monkeypatch.setattr(
        predictions_service,
        "_mlforecast_points",
        non_finite_mlforecast,
    )  # pyright: ignore[reportPrivateUsage]
    response = client.post(
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

    def non_finite_mlforecast(
        row: object,
    ) -> tuple[list[float], str, str | None, str, float | None]:
        del row
        return [1.0, 1.0], "available", None, "available", float("nan")

    monkeypatch.setattr(
        predictions_service,
        "_mlforecast_points",
        non_finite_mlforecast,
    )  # pyright: ignore[reportPrivateUsage]
    response = client.post(
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

    def non_finite_sarima(
        row: object,
    ) -> tuple[list[float], str, str | None]:
        del row
        return [float("nan"), float("nan")], "available", None

    monkeypatch.setattr(
        predictions_service,
        "_sarima_points",
        non_finite_sarima,
    )  # pyright: ignore[reportPrivateUsage]
    response = client.post(
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
        "crossValidationStatus": "unavailable",
        "crossValidationMae": None,
        "configuration": results["sarima"]["configuration"],
        "points": [],
    }


def test_sarima_uses_the_selected_seasonal_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.v1.predictions import service as predictions_service

    captured: dict[str, tuple[int, int, int, int]] = {}

    class FakeFittedModel:
        mle_retvals = {"converged": True}

        def forecast(self, periods: int, exog: object) -> list[float]:
            del exog
            return [1.0] * periods

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
    history = [(date(2024, month, 1), float(month), "reality") for month in range(1, 9)]
    prepared_target = predictions_service._PreparedTarget  # pyright: ignore[reportPrivateUsage]
    sarima_points = predictions_service._sarima_points  # pyright: ignore[reportPrivateUsage]
    row = prepared_target(
        Scenario(),
        Timeserie(time_unit="month"),
        "eligible",
        None,
        2,
        "manual",
        history,
        [{} for _ in history],
        [date(2025, 1, 1)],
        [{}],
    )

    assert sarima_points(row) == ([1.0], "available", None)
    assert captured["seasonal_order"] == (1, 0, 0, 2)


def test_missing_reality_period_is_saved_as_normal_ineligibility(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    organisation_key = _create_organisation(client)
    target_key = _create_target_and_metrics(client, organisation_key)
    with session_factory() as session:
        reality = session.scalar(
            select(Scenario).where(Scenario.scenario_key == "reality")
        )
        assert reality is not None
        timeserie = session.scalar(
            select(Timeserie).where(Timeserie.scenario_id == reality.scenario_id)
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
    response = client.post(
        f"/api/v1/organisations/{organisation_key}/predictions",
        json=_prediction_payload(target_key, name="Gap"),
    )
    assert response.status_code == 201
    target = response.json()["targets"][0]
    assert target["status"] == "ineligible"
    assert "not contiguous" in target["reason"]
    assert all(result["status"] == "ineligible" for result in target["results"])
