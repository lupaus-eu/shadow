"""Simulations: forecasts of a Model version's metrics (Shadow feature 4).

A run forecasts every input metric with at least the method's minimum history, applies the
what-if adjustments (a percentage change per metric key), and computes the derived metrics
from the forecast values by their formulas. Results are stored with the run; a run is never
recomputed, so later edits of the version do not change what was analysed.
"""

from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.formulas import FormulaError, evaluate_formula, parse_formula
from app.forecasting import InsufficientHistory, forecast
from app.metric_engine import add_months, formula_order, series_of_version
from app.model_routes import _audit, _editor_session, _member_session, _model, version_of
from app.models import Metric, Simulation, SimulationPoint


class Adjustment(BaseModel):
    metric_key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    change_pct: float = Field(ge=-100, le=1000)


class SimulationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    method: Literal["linear", "seasonal", "holt"] = "linear"
    horizon_months: int = Field(default=12, ge=1, le=60)
    adjustments: list[Adjustment] = Field(default_factory=list, max_length=100)

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if not (value := " ".join(value.split())):
            raise ValueError("must not be blank")
        return value


class SimulationResponse(BaseModel):
    id: UUID
    version_id: UUID
    name: str
    method: str
    horizon_months: int
    adjustments: list[Adjustment]
    skipped: dict[str, str]
    history_end: date | None
    created_at: str


class HistoryPoint(BaseModel):
    period: date
    value: float


class ForecastPointResponse(BaseModel):
    period: date
    value: float
    lower: float | None
    upper: float | None


class MetricResult(BaseModel):
    key: str
    name: str
    unit: str | None
    derived: bool
    history: list[HistoryPoint]
    forecast: list[ForecastPointResponse]


class SimulationResult(BaseModel):
    simulation: SimulationResponse
    metrics: list[MetricResult]


def _response(simulation: Simulation) -> SimulationResponse:
    return SimulationResponse(id=simulation.id, version_id=simulation.version_id, name=simulation.name, method=simulation.method, horizon_months=simulation.horizon_months, adjustments=[Adjustment(**item) for item in simulation.adjustments], skipped=simulation.skipped, history_end=simulation.history_end, created_at=simulation.created_at.isoformat())


def run_simulation(session: Session, simulation: Simulation) -> None:
    """Forecast the version's input metrics and derive the rest; stores points and the skipped reasons."""
    metrics, series = series_of_version(session, simulation.version_id)
    inputs = {key: metric for key, metric in metrics.items() if not metric.formula}
    usable = {key: values for key, values in series.items() if key in inputs and values}
    simulation.history_end = max((max(values) for values in usable.values()), default=None)
    skipped: dict[str, str] = {key: "no_values" for key in inputs if not series[key]}
    if simulation.history_end is None:
        simulation.skipped = skipped
        return
    until = add_months(simulation.history_end, simulation.horizon_months)
    factor = {item["metric_key"]: 1 + item["change_pct"] / 100 for item in simulation.adjustments}
    combined: dict[str, dict[date, float]] = {}
    bands: dict[str, dict[date, tuple[float, float]]] = {}
    for key, values in usable.items():
        try:
            points = forecast(values, simulation.method, until)
        except InsufficientHistory:
            skipped[key] = "insufficient_history"
            continue
        scale = factor.get(key, 1.0)
        combined[key] = dict(values) | {point.period: point.value * scale for point in points}
        bands[key] = {point.period: (point.lower * scale, point.upper * scale) for point in points}
    for key in formula_order(metrics):
        parsed = parse_formula(metrics[key].formula or "")
        if not all(name in combined for name in parsed.identifiers):
            skipped[key] = "inputs_missing"
            continue
        combined[key] = {}
        for period in sorted(set.intersection(*(set(combined[name]) for name in parsed.identifiers))):
            try:
                combined[key][period] = evaluate_formula(parsed, {name: combined[name][period] for name in parsed.identifiers})
            except (FormulaError, ZeroDivisionError, OverflowError):
                continue
    simulation.skipped = skipped
    for key, values in combined.items():
        for period, value in values.items():
            if period <= simulation.history_end and key in series and series[key].get(period) == value:
                continue  # history is read from the version, not stored
            lower, upper = bands.get(key, {}).get(period, (None, None))
            session.add(SimulationPoint(simulation_id=simulation.id, metric_key=key, period=period, organization_id=simulation.organization_id, value=value, lower=lower, upper=upper))
    session.flush()


def result_of(session: Session, simulation: Simulation) -> SimulationResult:
    metrics = {metric.key: metric for metric in session.scalars(select(Metric).where(Metric.version_id == simulation.version_id).order_by(Metric.key)).all()}
    _, history = series_of_version(session, simulation.version_id)
    points: dict[str, list[SimulationPoint]] = {}
    for point in session.scalars(select(SimulationPoint).where(SimulationPoint.simulation_id == simulation.id).order_by(SimulationPoint.metric_key, SimulationPoint.period)).all():
        points.setdefault(point.metric_key, []).append(point)
    results = []
    for key, metric in metrics.items():
        if key not in points and key in simulation.skipped:
            continue
        past = [HistoryPoint(period=period, value=value) for period, value in sorted(history.get(key, {}).items()) if simulation.history_end is None or period <= simulation.history_end]
        future = [ForecastPointResponse(period=point.period, value=point.value, lower=point.lower, upper=point.upper) for point in points.get(key, []) if simulation.history_end is None or point.period > simulation.history_end]
        results.append(MetricResult(key=key, name=metric.name, unit=metric.unit, derived=bool(metric.formula), history=past, forecast=future))
    return SimulationResult(simulation=_response(simulation), metrics=results)


def _simulation(session: Session, version_id: UUID, simulation_id: UUID) -> Simulation:
    simulation = session.scalar(select(Simulation).where(Simulation.id == simulation_id, Simulation.version_id == version_id))
    if simulation is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return simulation


def create_simulation_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Simulations"])
    base = "/{organization_id}/models/{model_id}/versions/{version_id}/simulations"

    @router.get(base, response_model=list[SimulationResponse])
    def list_simulations(organization_id: UUID, model_id: UUID, version_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[SimulationResponse]:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            version = version_of(session, organization_id, model_id, version_id)
            return [_response(item) for item in session.scalars(select(Simulation).where(Simulation.version_id == version.id).order_by(Simulation.created_at.desc())).all()]

    @router.post(base, response_model=SimulationResult, status_code=201)
    def run(organization_id: UUID, model_id: UUID, version_id: UUID, body: SimulationRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SimulationResult:
        with _editor_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id)
            version = version_of(session, organization_id, model.id, version_id)
            keys = set(session.scalars(select(Metric.key).where(Metric.version_id == version.id)).all())
            unknown = [item.metric_key for item in body.adjustments if item.metric_key not in keys]
            if unknown:
                raise HTTPException(status_code=422, detail=f"unknown metric keys: {', '.join(unknown)}")
            simulation = Simulation(id=uuid4(), organization_id=organization_id, model_id=model.id, version_id=version.id, name=body.name, method=body.method, horizon_months=body.horizon_months, adjustments=[item.model_dump() for item in body.adjustments], skipped={}, created_by_user_account_id=user.account.id)
            session.add(simulation)
            session.flush()
            run_simulation(session, simulation)
            _audit(session, request, "simulation.created", "simulation", simulation.id, {"version": version.name, "method": body.method, "horizon_months": body.horizon_months})
            session.refresh(simulation)
            return result_of(session, simulation)

    @router.get(base + "/{simulation_id}", response_model=SimulationResult)
    def read(organization_id: UUID, model_id: UUID, version_id: UUID, simulation_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SimulationResult:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            version = version_of(session, organization_id, model_id, version_id)
            return result_of(session, _simulation(session, version.id, simulation_id))

    @router.delete(base + "/{simulation_id}", status_code=204)
    def delete(organization_id: UUID, model_id: UUID, version_id: UUID, simulation_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _editor_session(session_factory, organization_id, user) as session:
            version = version_of(session, organization_id, model_id, version_id)
            simulation = _simulation(session, version.id, simulation_id)
            _audit(session, request, "simulation.deleted", "simulation", simulation.id, {"name": simulation.name})
            session.delete(simulation)
        return Response(status_code=204)

    return router


__all__: list[Any] = ["create_simulation_router", "result_of", "run_simulation"]
