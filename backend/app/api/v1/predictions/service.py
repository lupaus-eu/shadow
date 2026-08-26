"""Forecasting Domain service.

All source reads live here so each prediction target uses only its own observed
values and known inputs.
"""
# pyright: reportAttributeAccessIssue=false, reportMissingTypeStubs=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import math
import warnings
from collections import Counter
from datetime import date as dt_date
from statistics import mean
from typing import cast
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.org_states.models import Event, Scenario, Timeserie, TimeserieValue
from app.api.v1.org_twin_structure.models import (
    EdgeType,
    GraphEdge,
    GraphNode,
    NodeType,
)
from app.api.v1.organisations.models import Organisation
from app.api.v1.organisations.service import get_active_organisation
from app.api.v1.predictions.models import (
    PredictionModelResult,
    PredictionPoint,
    PredictionTarget,
    PredictionVersion,
)
from app.api.v1.predictions.schemas import (
    CutoffMode,
    PredictionCreateRequest,
    PredictionMetricPreflightResponse,
    PredictionModelResultResponse,
    PredictionPointResponse,
    PredictionPreflightRequest,
    PredictionPreflightResponse,
    PredictionRequestBase,
    PredictionTargetResponse,
    PredictionVersionDetailResponse,
    PredictionVersionListResponse,
)

RESULT_KINDS = ("naive", "seasonal_naive", "average", "mlforecast", "sarima")
type Observation = tuple[dt_date, float, str]
MAX_PAIRS = 50
MAX_PERIODS = 366
MAX_HISTORY = 10_000
MAX_POINTS = 100_000
MODEL_CONFIGURATION: dict[str, object] = {
    "seed": 41,
    "mlforecast": {"lags": [1, 2, 3, 7], "randomForestEstimators": 50, "maxDepth": 8},
    "sarima": {
        "order": [1, 0, 0],
        "seasonalOrder": [1, 0, 0],
        "maxiter": 50,
    },
}


def preflight_predictions(
    session: Session, organisation_key: str, payload: PredictionPreflightRequest
) -> PredictionPreflightResponse:
    organisation, targets = _request_context(session, organisation_key, payload)
    del organisation
    rows = _prepare_targets(session, targets, payload)
    _enforce_limits(rows)
    return PredictionPreflightResponse(metrics=[row.preflight for row in rows])


def create_prediction(
    session: Session,
    organisation_key: str,
    payload: PredictionCreateRequest,
    actor_user_id: int,
) -> PredictionVersionDetailResponse:
    organisation, targets = _request_context(session, organisation_key, payload)
    rows = _prepare_targets(session, targets, payload)
    _enforce_limits(rows)
    if (
        session.scalar(
            select(PredictionVersion.prediction_version_id).where(
                PredictionVersion.organisation_id == organisation.organisation_id,
                func.lower(PredictionVersion.name) == payload.name.lower(),
            )
        )
        is not None
    ):
        raise _duplicate_name_exception()

    version = PredictionVersion(
        organisation_id=organisation.organisation_id,
        prediction_key=f"prediction_{uuid4().hex}",
        name=payload.name,
        cutoff_mode=payload.cutoff_mode,
        start_date=payload.start_date,
        end_date=payload.end_date,
        model_configuration=MODEL_CONFIGURATION,
        created_by=actor_user_id,
    )
    try:
        session.add(version)
        session.flush()
        for row in rows:
            target = PredictionTarget(
                prediction_version_id=version.prediction_version_id,
                target_scenario_id=row.scenario.scenario_id,
                target_scenario_key=row.scenario.scenario_key,
                metric_key=row.metric.timeserie_key,
                metric_name=row.metric.name,
                time_unit=row.metric.time_unit,
                unit=row.metric.unit,
                eligibility_status=row.status,
                eligibility_reason=row.reason,
                seasonal_period=row.seasonal_period,
                seasonal_period_source=row.seasonal_period_source,
                source_snapshot=row.source_snapshot,
                input_snapshot=row.input_snapshot,
                created_by=actor_user_id,
            )
            session.add(target)
            session.flush()
            _persist_result_set(session, target, row, actor_user_id)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if _is_duplicate_prediction_name_error(exc):
            raise _duplicate_name_exception() from exc
        raise
    except Exception:
        session.rollback()
        raise
    session.refresh(version)
    return _version_detail(session, version)


def list_predictions(
    session: Session, organisation_key: str
) -> list[PredictionVersionListResponse]:
    organisation = get_active_organisation(session, organisation_key)
    versions = session.scalars(
        select(PredictionVersion)
        .where(PredictionVersion.organisation_id == organisation.organisation_id)
        .order_by(
            PredictionVersion.created_time.desc(),
            PredictionVersion.prediction_version_id.desc(),
        )
    ).all()
    return [_version_list_item(version) for version in versions]


def get_prediction(
    session: Session, organisation_key: str, prediction_key: str
) -> PredictionVersionDetailResponse:
    organisation = get_active_organisation(session, organisation_key)
    version = session.scalar(
        select(PredictionVersion).where(
            PredictionVersion.organisation_id == organisation.organisation_id,
            PredictionVersion.prediction_key == prediction_key,
        )
    )
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found."
        )
    return _version_detail(session, version)


class _PreparedTarget:
    def __init__(
        self,
        scenario: Scenario,
        metric: Timeserie,
        status: str,
        reason: str | None,
        seasonal_period: int | None,
        seasonal_period_source: str | None,
        history: list[Observation],
        history_features: list[dict[str, float]],
        periods: list[dt_date],
        features: list[dict[str, float]],
    ) -> None:
        self.scenario = scenario
        self.metric = metric
        self.status = status
        self.reason = reason
        self.seasonal_period = seasonal_period
        self.seasonal_period_source = seasonal_period_source
        self.history = history
        self.history_features = history_features
        self.periods = periods
        self.features = features

    @property
    def source_snapshot(self) -> dict[str, object]:
        return {
            "targetScenarioId": self.scenario.scenario_key,
            "observationPolicy": "targetScenarioOnly",
            "metric": {
                "id": self.metric.timeserie_key,
                "timeUnit": self.metric.time_unit,
                "unit": self.metric.unit,
            },
            "effectiveObservations": [
                {"date": day.isoformat(), "value": value, "source": source}
                for day, value, source in self.history
            ],
        }

    @property
    def input_snapshot(self) -> dict[str, object]:
        return {
            "historyPeriods": [
                {"date": day.isoformat(), **features}
                for (day, _, _), features in zip(
                    self.history, self.history_features, strict=True
                )
            ],
            "periods": [
                {"date": day.isoformat(), **features}
                for day, features in zip(self.periods, self.features, strict=True)
            ],
        }

    @property
    def preflight(self) -> PredictionMetricPreflightResponse:
        return PredictionMetricPreflightResponse(
            scenarioId=self.scenario.scenario_key,
            metricId=self.metric.timeserie_key,
            status=self.status,
            reason=self.reason,
            seasonalPeriod=self.seasonal_period,
            seasonalPeriodSource=self.seasonal_period_source,
            requiresManualSeasonalPeriod=self.status
            == "requires_manual_seasonal_period",
        )


def _request_context(
    session: Session, organisation_key: str, payload: PredictionRequestBase
) -> tuple[Organisation, list[Scenario]]:
    organisation = get_active_organisation(session, organisation_key)
    targets = session.scalars(
        select(Scenario).where(
            Scenario.organisation_id == organisation.organisation_id,
            Scenario.scenario_key.in_(payload.target_scenario_ids),
            Scenario.deleted_time.is_(None),
        )
    ).all()
    by_key = {scenario.scenario_key: scenario for scenario in targets}
    if len(by_key) != len(payload.target_scenario_ids):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Target scenario not found."
        )
    return organisation, [by_key[key] for key in payload.target_scenario_ids]


def _prepare_targets(
    session: Session,
    targets: list[Scenario],
    payload: PredictionRequestBase,
) -> list[_PreparedTarget]:
    prepared: list[_PreparedTarget] = []
    candidate_count = 0
    for scenario in targets:
        metrics = session.scalars(
            select(Timeserie)
            .where(
                Timeserie.scenario_id == scenario.scenario_id,
                Timeserie.deleted_time.is_(None),
            )
            .order_by(Timeserie.timeserie_key)
        ).all()
        for metric in metrics:
            if _is_model_candidate(metric):
                candidate_count += 1
                if candidate_count > MAX_PAIRS:
                    raise _pair_limit_exception()
            row = _prepare_metric(session, scenario, metric, payload)
            prepared.append(row)
    return prepared


def _is_model_candidate(metric: Timeserie) -> bool:
    return metric.value_unit == "number"


def _prepare_metric(
    session: Session,
    scenario: Scenario,
    metric: Timeserie,
    payload: PredictionRequestBase,
) -> _PreparedTarget:
    def empty(current_status: str, current_reason: str) -> _PreparedTarget:
        return _PreparedTarget(
            scenario,
            metric,
            current_status,
            current_reason,
            None,
            None,
            [],
            [],
            [],
            [],
        )

    if metric.value_unit != "number":
        return empty("ineligible", "Only numeric metrics can be forecast.")
    periods = _periods_in_range(payload.start_date, payload.end_date, metric.time_unit)
    if not periods:
        return empty(
            "ineligible", "The selected date range contains no valid metric periods."
        )
    if len(periods) > MAX_PERIODS:
        return empty(
            "ineligible", f"Prediction range exceeds the {MAX_PERIODS} period limit."
        )
    history = _target_history(session, metric, payload, periods[0])
    if not history:
        return empty(
            "ineligible",
            "Target scenario has no observations available under the selected "
            "cutoff.",
        )
    if len(history) > MAX_HISTORY:
        return empty(
            "ineligible",
            "Effective observation history exceeds the "
            f"{MAX_HISTORY} observation limit.",
        )
    if not _is_contiguous([item[0] for item in history], metric.time_unit):
        return empty(
            "ineligible",
            "Effective observations are not contiguous on the metric time-unit grid.",
        )
    seasonal_period, source = _seasonal_period(
        history, payload.manual_seasonal_periods.get(metric.timeserie_key)
    )
    if seasonal_period is None:
        return _PreparedTarget(
            scenario,
            metric,
            "requires_manual_seasonal_period",
            "Automatic seasonality is inconclusive; provide a manual seasonal period.",
            None,
            None,
            history,
            [],
            periods,
            [],
        )
    history_features = _known_features(
        session,
        scenario,
        metric.timeserie_id,
        metric.time_unit,
        [day for day, _, _ in history],
    )
    features = _known_features(
        session, scenario, metric.timeserie_id, metric.time_unit, periods
    )
    return _PreparedTarget(
        scenario,
        metric,
        "eligible",
        None,
        seasonal_period,
        source,
        history,
        history_features,
        periods,
        features,
    )


def _target_history(
    session: Session,
    target_metric: Timeserie,
    payload: PredictionRequestBase,
    first_period: dt_date,
) -> list[Observation]:
    values = session.scalars(
        select(TimeserieValue)
        .where(
            TimeserieValue.timeserie_id == target_metric.timeserie_id,
            TimeserieValue.deleted_time.is_(None),
        )
        .order_by(TimeserieValue.date)
        .limit(MAX_HISTORY + 1)
    ).all()
    history: list[Observation] = []
    for item in values:
        if payload.cutoff_mode == "asOfStart" and item.date >= first_period:
            continue
        value = item.value.get("value")
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            continue
        history.append((item.date, float(value), "targetScenario"))
    return history


def _known_features(
    session: Session,
    scenario: Scenario,
    metric_id: int,
    time_unit: str,
    periods: list[dt_date],
) -> list[dict[str, float]]:
    events = session.scalars(
        select(Event).where(
            Event.scenario_id == scenario.scenario_id, Event.deleted_time.is_(None)
        )
    ).all()
    nodes = session.scalars(
        select(GraphNode).where(
            GraphNode.scenario_id == scenario.scenario_id,
            GraphNode.deleted_time.is_(None),
        )
    ).all()
    edges = session.scalars(
        select(GraphEdge).where(
            GraphEdge.scenario_id == scenario.scenario_id,
            GraphEdge.deleted_time.is_(None),
        )
    ).all()
    node_types = {
        node_type.node_type_id: node_type.node_type_key
        for node_type in session.scalars(select(NodeType)).all()
    }
    edge_types = {
        edge_type.edge_type_id: edge_type.edge_type_key
        for edge_type in session.scalars(select(EdgeType)).all()
    }
    output: list[dict[str, float]] = []
    for period in periods:
        active_nodes = [
            node
            for node in nodes
            if _visible_at(node.create_date, node.delete_date, period)
        ]
        active_edges = [
            edge
            for edge in edges
            if _visible_at(edge.create_date, edge.delete_date, period)
        ]
        feature: dict[str, float] = {
            "eventCount": float(
                sum(
                    _period_start(event.target_date, time_unit) == period
                    for event in events
                )
            ),
            "activeNodeCount": float(len(active_nodes)),
            "activeEdgeCount": float(len(active_edges)),
            "metricLinkedNodeCount": float(
                sum(
                    node.timeserie_id == metric_id
                    or node.timeserie_secondary_id == metric_id
                    for node in active_nodes
                )
            ),
        }
        for type_key, count in Counter(
            node_types.get(node.node_type_id, "unknown") for node in active_nodes
        ).items():
            feature[f"nodeType:{type_key}"] = float(count)
        for type_key, count in Counter(
            edge_types.get(edge.edge_type_id, "unknown") for edge in active_edges
        ).items():
            feature[f"edgeType:{type_key}"] = float(count)
        output.append(feature)
    return output


def _persist_result_set(
    session: Session,
    target: PredictionTarget,
    row: _PreparedTarget,
    actor_user_id: int,
) -> None:
    if row.status != "eligible":
        for kind in RESULT_KINDS:
            session.add(
                PredictionModelResult(
                    prediction_target_id=target.prediction_target_id,
                    result_kind=kind,
                    status="ineligible",
                    reason=row.reason,
                    cross_validation_status="unavailable",
                    configuration=MODEL_CONFIGURATION,
                    created_by=actor_user_id,
                )
            )
        return
    values = [value for _, value, _ in row.history]
    points_by_kind: dict[str, list[float]] = {
        "naive": [values[-1]] * len(row.periods),
        "average": [mean(values)] * len(row.periods),
        "seasonal_naive": _seasonal_naive(
            values, len(row.periods), row.seasonal_period or 1
        ),
    }
    for kind in ("naive", "seasonal_naive", "average"):
        _save_result(
            session,
            target,
            kind,
            "available",
            None,
            "not_applicable",
            None,
            points_by_kind[kind],
            actor_user_id,
        )
    ml_points, ml_status, ml_reason, ml_cv_status, ml_mae = _mlforecast_points(row)
    _save_result(
        session,
        target,
        "mlforecast",
        ml_status,
        ml_reason,
        ml_cv_status,
        ml_mae,
        ml_points,
        actor_user_id,
    )
    sarima_points, sarima_status, sarima_reason = _sarima_points(row)
    _save_result(
        session,
        target,
        "sarima",
        sarima_status,
        sarima_reason,
        "not_applicable",
        None,
        sarima_points,
        actor_user_id,
    )


def _save_result(
    session: Session,
    target: PredictionTarget,
    kind: str,
    result_status: str,
    reason: str | None,
    cv_status: str,
    cv_mae: float | None,
    values: list[float],
    actor_user_id: int,
) -> None:
    if result_status == "available":
        non_finite_reason = _non_finite_result_reason(kind, values, cv_mae)
        if non_finite_reason is not None:
            result_status = "ineligible"
            reason = non_finite_reason
            cv_status = "unavailable"
            cv_mae = None
            values = []
    result = PredictionModelResult(
        prediction_target_id=target.prediction_target_id,
        result_kind=kind,
        status=result_status,
        reason=reason,
        cross_validation_status=cv_status,
        cross_validation_mae=cv_mae,
        configuration=MODEL_CONFIGURATION,
        created_by=actor_user_id,
    )
    session.add(result)
    session.flush()
    if result_status == "available":
        session.add_all(
            PredictionPoint(
                prediction_model_result_id=result.prediction_model_result_id,
                date=day,
                value=value,
                created_by=actor_user_id,
            )
            for day, value in zip(
                _current_periods(target.input_snapshot), values, strict=True
            )
        )


def _mlforecast_points(
    row: _PreparedTarget,
) -> tuple[list[float], str, str | None, str, float | None]:
    # The package is used for the actual fitting path. Short histories are a normal
    # per-model state, not a failed version.
    if len(row.history) < 12:
        return (
            [],
            "ineligible",
            "MLForecast needs at least 12 contiguous observations.",
            "unavailable",
            None,
        )
    try:
        import pandas as pd
        from mlforecast import MLForecast
        from sklearn.ensemble import RandomForestRegressor

        normalised = _normalised_features(row.history_features, row.features)
        history_frame = pd.DataFrame(
            [
                {"unique_id": "metric", "ds": day, "y": value, **features}
                for (day, value, _), features in zip(
                    row.history, normalised[: len(row.history_features)], strict=True
                )
            ]
        )
        history_frame["ds"] = pd.to_datetime(history_frame["ds"])
        model = MLForecast(
            models=[
                RandomForestRegressor(
                    n_estimators=50, max_depth=8, random_state=41, n_jobs=1
                )
            ],
            freq=_mlforecast_frequency(row.metric.time_unit),
            lags=[1, 2, 3, 7],
            date_features=["year", "month", "dayofweek"],
        )
        model.fit(history_frame, static_features=[])
        future_features = normalised[len(row.history_features) :]
        future_frame = pd.DataFrame(
            [
                {"unique_id": "metric", "ds": day, **features}
                for day, features in zip(row.periods, future_features, strict=True)
            ]
        )
        future_frame["ds"] = pd.to_datetime(future_frame["ds"])
        prediction = model.predict(len(row.periods), X_df=future_frame)
        values = [float(value) for value in prediction.iloc[:, -1].tolist()]
        mae: float | None = None
        if len(row.history) >= 12:
            cross_validation = model.cross_validation(
                history_frame,
                n_windows=3,
                h=1,
                static_features=[],
            )
            mae = float(
                (cross_validation["y"] - cross_validation.iloc[:, -1]).abs().mean()
            )
        return (
            values,
            "available",
            None,
            "available" if mae is not None else "unavailable",
            mae,
        )
    except ValueError as exc:
        return (
            [],
            "ineligible",
            f"MLForecast cannot fit this metric: {exc}",
            "unavailable",
            None,
        )


def _sarima_points(row: _PreparedTarget) -> tuple[list[float], str, str | None]:
    if len(row.history) < max(8, (row.seasonal_period or 2) * 2):
        return (
            [],
            "ineligible",
            "SARIMA has insufficient history for the selected seasonal period.",
        )
    try:
        import numpy as np
        from statsmodels.tools.sm_exceptions import ConvergenceWarning
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        normalised = _normalised_features(row.history_features, row.features)
        history_exog = np.asarray(
            [
                list(features.values())
                for features in normalised[: len(row.history_features)]
            ],
            dtype=float,
        )
        future_exog = np.asarray(
            [
                list(features.values())
                for features in normalised[len(row.history_features) :]
            ],
            dtype=float,
        )
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always", ConvergenceWarning)
            fitted = SARIMAX(
                [value for _, value, _ in row.history],
                exog=history_exog,
                order=(1, 0, 0),
                seasonal_order=(1, 0, 0, row.seasonal_period),
                trend="c",
            ).fit(disp=False, maxiter=50)
        emitted_convergence_warning = any(
            issubclass(caught.category, ConvergenceWarning)
            for caught in caught_warnings
        )
        mle_retvals = fitted.mle_retvals
        converged = bool(mle_retvals.get("converged", False))
        if emitted_convergence_warning or not converged:
            return [], "ineligible", "SARIMA fitting did not converge."
        return (
            [
                float(value)
                for value in fitted.forecast(len(row.periods), exog=future_exog)
            ],
            "available",
            None,
        )
    except ValueError as exc:
        return [], "ineligible", f"SARIMA cannot fit this metric: {exc}"


def _seasonal_naive(values: list[float], amount: int, period: int) -> list[float]:
    generated = values.copy()
    for _ in range(amount):
        generated.append(generated[-period])
    return generated[-amount:]


def _seasonal_period(
    history: list[Observation], manual_period: int | None
) -> tuple[int | None, str | None]:
    if manual_period is not None:
        return manual_period, "manual"
    values = [value for _, value, _ in history]
    candidates = [
        period
        for period in range(2, min(24, len(values) // 3 + 1))
        if _autocorrelation(values, period) >= 0.35
    ]
    if not candidates:
        return None, None
    scored = [
        (
            mean(
                abs(values[index] - values[index - period])
                for index in range(period, len(values))
            ),
            period,
        )
        for period in candidates
    ]
    return min(scored)[1], "automatic"


def _autocorrelation(values: list[float], lag: int) -> float:
    left, right = values[:-lag], values[lag:]
    left_mean, right_mean = mean(left), mean(right)
    numerator = sum(
        (a - left_mean) * (b - right_mean) for a, b in zip(left, right, strict=True)
    )
    denominator = math.sqrt(
        sum((a - left_mean) ** 2 for a in left)
        * sum((b - right_mean) ** 2 for b in right)
    )
    return numerator / denominator if denominator else 0.0


def _normalised_features(
    history_features: list[dict[str, float]], future_features: list[dict[str, float]]
) -> list[dict[str, float]]:
    keys = sorted(
        {key for features in [*history_features, *future_features] for key in features}
    )
    return [
        {key: features.get(key, 0.0) for key in keys}
        for features in [*history_features, *future_features]
    ]


def _period_start(value: dt_date, time_unit: str) -> dt_date:
    if time_unit == "day":
        return value
    if time_unit == "week":
        return dt_date.fromordinal(value.toordinal() - value.weekday())
    if time_unit == "month":
        return value.replace(day=1)
    return value.replace(month=1, day=1)


def _periods_in_range(start: dt_date, end: dt_date, time_unit: str) -> list[dt_date]:
    current = _period_start(start, time_unit)
    result: list[dt_date] = []
    while current <= end:
        if current >= start:
            result.append(current)
        current = _next_period(current, time_unit)
    return result


def _next_period(value: dt_date, time_unit: str) -> dt_date:
    if time_unit == "day":
        return dt_date.fromordinal(value.toordinal() + 1)
    if time_unit == "week":
        return dt_date.fromordinal(value.toordinal() + 7)
    if time_unit == "month":
        return dt_date(
            value.year + (value.month == 12),
            1 if value.month == 12 else value.month + 1,
            1,
        )
    return dt_date(value.year + 1, 1, 1)


def _is_contiguous(days: list[dt_date], time_unit: str) -> bool:
    return bool(days) and all(
        right == _next_period(left, time_unit)
        for left, right in zip(days, days[1:], strict=False)
    )


def _visible_at(
    create_date: dt_date, delete_date: dt_date | None, period: dt_date
) -> bool:
    return create_date <= period and (delete_date is None or period <= delete_date)


def _mlforecast_frequency(time_unit: str) -> str:
    return {"day": "D", "week": "W-MON", "month": "MS", "year": "YS"}[time_unit]


def _current_periods(snapshot: dict[str, object]) -> list[dt_date]:
    raw_periods = snapshot.get("periods", [])
    if not isinstance(raw_periods, list):
        return []
    return [
        dt_date.fromisoformat(str(item["date"]))
        for item in raw_periods
        if isinstance(item, dict)
    ]


def _enforce_limits(rows: list[_PreparedTarget]) -> None:
    eligible = [row for row in rows if row.status == "eligible"]
    if len(eligible) > MAX_PAIRS:
        raise _pair_limit_exception()
    if sum(len(row.periods) * len(RESULT_KINDS) for row in eligible) > MAX_POINTS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Prediction request exceeds the {MAX_POINTS} prediction point limit."
            ),
        )


def _version_list_item(version: PredictionVersion) -> PredictionVersionListResponse:
    return PredictionVersionListResponse(
        id=version.prediction_key,
        name=version.name,
        startDate=version.start_date,
        endDate=version.end_date,
        cutoffMode=cast(CutoffMode, version.cutoff_mode),
        createdTime=version.created_time.isoformat(),
    )


def _version_detail(
    session: Session, version: PredictionVersion
) -> PredictionVersionDetailResponse:
    targets = session.scalars(
        select(PredictionTarget)
        .where(PredictionTarget.prediction_version_id == version.prediction_version_id)
        .order_by(PredictionTarget.prediction_target_id)
    ).all()
    return PredictionVersionDetailResponse(
        **_version_list_item(version).model_dump(),
        modelConfiguration=version.model_configuration,
        targets=[_target_response(session, target) for target in targets],
    )


def _target_response(
    session: Session, target: PredictionTarget
) -> PredictionTargetResponse:
    results = session.scalars(
        select(PredictionModelResult)
        .where(
            PredictionModelResult.prediction_target_id == target.prediction_target_id
        )
        .order_by(PredictionModelResult.prediction_model_result_id)
    ).all()
    return PredictionTargetResponse(
        scenarioId=target.target_scenario_key,
        metricId=target.metric_key,
        metricName=target.metric_name,
        timeUnit=target.time_unit,
        unit=target.unit,
        status=target.eligibility_status,
        reason=target.eligibility_reason,
        seasonalPeriod=target.seasonal_period,
        seasonalPeriodSource=target.seasonal_period_source,
        sourceSnapshot=target.source_snapshot,
        inputSnapshot=target.input_snapshot,
        results=[_result_response(session, result) for result in results],
    )


def _result_response(
    session: Session, result: PredictionModelResult
) -> PredictionModelResultResponse:
    points = session.scalars(
        select(PredictionPoint)
        .where(
            PredictionPoint.prediction_model_result_id
            == result.prediction_model_result_id
        )
        .order_by(PredictionPoint.date)
    ).all()
    return PredictionModelResultResponse(
        kind=result.result_kind,
        status=result.status,
        reason=result.reason,
        crossValidationStatus=result.cross_validation_status,
        crossValidationMae=result.cross_validation_mae,
        configuration=result.configuration,
        points=[
            PredictionPointResponse(date=point.date, value=point.value)
            for point in points
        ],
    )


def _duplicate_name_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            "A prediction version with this name already exists in the organisation."
        ),
    )


def _is_duplicate_prediction_name_error(error: IntegrityError) -> bool:
    original = error.orig
    if original is None:
        return False
    try:
        diagnostic = original.diag
        return diagnostic is not None and (
            diagnostic.constraint_name == "ux_prediction_versions_organisation_name"
        )
    except AttributeError:
        return False


def _non_finite_result_reason(
    kind: str, values: list[float], cv_mae: float | None
) -> str | None:
    name = {"mlforecast": "MLForecast", "sarima": "SARIMA"}.get(kind, kind)
    if not all(math.isfinite(value) for value in values):
        return f"{name} generated non-finite forecast values."
    if cv_mae is not None and not math.isfinite(cv_mae):
        return f"{name} generated a non-finite cross-validation MAE."
    return None


def _pair_limit_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=(
            f"Prediction request exceeds the {MAX_PAIRS} forecast candidate pair limit."
        ),
    )
