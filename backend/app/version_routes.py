"""Model versions: the baseline and the versions forked from it (Shadow feature 2), until the line picker replaces them.

A version has a line of the same id (ADR-0048): the baseline is the Base line and a fork is a Scenario line that
branches from its base line's last event, so it shows the base's graph and gets its metrics copied. Graphs are
edited as events (``timeline_edit_routes``); the old ``nodes`` and ``connections`` tables no longer change, which
is why the changes and merge routes of ADR-0045 are gone (ADR-0050 replaces merge; ticket 08 retires the rest).
Every member can create and edit versions; Owners and Admins delete them. The baseline cannot be deleted.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.model_routes import (
    MANAGERS,
    VersionResponse,
    _audit,
    _editor_session,
    _manager_session,
    _member_session,
    _model,
    _stale,
    _latest_state,
    _today_in_organization,
    baseline_of,
    version_of,
)
from app.metric_routes import copy_metrics
from app.models import Metric, ModelLine, ModelVersion, TimelineEvent
from app.timeline.loader import load_timeline


class VersionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    base_version_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if not (value := " ".join(value.split())):
            raise ValueError("must not be blank")
        return value


class VersionUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    expected_version: int = Field(ge=1)


def _fork_line(session: Session, base: ModelVersion, fork: ModelVersion, created_by: UUID | None) -> None:
    """Give the new version a Scenario line of the same id, branching from the base line's last event.

    A base line without an event first gets an empty "Initial situation" event dated today (a Scenario must
    branch from an event). The Scenario has no events yet, so it is dated on or after its branch event by
    construction.
    """
    if session.get(ModelLine, base.id) is None:  # a version made before lines existed cannot be forked
        raise HTTPException(status_code=409, detail={"reason": "no_line"})
    branch = session.scalars(select(TimelineEvent).where(TimelineEvent.line_id == base.id).order_by(TimelineEvent.occurred_on.desc(), TimelineEvent.seq.desc()).limit(1)).first()
    if branch is None:
        branch = TimelineEvent(id=uuid4(), organization_id=base.organization_id, model_id=base.model_id, line_id=base.id, occurred_on=_today_in_organization(session, base.organization_id), title="Initial situation", created_by_user_account_id=created_by)
        session.add(branch)
        session.flush()
    session.add(ModelLine(id=fork.id, organization_id=fork.organization_id, model_id=fork.model_id, name=fork.name, description=fork.description, kind="scenario", parent_line_id=base.id, branch_event_id=branch.id, created_by_user_account_id=created_by, version=1))
    session.flush()


def fork_version(session: Session, base: ModelVersion, name: str, description: str | None, created_by: UUID | None = None) -> ModelVersion:
    """A new version with its Scenario line, which starts from the base line's last event and gets the base's metrics."""
    fork = ModelVersion(id=uuid4(), organization_id=base.organization_id, model_id=base.model_id, name=name, description=description, is_baseline=False, base_version_id=base.id, version=1)
    session.add(fork)
    session.flush()
    _fork_line(session, base, fork, created_by)
    # Element ids are the same in every line, so a metric keeps the node it is tied to, if the base's graph still has it.
    present = _latest_state(load_timeline(session, base.model_id), base.id)[0].nodes
    linked = set(session.scalars(select(Metric.node_id).where(Metric.line_id == base.id, Metric.node_id.is_not(None))))
    copy_metrics(session, base.id, fork.id, {node_id: node_id for node_id in linked if node_id in present})
    return fork


def create_version_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Versions"])

    @router.get("/{organization_id}/models/{model_id}/versions", response_model=list[VersionResponse])
    def list_versions(organization_id: UUID, model_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[VersionResponse]:
        with _member_session(session_factory, organization_id, user) as (session, _membership):
            _model(session, organization_id, model_id)
            versions = session.scalars(select(ModelVersion).where(ModelVersion.model_id == model_id).order_by(ModelVersion.is_baseline.desc(), ModelVersion.created_at)).all()
            return [VersionResponse.model_validate(item, from_attributes=True) for item in versions]

    @router.post("/{organization_id}/models/{model_id}/versions", response_model=VersionResponse, status_code=201)
    def create_version(organization_id: UUID, model_id: UUID, body: VersionRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> VersionResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            model = _model(session, organization_id, model_id)
            base = version_of(session, organization_id, model.id, body.base_version_id)
            if session.scalar(select(ModelVersion.id).where(ModelVersion.model_id == model.id, func.lower(ModelVersion.name) == body.name.lower())) is not None:
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            fork = fork_version(session, base, body.name, body.description, user.account.id)
            _audit(session, request, "version.created", "model_version", fork.id, {"model_id": str(model.id), "name": fork.name, "base": base.name})
            return VersionResponse.model_validate(fork, from_attributes=True)

    @router.patch("/{organization_id}/models/{model_id}/versions/{version_id}", response_model=VersionResponse)
    def update_version(organization_id: UUID, model_id: UUID, version_id: UUID, body: VersionUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> VersionResponse:
        with _editor_session(session_factory, organization_id, user) as session:
            version = version_of(session, organization_id, model_id, version_id, lock=True)
            _stale(version.version, body.expected_version)
            if version.is_baseline and body.name.lower() != version.name.lower():
                raise HTTPException(status_code=422, detail="the baseline keeps its name")
            duplicate = session.scalar(select(ModelVersion.id).where(ModelVersion.model_id == model_id, func.lower(ModelVersion.name) == body.name.lower(), ModelVersion.id != version.id))
            if duplicate is not None:
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            changes = {key: value for key, value in (("name", body.name), ("description", body.description)) if getattr(version, key) != value}
            version.name, version.description = body.name, body.description
            version.version += 1
            if (line := session.get(ModelLine, version.id)) is not None:
                line.name, line.description = body.name, body.description
            _audit(session, request, "version.updated", "model_version", version.id, changes)
            return VersionResponse.model_validate(version, from_attributes=True)

    @router.delete("/{organization_id}/models/{model_id}/versions/{version_id}", status_code=204)
    def delete_version(organization_id: UUID, model_id: UUID, version_id: UUID, expected_version: int, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> Response:
        with _manager_session(session_factory, organization_id, user) as session:
            version = version_of(session, organization_id, model_id, version_id, lock=True)
            if version.is_baseline:
                raise HTTPException(status_code=422, detail="the baseline cannot be deleted")
            _stale(version.version, expected_version)
            if session.scalar(select(ModelVersion.id).where(ModelVersion.base_version_id == version.id)) is not None:
                raise HTTPException(status_code=409, detail={"reason": "has_forks"})
            _audit(session, request, "version.deleted", "model_version", version.id, {"name": version.name})
            session.flush()
            if (line := session.get(ModelLine, version.id)) is not None:
                session.delete(line)  # takes its metrics, values, simulations, events and positions with it
            session.delete(version)
        return Response(status_code=204)

    return router


__all__ = ["MANAGERS", "baseline_of", "create_version_router", "fork_version"]
