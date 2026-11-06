"""Analysis of a simulation and its action proposals (Shadow feature 5).

``GET`` returns the findings per metric and the stored proposals; ``POST`` (re)generates the
proposals: new ones are added, ones nobody has acted on any more are removed, and accepted or
dismissed ones are kept as they are. ``compare_to`` names a second simulation of the same Model
(for example one of the baseline) that the findings are compared against.
"""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from uuid import uuid4

from app.analysis import analyze
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.model_routes import _audit, _editor_session, _member_session, _model, _stale
from app.models import Metric, Recommendation, Simulation
from app.simulation_routes import SimulationResponse, _response, result_of


class FindingResponse(BaseModel):
    key: str
    name: str
    unit: str | None
    derived: bool
    start: float | None
    end: float | None
    change_pct: float | None
    trend: str
    turns_negative: date | None
    band_ratio: float | None
    versus: float | None


class RecommendationResponse(BaseModel):
    id: UUID
    kind: str
    severity: str
    metric_key: str
    title: str
    rationale: str
    status: str
    version: int


class AnalysisResponse(BaseModel):
    simulation: SimulationResponse
    compared_to: SimulationResponse | None
    findings: list[FindingResponse]
    recommendations: list[RecommendationResponse]


class StatusUpdate(BaseModel):
    status: Literal["proposed", "accepted", "dismissed"]
    expected_version: int


def _simulation(session: Session, model_id: UUID, simulation_id: UUID) -> Simulation:
    simulation = session.scalar(select(Simulation).where(Simulation.id == simulation_id, Simulation.model_id == model_id))
    if simulation is None:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return simulation


def _build(session: Session, simulation: Simulation, other: Simulation | None):
    formulas = {metric.key: metric.formula for metric in session.scalars(select(Metric).where(Metric.version_id == simulation.version_id)).all() if metric.formula}
    return analyze(result_of(session, simulation), formulas, result_of(session, other) if other else None)


def _stored(session: Session, simulation: Simulation) -> list[RecommendationResponse]:
    order = {"high": 0, "medium": 1, "low": 2}
    rows = session.scalars(select(Recommendation).where(Recommendation.simulation_id == simulation.id)).all()
    return [RecommendationResponse.model_validate(row, from_attributes=True) for row in sorted(rows, key=lambda row: (order[row.severity], row.metric_key, row.kind))]


def create_analysis_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Analysis"])
    base = "/{organization_id}/models/{model_id}/simulations/{simulation_id}"

    @router.get(base + "/analysis", response_model=AnalysisResponse)
    def read(organization_id: UUID, model_id: UUID, simulation_id: UUID, compare_to: UUID | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> AnalysisResponse:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            simulation = _simulation(session, model_id, simulation_id)
            other = _simulation(session, model_id, compare_to) if compare_to else None
            analysis = _build(session, simulation, other)
            return AnalysisResponse(simulation=_response(simulation), compared_to=_response(other) if other else None, findings=[FindingResponse(**vars(item)) for item in analysis.findings], recommendations=_stored(session, simulation))

    @router.post(base + "/analysis", response_model=AnalysisResponse)
    def generate(organization_id: UUID, model_id: UUID, simulation_id: UUID, request: Request, compare_to: UUID | None = None, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> AnalysisResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            _model(session, organization_id, model_id)
            simulation = _simulation(session, model_id, simulation_id)
            other = _simulation(session, model_id, compare_to) if compare_to else None
            analysis = _build(session, simulation, other)
            existing = {(row.kind, row.metric_key): row for row in session.scalars(select(Recommendation).where(Recommendation.simulation_id == simulation.id)).all()}
            wanted = {(item.kind, item.metric_key): item for item in analysis.proposals}
            for key, row in existing.items():
                if key not in wanted and row.status == "proposed":
                    session.delete(row)
            for key, item in wanted.items():
                if key in existing:
                    if existing[key].status == "proposed":
                        existing[key].severity, existing[key].title, existing[key].rationale = item.severity, item.title, item.rationale
                    continue
                session.add(Recommendation(id=uuid4(), organization_id=organization_id, simulation_id=simulation.id, kind=item.kind, severity=item.severity, metric_key=item.metric_key, title=item.title, rationale=item.rationale))
            session.flush()
            _audit(session, request, "analysis.generated", "simulation", simulation.id, {"proposals": len(wanted)})
            return AnalysisResponse(simulation=_response(simulation), compared_to=_response(other) if other else None, findings=[FindingResponse(**vars(item)) for item in analysis.findings], recommendations=_stored(session, simulation))

    @router.patch(base + "/recommendations/{recommendation_id}", response_model=RecommendationResponse)
    def decide(organization_id: UUID, model_id: UUID, simulation_id: UUID, recommendation_id: UUID, body: StatusUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> RecommendationResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            _model(session, organization_id, model_id)
            row = session.scalar(select(Recommendation).where(Recommendation.id == recommendation_id, Recommendation.simulation_id == simulation_id).with_for_update())
            if row is None:
                raise HTTPException(status_code=404, detail="Recommendation not found")
            _stale(row.version, body.expected_version)
            row.status = body.status
            row.version += 1
            _audit(session, request, "recommendation.decided", "recommendation", row.id, {"status": body.status, "kind": row.kind, "metric": row.metric_key})
            return RecommendationResponse.model_validate(row, from_attributes=True)

    return router
