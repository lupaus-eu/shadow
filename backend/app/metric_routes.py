"""Metrics (KPIs): monthly values and formulas per Model version (Shadow feature 3).

An input metric holds monthly values; a derived metric has a formula over other metrics of the
same version by key and is computed on read. Every member edits; reads need no more than
membership. Deleting a metric that other formulas read is refused.
"""

from datetime import date
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.formulas import FormulaError, parse_formula
from app.metric_engine import formula_order, month_start, series_of_version
from app.model_routes import _audit, _editor_session, _member_session, _model, _stale, version_of
from app.models import Metric, MetricValue, Node

KEY_PATTERN = r"^[a-z][a-z0-9_]{0,39}$"
MAX_VALUES_PER_REQUEST = 600


class MetricRequest(BaseModel):
    key: str = Field(pattern=KEY_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    unit: str | None = Field(default=None, max_length=20)
    node_id: UUID | None = None
    formula: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if not (value := " ".join(value.split())):
            raise ValueError("must not be blank")
        return value

    @field_validator("formula")
    @classmethod
    def blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class MetricUpdate(MetricRequest):
    expected_version: int = Field(ge=1)


class MetricResponse(BaseModel):
    id: UUID
    key: str
    name: str
    unit: str | None
    node_id: UUID | None
    formula: str | None
    derived: bool
    version: int
    values: int


class ValuePoint(BaseModel):
    period: date
    value: float | None = None


class ValuesRequest(BaseModel):
    values: list[ValuePoint] = Field(max_length=MAX_VALUES_PER_REQUEST)


class SeriesResponse(BaseModel):
    metric: MetricResponse
    points: list[ValuePoint]


def _response(metric: Metric, count: int) -> MetricResponse:
    return MetricResponse(id=metric.id, key=metric.key, name=metric.name, unit=metric.unit, node_id=metric.node_id, formula=metric.formula, derived=bool(metric.formula), version=metric.version, values=count)


def _metric(session: Session, version_id: UUID, metric_id: UUID, *, lock: bool = False) -> Metric:
    statement = select(Metric).where(Metric.id == metric_id, Metric.version_id == version_id)
    metric = session.scalar(statement.with_for_update() if lock else statement)
    if metric is None:
        raise HTTPException(status_code=404, detail="Metric not found")
    return metric


def _check_formulas(session: Session, version_id: UUID, changed: Metric | None = None, removed_key: str | None = None) -> None:
    """The version's formulas must parse, read existing keys, and not form a cycle."""
    metrics = {metric.key: metric for metric in session.scalars(select(Metric).where(Metric.version_id == version_id)).all()}
    if changed is not None:
        metrics[changed.key] = changed
    if removed_key is not None:
        metrics.pop(removed_key, None)
    try:
        formula_order(metrics)
    except FormulaError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


def _validate_node(session: Session, version_id: UUID, node_id: UUID | None) -> None:
    if node_id is not None and session.scalar(select(Node.id).where(Node.id == node_id, Node.version_id == version_id)) is None:
        raise HTTPException(status_code=422, detail="node not found in this version")


def copy_metrics(session: Session, base_version_id: UUID, fork_version_id: UUID, node_mapping: dict[UUID, UUID]) -> None:
    """Copy a version's metrics and stored values into a fork (nodes already copied)."""
    mapping: dict[UUID, UUID] = {}
    for metric in session.scalars(select(Metric).where(Metric.version_id == base_version_id)).all():
        copy = Metric(id=uuid4(), organization_id=metric.organization_id, model_id=metric.model_id, version_id=fork_version_id, node_id=node_mapping.get(metric.node_id) if metric.node_id else None, key=metric.key, name=metric.name, unit=metric.unit, formula=metric.formula, version=1)
        mapping[metric.id] = copy.id
        session.add(copy)
    session.flush()
    for value in session.scalars(select(MetricValue).where(MetricValue.version_id == base_version_id)).all():
        session.add(MetricValue(metric_id=mapping[value.metric_id], period=value.period, organization_id=value.organization_id, version_id=fork_version_id, value=value.value))
    session.flush()


def create_metric_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Metrics"])
    base = "/{organization_id}/models/{model_id}/versions/{version_id}/metrics"

    @router.get(base, response_model=list[MetricResponse])
    def list_metrics(organization_id: UUID, model_id: UUID, version_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[MetricResponse]:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            version = version_of(session, organization_id, model_id, version_id)
            metrics, series = series_of_version(session, version.id)
            return [_response(metric, len(series[key])) for key, metric in metrics.items()]

    @router.post(base, response_model=MetricResponse, status_code=201)
    def create_metric(organization_id: UUID, model_id: UUID, version_id: UUID, body: MetricRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> MetricResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id)
            version = version_of(session, organization_id, model.id, version_id)
            if session.scalar(select(Metric.id).where(Metric.version_id == version.id, Metric.key == body.key)) is not None:
                raise HTTPException(status_code=409, detail={"reason": "duplicate_key"})
            _validate_node(session, version.id, body.node_id)
            metric = Metric(id=uuid4(), organization_id=organization_id, model_id=model.id, version_id=version.id, node_id=body.node_id, key=body.key, name=body.name, unit=body.unit, formula=body.formula, version=1)
            _check_formulas(session, version.id, changed=metric)
            session.add(metric)
            session.flush()
            _audit(session, request, "metric.created", "metric", metric.id, {"key": metric.key, "name": metric.name})
            return _response(metric, 0)

    @router.patch(base + "/{metric_id}", response_model=MetricResponse)
    def update_metric(organization_id: UUID, model_id: UUID, version_id: UUID, metric_id: UUID, body: MetricUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> MetricResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            version = version_of(session, organization_id, model_id, version_id)
            metric = _metric(session, version.id, metric_id, lock=True)
            _stale(metric.version, body.expected_version)
            if body.key != metric.key:
                raise HTTPException(status_code=422, detail="the key of a metric cannot change")
            _validate_node(session, version.id, body.node_id)
            was_derived = bool(metric.formula)
            changes = {key: value for key, value in (("name", body.name), ("unit", body.unit), ("node_id", str(body.node_id) if body.node_id else None), ("formula", body.formula)) if (str(getattr(metric, key)) if key == "node_id" and getattr(metric, key) else getattr(metric, key)) != value}
            metric.name, metric.unit, metric.node_id, metric.formula = body.name, body.unit, body.node_id, body.formula
            _check_formulas(session, version.id, changed=metric)
            if body.formula and not was_derived:
                session.execute(delete(MetricValue).where(MetricValue.metric_id == metric.id))  # a derived metric holds no stored values
            metric.version += 1
            _audit(session, request, "metric.updated", "metric", metric.id, {key: value for key, value in changes.items() if key != "formula"} | ({"formula_changed": True} if "formula" in changes else {}))
            count = len(series_of_version(session, version.id)[1][metric.key])
            return _response(metric, count)

    @router.delete(base + "/{metric_id}", status_code=204)
    def delete_metric(organization_id: UUID, model_id: UUID, version_id: UUID, metric_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _editor_session(session_factory, organization_id, user) as session:
            version = version_of(session, organization_id, model_id, version_id)
            metric = _metric(session, version.id, metric_id, lock=True)
            _stale(metric.version, expected_version)
            readers = [other.key for other in session.scalars(select(Metric).where(Metric.version_id == version.id, Metric.formula.is_not(None), Metric.id != metric.id)).all() if metric.key in parse_formula(other.formula or "").identifiers]
            if readers:
                raise HTTPException(status_code=409, detail={"reason": "read_by_formulas", "metrics": readers})
            _audit(session, request, "metric.deleted", "metric", metric.id, {"key": metric.key})
            session.delete(metric)
        return Response(status_code=204)

    @router.get(base + "/{metric_id}/series", response_model=SeriesResponse)
    def read_series(organization_id: UUID, model_id: UUID, version_id: UUID, metric_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SeriesResponse:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            version = version_of(session, organization_id, model_id, version_id)
            metric = _metric(session, version.id, metric_id)
            _, series = series_of_version(session, version.id)
            points = [ValuePoint(period=period, value=value) for period, value in sorted(series[metric.key].items())]
            return SeriesResponse(metric=_response(metric, len(points)), points=points)

    @router.put(base + "/{metric_id}/values", response_model=SeriesResponse)
    def write_values(organization_id: UUID, model_id: UUID, version_id: UUID, metric_id: UUID, body: ValuesRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> SeriesResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            version = version_of(session, organization_id, model_id, version_id)
            metric = _metric(session, version.id, metric_id, lock=True)
            if metric.formula:
                raise HTTPException(status_code=422, detail="a derived metric has no stored values")
            wanted = {month_start(point.period): point.value for point in body.values}
            existing = {value.period: value for value in session.scalars(select(MetricValue).where(MetricValue.metric_id == metric.id, MetricValue.period.in_(list(wanted)))).all()}
            for period, value in wanted.items():
                if value is None:
                    if period in existing:
                        session.delete(existing[period])
                elif period in existing:
                    existing[period].value = value
                else:
                    session.add(MetricValue(metric_id=metric.id, period=period, organization_id=organization_id, version_id=version.id, value=value))
            session.flush()
            _audit(session, request, "metric.values_changed", "metric", metric.id, {"key": metric.key, "periods": len(wanted)})
            _, series = series_of_version(session, version.id)
            points = [ValuePoint(period=period, value=value) for period, value in sorted(series[metric.key].items())]
            return SeriesResponse(metric=_response(metric, len(points)), points=points)

    return router
