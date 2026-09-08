"""Forecasting preparation, detached calculation, and publication boundaries."""
# pyright: reportAttributeAccessIssue=false, reportMissingTypeStubs=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import math
import warnings
from collections import Counter
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date as dt_date
from statistics import mean
from typing import Literal, cast
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.org_states.derived_metrics import (
    FormulaError,
    evaluate_formula,
    parse_formula,
)
from app.api.v1.org_states.models import (
    DerivedMetricEquation,
    Event,
    Scenario,
    Timeserie,
    TimeserieValue,
)
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
from app.api.v1.predictions.snapshots import (
    CalculatedResult,
    CalculatedTarget,
    CrossValidationStatus,
    EligibilityStatus,
    PredictionCalculation,
    PredictionInputSnapshot,
    PredictionIntervalStatus,
    PredictionTargetSnapshot,
    ResultKind,
    ResultStatus,
    SnapshotFeaturePeriod,
    SnapshotMetricReference,
    SnapshotObservation,
    TimeUnit,
)

RESULT_KINDS = ("naive", "seasonal_naive", "average", "mlforecast", "sarima")
type Observation = tuple[dt_date, float, Literal["targetScenario"]]
MAX_PAIRS = 50
MAX_PERIODS = 366
MAX_HISTORY = 10_000
MAX_POINTS = 100_000
BASE_MODEL_CONFIGURATION: dict[str, object] = {
    "seed": 41,
    "mlforecast": {"lags": [1, 2, 3, 7], "randomForestEstimators": 50, "maxDepth": 8},
    "sarima": {
        "order": [1, 0, 0],
        "seasonalOrder": [1, 0, 0],
        "maxiter": 50,
    },
}


@dataclass(frozen=True)
class _GeneratedResult:
    values: list[float]
    status: ResultStatus
    reason: str | None
    cross_validation_status: CrossValidationStatus
    cross_validation_mae: float | None
    prediction_interval_status: PredictionIntervalStatus
    prediction_interval_reason: str | None
    bounds: list[tuple[float, float]] | None = None


def _model_configuration(confidence_level: int) -> dict[str, object]:
    return {
        **BASE_MODEL_CONFIGURATION,
        "predictionIntervals": {
            "confidenceLevel": confidence_level,
            "mlforecast": {
                "method": "conformal_error",
                "nWindows": 3,
                "h": 1,
            },
            "sarima": {
                "method": "native_forecast_result",
                "alpha": round(1 - confidence_level / 100, 10),
            },
        },
    }


def preflight_predictions(
    session: Session, organisation_key: str, payload: PredictionPreflightRequest
) -> PredictionPreflightResponse:
    with _consistent_read_session(session) as read_session:
        organisation, targets = _request_context(
            read_session, organisation_key, payload
        )
        del organisation
        rows = _prepare_targets(read_session, targets, payload)
    _enforce_limits(rows)
    return PredictionPreflightResponse(
        metrics=[_preflight_response(row) for row in rows]
    )


def create_prediction(
    session: Session,
    organisation_key: str,
    payload: PredictionCreateRequest,
    actor_user_id: int,
) -> PredictionVersionDetailResponse:
    snapshot = prepare_prediction_snapshot(
        session, organisation_key, payload, actor_user_id
    )
    calculation = calculate_prediction(snapshot)
    return publish_prediction(session, snapshot, calculation)


def prepare_prediction_snapshot(
    session: Session,
    organisation_key: str,
    payload: PredictionCreateRequest,
    actor_user_id: int,
) -> PredictionInputSnapshot:
    """Freeze every source and configuration input in one database snapshot."""
    with _consistent_read_session(session) as read_session:
        organisation, targets = _request_context(
            read_session, organisation_key, payload
        )
        rows = _prepare_targets(read_session, targets, payload)
        _enforce_limits(rows)
        if (
            read_session.scalar(
                select(PredictionVersion.prediction_version_id).where(
                    PredictionVersion.organisation_id == organisation.organisation_id,
                    func.lower(PredictionVersion.name) == payload.name.lower(),
                )
            )
            is not None
        ):
            raise _duplicate_name_exception()
        return PredictionInputSnapshot(
            organisationInternalId=organisation.organisation_id,
            organisationKey=organisation.organisation_key,
            predictionKey=f"prediction_{uuid4().hex}",
            name=payload.name,
            creatorUserId=actor_user_id,
            cutoffMode=payload.cutoff_mode,
            confidenceLevel=payload.confidence_level,
            startDate=payload.start_date,
            endDate=payload.end_date,
            modelConfiguration=_model_configuration(payload.confidence_level),
            targets=rows,
        )


def publish_prediction(
    session: Session,
    snapshot: PredictionInputSnapshot,
    calculation: PredictionCalculation,
) -> PredictionVersionDetailResponse:
    """Persist one detached calculation as an immutable version transaction."""
    if (
        calculation.snapshot_format != snapshot.snapshot_format
        or calculation.prediction_key != snapshot.prediction_key
        or len(calculation.targets) != len(snapshot.targets)
    ):
        raise ValueError("Calculation output does not match its prediction snapshot.")
    expected_kinds = set(RESULT_KINDS)
    for row, calculated_target in zip(
        snapshot.targets, calculation.targets, strict=True
    ):
        if (
            calculated_target.scenario_key != row.scenario_key
            or calculated_target.metric_key != row.metric_key
            or {result.kind for result in calculated_target.results} != expected_kinds
            or any(
                result.status == "available"
                and len(result.values) != len(row.prediction_periods)
                for result in calculated_target.results
            )
        ):
            raise ValueError(
                "Calculation output does not match its prediction snapshot."
            )
    if (
        session.scalar(
            select(PredictionVersion.prediction_version_id).where(
                PredictionVersion.organisation_id == snapshot.organisation_internal_id,
                func.lower(PredictionVersion.name) == snapshot.name.lower(),
            )
        )
        is not None
    ):
        raise _duplicate_name_exception()
    version = PredictionVersion(
        organisation_id=snapshot.organisation_internal_id,
        prediction_key=snapshot.prediction_key,
        name=snapshot.name,
        cutoff_mode=snapshot.cutoff_mode,
        confidence_level=snapshot.confidence_level,
        start_date=snapshot.start_date,
        end_date=snapshot.end_date,
        model_configuration=snapshot.model_configuration,
        created_by=snapshot.creator_user_id,
    )
    try:
        session.add(version)
        session.flush()
        for row, calculated_target in zip(
            snapshot.targets, calculation.targets, strict=True
        ):
            if (
                calculated_target.scenario_key != row.scenario_key
                or calculated_target.metric_key != row.metric_key
            ):
                raise ValueError("Calculated target order does not match the snapshot.")
            target = PredictionTarget(
                prediction_version_id=version.prediction_version_id,
                target_scenario_id=row.scenario_internal_id,
                target_scenario_key=row.scenario_key,
                metric_key=row.metric_key,
                metric_name=row.metric_name,
                time_unit=row.time_unit,
                unit=row.unit,
                eligibility_status=row.status,
                eligibility_reason=row.reason,
                seasonal_period=row.seasonal_period,
                seasonal_period_source=row.seasonal_period_source,
                source_snapshot=row.source_audit_snapshot(),
                input_snapshot=row.input_audit_snapshot(),
                created_by=snapshot.creator_user_id,
            )
            session.add(target)
            session.flush()
            for generated in calculated_target.results:
                _save_result(
                    session,
                    target,
                    [item.date for item in row.prediction_periods],
                    generated,
                    snapshot.model_configuration,
                    snapshot.creator_user_id,
                )
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


@contextmanager
def _consistent_read_session(session: Session) -> Generator[Session]:
    """Use one PostgreSQL REPEATABLE READ transaction for snapshot preparation."""
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        yield session
        return
    snapshot_bind = bind.execution_options(isolation_level="REPEATABLE READ")
    with Session(bind=snapshot_bind, autoflush=False) as read_session:
        with read_session.begin():
            yield read_session


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


_PreparedTarget = PredictionTargetSnapshot


def _preflight_response(
    row: PredictionTargetSnapshot,
) -> PredictionMetricPreflightResponse:
    return PredictionMetricPreflightResponse(
        scenarioId=row.scenario_key,
        metricId=row.metric_key,
        status=row.status,
        reason=row.reason,
        seasonalPeriod=row.seasonal_period,
        seasonalPeriodSource=row.seasonal_period_source,
        requiresManualSeasonalPeriod=row.status == "requires_manual_seasonal_period",
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
        equations = {
            equation.derived_timeserie_id: equation
            for equation in session.scalars(
                select(DerivedMetricEquation).where(
                    DerivedMetricEquation.scenario_id == scenario.scenario_id,
                    DerivedMetricEquation.deleted_time.is_(None),
                )
            ).all()
        }
        metrics_by_id = {metric.timeserie_id: metric for metric in metrics}
        referenced_ids = {
            reference_id
            for equation in equations.values()
            for reference_id in equation.referenced_timeserie_ids
        }
        if referenced_ids:
            metrics_by_id.update(
                {
                    metric.timeserie_id: metric
                    for metric in session.scalars(
                        select(Timeserie).where(
                            Timeserie.scenario_id == scenario.scenario_id,
                            Timeserie.timeserie_id.in_(referenced_ids),
                        )
                    ).all()
                }
            )
        for metric in [
            item for item in metrics if item.timeserie_id not in equations
        ] + [item for item in metrics if item.timeserie_id in equations]:
            if _is_model_candidate(metric) and metric.timeserie_id not in equations:
                candidate_count += 1
                if candidate_count > MAX_PAIRS:
                    raise _pair_limit_exception()
            row = _prepare_metric(
                session,
                scenario,
                metric,
                payload,
                equations.get(metric.timeserie_id),
                metrics_by_id,
            )
            prepared.append(row)
    return prepared


def _is_model_candidate(metric: Timeserie) -> bool:
    return metric.value_unit == "number"


def _prepare_metric(
    session: Session,
    scenario: Scenario,
    metric: Timeserie,
    payload: PredictionRequestBase,
    equation: DerivedMetricEquation | None = None,
    metrics_by_id: dict[int, Timeserie] | None = None,
) -> _PreparedTarget:
    def target(
        *,
        current_status: EligibilityStatus,
        current_reason: str | None,
        seasonal_period: int | None = None,
        seasonal_period_source: str | None = None,
        history: list[Observation] | None = None,
        history_features: list[dict[str, float]] | None = None,
        periods: list[dt_date] | None = None,
        features: list[dict[str, float]] | None = None,
        derived_formula: str | None = None,
        references: list[SnapshotMetricReference] | None = None,
    ) -> _PreparedTarget:
        current_history = history or []
        current_periods = periods or []
        current_features = (
            features if features is not None else [{} for _ in current_periods]
        )
        current_history_features = (
            history_features
            if history_features is not None
            else [{} for _ in current_history]
        )
        return _PreparedTarget(
            scenarioInternalId=scenario.scenario_id,
            scenarioKey=scenario.scenario_key,
            scenarioName=scenario.name,
            metricKey=metric.timeserie_key,
            metricName=metric.name,
            metricShortName=metric.short_name,
            timeUnit=cast(TimeUnit, metric.time_unit),
            unit=metric.unit,
            status=current_status,
            reason=current_reason,
            seasonalPeriod=seasonal_period,
            seasonalPeriodSource=seasonal_period_source,
            observations=[
                SnapshotObservation(date=day, value=value, source=source)
                for day, value, source in current_history
            ],
            historyPeriods=[
                SnapshotFeaturePeriod(date=day, features=feature_values)
                for (day, _, _), feature_values in zip(
                    current_history, current_history_features, strict=True
                )
            ],
            predictionPeriods=[
                SnapshotFeaturePeriod(date=day, features=feature_values)
                for day, feature_values in zip(
                    current_periods, current_features, strict=True
                )
            ],
            derivedFormula=derived_formula,
            referencedMetrics=references or [],
        )

    def empty(
        current_status: EligibilityStatus,
        current_reason: str,
        *,
        history: list[Observation] | None = None,
        periods: list[dt_date] | None = None,
    ) -> _PreparedTarget:
        return target(
            current_status=current_status,
            current_reason=current_reason,
            history=history,
            periods=periods,
        )

    periods = _periods_in_range(payload.start_date, payload.end_date, metric.time_unit)
    if metric.value_unit != "number":
        return empty(
            "ineligible",
            "Only numeric metrics can be forecast.",
            periods=periods,
        )
    if not periods:
        return empty(
            "ineligible", "The selected date range contains no valid metric periods."
        )
    if len(periods) > MAX_PERIODS:
        return empty(
            "ineligible",
            f"Prediction range exceeds the {MAX_PERIODS} period limit.",
            periods=periods,
        )
    if equation is not None:
        referenced_metrics = [
            metrics_by_id[reference_id]
            for reference_id in equation.referenced_timeserie_ids
            if metrics_by_id is not None and reference_id in metrics_by_id
        ]
        return target(
            current_status="eligible",
            current_reason=None,
            periods=periods,
            features=[{} for _ in periods],
            derived_formula=equation.formula,
            references=[
                SnapshotMetricReference(
                    metricKey=reference.timeserie_key,
                    shortName=reference.short_name or "",
                )
                for reference in referenced_metrics
            ],
        )
    history = _target_history(session, metric, payload, periods[0])
    if not history:
        return empty(
            "ineligible",
            "Target scenario has no observations available under the selected cutoff.",
            periods=periods,
        )
    if len(history) > MAX_HISTORY:
        return empty(
            "ineligible",
            "Effective observation history exceeds the "
            f"{MAX_HISTORY} observation limit.",
            history=history,
            periods=periods,
        )
    if not _is_contiguous([item[0] for item in history], metric.time_unit):
        return empty(
            "ineligible",
            "Effective observations are not contiguous on the metric time-unit grid.",
            history=history,
            periods=periods,
        )
    seasonal_period, source = _seasonal_period(
        history, payload.manual_seasonal_periods.get(metric.timeserie_key)
    )
    if seasonal_period is None:
        return target(
            current_status="requires_manual_seasonal_period",
            current_reason=(
                "Automatic seasonality is inconclusive; provide a manual seasonal "
                "period."
            ),
            history=history,
            periods=periods,
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
    return target(
        current_status="eligible",
        current_reason=None,
        seasonal_period=seasonal_period,
        seasonal_period_source=source,
        history=history,
        history_features=history_features,
        periods=periods,
        features=features,
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


def calculate_prediction(snapshot: PredictionInputSnapshot) -> PredictionCalculation:
    """Calculate detached results without a database session or ORM instances."""
    results_by_target: dict[tuple[str, str], list[CalculatedResult]] = {}
    normal_results: dict[tuple[str, str, str], CalculatedResult] = {}
    for row in snapshot.targets:
        if row.derived_formula is not None:
            continue
        results = _calculate_normal_result_set(row, snapshot.confidence_level)
        results_by_target[(row.scenario_key, row.metric_key)] = results
        for result in results:
            normal_results[(row.scenario_key, row.metric_key, result.kind)] = result
    for row in snapshot.targets:
        if row.derived_formula is None:
            continue
        results_by_target[(row.scenario_key, row.metric_key)] = (
            _calculate_derived_result_set(row, normal_results)
        )
    return PredictionCalculation(
        snapshotFormat=snapshot.snapshot_format,
        predictionKey=snapshot.prediction_key,
        targets=[
            CalculatedTarget(
                scenarioKey=row.scenario_key,
                metricKey=row.metric_key,
                results=results_by_target[(row.scenario_key, row.metric_key)],
            )
            for row in snapshot.targets
        ],
    )


def _calculate_normal_result_set(
    row: _PreparedTarget, confidence_level: int
) -> list[CalculatedResult]:
    if row.status != "eligible":
        return [
            _calculated_result(
                kind,
                _GeneratedResult(
                    [],
                    "ineligible",
                    row.reason,
                    "unavailable",
                    None,
                    (
                        "unavailable"
                        if kind in ("mlforecast", "sarima")
                        else "not_applicable"
                    ),
                    row.reason if kind in ("mlforecast", "sarima") else None,
                ),
            )
            for kind in RESULT_KINDS
        ]
    values = [item.value for item in row.observations]
    amount = len(row.prediction_periods)
    baseline_values = {
        "naive": [values[-1]] * amount,
        "average": [mean(values)] * amount,
        "seasonal_naive": _seasonal_naive(values, amount, row.seasonal_period or 1),
    }
    results = [
        _calculated_result(
            cast(ResultKind, kind),
            _GeneratedResult(
                baseline_values[kind],
                "available",
                None,
                "not_applicable",
                None,
                "not_applicable",
                None,
            ),
        )
        for kind in ("naive", "seasonal_naive", "average")
    ]
    results.extend(
        (
            _calculated_result("mlforecast", _mlforecast_result(row, confidence_level)),
            _calculated_result("sarima", _sarima_result(row, confidence_level)),
        )
    )
    return results


def _calculate_derived_result_set(
    row: _PreparedTarget,
    normal_results: dict[tuple[str, str, str], CalculatedResult],
) -> list[CalculatedResult]:
    assert row.derived_formula is not None
    try:
        parsed = parse_formula(row.derived_formula)
    except FormulaError as error:
        return [
            _calculated_result(
                kind,
                _GeneratedResult(
                    [],
                    "ineligible",
                    str(error),
                    "not_applicable",
                    None,
                    "not_applicable",
                    None,
                ),
            )
            for kind in RESULT_KINDS
        ]
    output: list[CalculatedResult] = []
    for kind_value in RESULT_KINDS:
        values_by_name: dict[str, list[float]] = {}
        failure: str | None = None
        for reference in row.referenced_metrics:
            source_result = normal_results.get(
                (row.scenario_key, reference.metric_key, kind_value)
            )
            if source_result is None:
                failure = (
                    f"Referenced metric {reference.metric_key} has no "
                    "prediction target."
                )
                break
            if source_result.status != "available":
                failure = (
                    f"Referenced metric {reference.metric_key} has no available "
                    f"{kind_value} result."
                )
                break
            values_by_name[reference.short_name] = source_result.values
        values: list[float] = []
        if failure is None:
            for index, period in enumerate(row.prediction_periods):
                try:
                    values.append(
                        evaluate_formula(
                            parsed,
                            {
                                name: source_values[index]
                                for name, source_values in values_by_name.items()
                            },
                        )
                    )
                except (FormulaError, IndexError, KeyError):
                    failure = (
                        "Derived formula cannot be evaluated for "
                        f"{period.date.isoformat()}."
                    )
                    break
        output.append(
            _calculated_result(
                kind_value,
                _GeneratedResult(
                    values if failure is None else [],
                    "available" if failure is None else "ineligible",
                    failure,
                    "not_applicable",
                    None,
                    "not_applicable",
                    None,
                ),
            )
        )
    return output


def _calculated_result(
    kind: ResultKind, generated: _GeneratedResult
) -> CalculatedResult:
    result_status = generated.status
    reason = generated.reason
    cv_status = generated.cross_validation_status
    cv_mae = generated.cross_validation_mae
    values = generated.values
    interval_status = generated.prediction_interval_status
    interval_reason = generated.prediction_interval_reason
    bounds = generated.bounds
    if result_status == "available":
        non_finite_reason = _non_finite_result_reason(kind, values, cv_mae)
        if non_finite_reason is not None:
            result_status = "ineligible"
            reason = non_finite_reason
            cv_status = "unavailable"
            cv_mae = None
            values = []
            interval_status = "unavailable"
            interval_reason = reason
            bounds = None
    return CalculatedResult(
        kind=kind,
        values=values,
        status=result_status,
        reason=reason,
        crossValidationStatus=cv_status,
        crossValidationMae=cv_mae,
        predictionIntervalStatus=interval_status,
        predictionIntervalReason=interval_reason,
        bounds=bounds,
    )


def _save_result(
    session: Session,
    target: PredictionTarget,
    periods: list[dt_date],
    calculated: CalculatedResult,
    model_configuration: dict[str, object],
    actor_user_id: int,
) -> None:
    result = PredictionModelResult(
        prediction_target_id=target.prediction_target_id,
        result_kind=calculated.kind,
        status=calculated.status,
        reason=calculated.reason,
        prediction_interval_status=calculated.prediction_interval_status,
        prediction_interval_reason=calculated.prediction_interval_reason,
        cross_validation_status=calculated.cross_validation_status,
        cross_validation_mae=calculated.cross_validation_mae,
        configuration=model_configuration,
        created_by=actor_user_id,
    )
    session.add(result)
    session.flush()
    if calculated.status == "available":
        session.add_all(
            PredictionPoint(
                prediction_model_result_id=result.prediction_model_result_id,
                date=day,
                value=value,
                lower_bound=(
                    calculated.bounds[index][0]
                    if calculated.bounds is not None
                    else None
                ),
                upper_bound=(
                    calculated.bounds[index][1]
                    if calculated.bounds is not None
                    else None
                ),
                created_by=actor_user_id,
            )
            for index, (day, value) in enumerate(
                zip(periods, calculated.values, strict=True)
            )
        )


def _mlforecast_result(row: _PreparedTarget, confidence_level: int) -> _GeneratedResult:
    # The package is used for the actual fitting path. Short histories are a normal
    # per-model state, not a failed version.
    if len(row.observations) < 12:
        return _GeneratedResult(
            [],
            "ineligible",
            "MLForecast needs at least 12 contiguous observations.",
            "unavailable",
            None,
            "unavailable",
            "MLForecast needs at least 12 contiguous observations.",
        )
    try:
        import pandas as pd
        from mlforecast import MLForecast
        from mlforecast.utils import PredictionIntervals
        from sklearn.ensemble import RandomForestRegressor

        history_features = [item.features for item in row.history_periods]
        future_features = [item.features for item in row.prediction_periods]
        normalised = _normalised_features(history_features, future_features)
        history_frame = pd.DataFrame(
            [
                {
                    "unique_id": "metric",
                    "ds": observation.date,
                    "y": observation.value,
                    **features,
                }
                for observation, features in zip(
                    row.observations, normalised[: len(history_features)], strict=True
                )
            ]
        )
        history_frame["ds"] = pd.to_datetime(history_frame["ds"])

        def new_model() -> MLForecast:
            return MLForecast(
                models=[
                    RandomForestRegressor(
                        n_estimators=50, max_depth=8, random_state=41, n_jobs=1
                    )
                ],
                freq=_mlforecast_frequency(row.time_unit),
                lags=[1, 2, 3, 7],
                date_features=["year", "month", "dayofweek"],
            )

        model = new_model()
        model.fit(history_frame, static_features=[])
        normalised_future_features = normalised[len(history_features) :]
        future_frame = pd.DataFrame(
            [
                {"unique_id": "metric", "ds": period.date, **features}
                for period, features in zip(
                    row.prediction_periods,
                    normalised_future_features,
                    strict=True,
                )
            ]
        )
        future_frame["ds"] = pd.to_datetime(future_frame["ds"])
        prediction = model.predict(len(row.prediction_periods), X_df=future_frame)
        values = _named_prediction_values(prediction, "RandomForestRegressor")
        mae: float | None = None
        if len(row.observations) >= 12:
            cross_validation = model.cross_validation(
                history_frame,
                n_windows=3,
                h=1,
                static_features=[],
            )
            mae = float(
                (cross_validation["y"] - cross_validation["RandomForestRegressor"])
                .abs()
                .mean()
            )
        point_result = _GeneratedResult(
            values,
            "available",
            None,
            "available" if mae is not None else "unavailable",
            mae,
            "unavailable",
            "MLForecast prediction interval is unavailable.",
        )
        try:
            interval_model = new_model()
            interval_model.fit(
                history_frame,
                static_features=[],
                prediction_intervals=PredictionIntervals(
                    n_windows=3, h=1, method="conformal_error"
                ),
            )
            # ADR-011 intentionally uses one-step calibration, so MLForecast's
            # horizon-constant-width notice is expected for multi-period output.
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=(
                        "Prediction intervals are calculated using 1-step ahead "
                        "cross-validation, with a constant width for all horizons."
                    ),
                    category=UserWarning,
                    module=r"mlforecast\.forecast",
                )
                interval_prediction = interval_model.predict(
                    len(row.prediction_periods),
                    X_df=future_frame,
                    level=[confidence_level],
                )
            interval_values = _named_prediction_values(
                interval_prediction, "RandomForestRegressor"
            )
            bounds = _validated_bounds(
                interval_values,
                _named_prediction_values(
                    interval_prediction, f"RandomForestRegressor-lo-{confidence_level}"
                ),
                _named_prediction_values(
                    interval_prediction, f"RandomForestRegressor-hi-{confidence_level}"
                ),
            )
            return _GeneratedResult(
                interval_values,
                point_result.status,
                point_result.reason,
                point_result.cross_validation_status,
                point_result.cross_validation_mae,
                "available",
                None,
                bounds,
            )
        except (KeyError, TypeError, ValueError):
            return point_result
    except ValueError as exc:
        reason = f"MLForecast cannot fit this metric: {exc}"
        return _GeneratedResult(
            [], "ineligible", reason, "unavailable", None, "unavailable", reason
        )


def _sarima_result(row: _PreparedTarget, confidence_level: int) -> _GeneratedResult:
    if len(row.observations) < max(8, (row.seasonal_period or 2) * 2):
        reason = "SARIMA has insufficient history for the selected seasonal period."
        return _GeneratedResult(
            [], "ineligible", reason, "not_applicable", None, "unavailable", reason
        )
    try:
        import numpy as np
        from statsmodels.tools.sm_exceptions import ConvergenceWarning
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        history_features = [item.features for item in row.history_periods]
        future_features = [item.features for item in row.prediction_periods]
        normalised = _normalised_features(history_features, future_features)
        history_exog = np.asarray(
            [
                list(features.values())
                for features in normalised[: len(history_features)]
            ],
            dtype=float,
        )
        future_exog = np.asarray(
            [
                list(features.values())
                for features in normalised[len(history_features) :]
            ],
            dtype=float,
        )
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always", ConvergenceWarning)
            fitted = SARIMAX(
                [item.value for item in row.observations],
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
            reason = "SARIMA fitting did not converge."
            return _GeneratedResult(
                [], "ineligible", reason, "not_applicable", None, "unavailable", reason
            )
        values = [
            float(value)
            for value in fitted.forecast(len(row.prediction_periods), exog=future_exog)
        ]
        point_result = _GeneratedResult(
            values,
            "available",
            None,
            "not_applicable",
            None,
            "unavailable",
            "SARIMA prediction interval is unavailable.",
        )
        try:
            forecast_result = fitted.get_forecast(
                len(row.prediction_periods), exog=future_exog
            )
            interval_values = [float(value) for value in forecast_result.predicted_mean]
            confidence_bounds = forecast_result.conf_int(
                alpha=1 - confidence_level / 100
            )
            if hasattr(confidence_bounds, "iloc"):
                lower_values = confidence_bounds.iloc[:, 0].tolist()
                upper_values = confidence_bounds.iloc[:, 1].tolist()
            else:
                lower_values = [pair[0] for pair in confidence_bounds]
                upper_values = [pair[1] for pair in confidence_bounds]
            return _GeneratedResult(
                interval_values,
                point_result.status,
                point_result.reason,
                point_result.cross_validation_status,
                point_result.cross_validation_mae,
                "available",
                None,
                _validated_bounds(interval_values, lower_values, upper_values),
            )
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            return point_result
    except ValueError as exc:
        reason = f"SARIMA cannot fit this metric: {exc}"
        return _GeneratedResult(
            [], "ineligible", reason, "not_applicable", None, "unavailable", reason
        )


def _named_prediction_values(prediction: object, column: str) -> list[float]:
    try:
        values = prediction[column].tolist()  # type: ignore[index,union-attr]
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("MLForecast prediction columns are unavailable.") from exc
    return [float(value) for value in values]


def _validated_bounds(
    values: list[float], lower_values: object, upper_values: object
) -> list[tuple[float, float]]:
    lower = [float(value) for value in lower_values]  # type: ignore[union-attr]
    upper = [float(value) for value in upper_values]  # type: ignore[union-attr]
    if len(values) != len(lower) or len(values) != len(upper):
        raise ValueError("Prediction interval bounds are incomplete.")
    bounds = list(zip(lower, upper, strict=True))
    if any(
        not math.isfinite(value)
        or not math.isfinite(lower_bound)
        or not math.isfinite(upper_bound)
        or lower_bound > value
        or value > upper_bound
        for value, (lower_bound, upper_bound) in zip(values, bounds, strict=True)
    ):
        raise ValueError("Prediction interval bounds are invalid.")
    return bounds


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


def _enforce_limits(rows: list[_PreparedTarget]) -> None:
    eligible = [row for row in rows if row.status == "eligible"]
    if len(eligible) > MAX_PAIRS:
        raise _pair_limit_exception()
    if (
        sum(len(row.prediction_periods) * len(RESULT_KINDS) for row in eligible)
        > MAX_POINTS
    ):
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
        confidenceLevel=version.confidence_level,
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
        predictionIntervalStatus=result.prediction_interval_status,
        predictionIntervalReason=result.prediction_interval_reason,
        crossValidationStatus=result.cross_validation_status,
        crossValidationMae=result.cross_validation_mae,
        configuration=result.configuration,
        points=[
            PredictionPointResponse(
                date=point.date,
                value=point.value,
                lowerBound=point.lower_bound,
                upperBound=point.upper_bound,
            )
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
