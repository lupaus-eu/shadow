"""Organization-wide Labels (Yearclock V2, P2; `.scratch/yearclock-v2-classification/`).

Every member can read the Label set. Editors of any Yearclock, Admins, and
Owners can create a Label (creating an existing name returns it, so inline
creation is idempotent). Only Owners and Admins rename, recolor, merge, or
delete, and merge and delete need an explicit confirmation that is first
answered with the usage count.
"""

from contextlib import contextmanager
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.access import edits_any_yearclock
from app.revisions import mark_changed
from app.event_labels import label_usage, move_label_assignments, rewrite_override_labels, touch_events_with_label
from app.limits import require_label_capacity
from app.models import EventLabel, Label, OrganizationMembership, OrganizationRole, Yearclock
from app.subscription_access import require_organization_mutation_access

# Distinct, WCAG-contrasting hues for Label swatches; text is always shown beside the swatch.
LABEL_COLORS = (
    "#1f5f99", "#2e7d32", "#8e24aa", "#c62828", "#ef6c00", "#00838f",
    "#5d4037", "#455a64", "#ad1457", "#283593", "#827717", "#6a1b9a",
)
MANAGERS = {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}


class LabelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    color: str

    @field_validator("name")
    @classmethod
    def trimmed(cls, value: str) -> str:
        if not (value := " ".join(value.split())):
            raise ValueError("must not be blank")
        return value

    @field_validator("color")
    @classmethod
    def from_palette(cls, value: str) -> str:
        if value.lower() not in LABEL_COLORS:
            raise ValueError("color must come from the Label palette")
        return value.lower()


class LabelUpdate(LabelRequest):
    expected_version: int = Field(ge=1)


class LabelMerge(BaseModel):
    into_label_id: UUID
    expected_version: int = Field(ge=1)
    confirm: bool = False


class LabelResponse(BaseModel):
    id: UUID
    name: str
    color: str
    version: int
    usage: int


def labels_of(session_factory: sessionmaker[Session], organization_id: UUID, user: AuthenticatedUser) -> list[LabelResponse]:
    with _member_session(session_factory, organization_id, user) as (session, _membership):
        usage = label_usage(session, organization_id)
        labels = session.scalars(select(Label).where(Label.organization_id == organization_id).order_by(func.lower(Label.name))).all()
        return [_response(label, usage) for label in labels]

def create_label_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Labels"])

    @router.get("/{organization_id}/labels", response_model=list[LabelResponse])
    def list_labels(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[LabelResponse]:
        return labels_of(session_factory, organization_id, user)
    @router.post("/{organization_id}/labels", response_model=LabelResponse, status_code=201)
    def create(organization_id: UUID, body: LabelRequest, request: Request, response: Response, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LabelResponse:
        with _member_session(session_factory, organization_id, user) as (session, membership):
            if membership.role not in MANAGERS and not _edits_any_yearclock(session, membership):
                raise HTTPException(status_code=403, detail="Editor, Admin, or Owner required")
            require_organization_mutation_access(session, organization_id)
            existing = _by_name(session, organization_id, body.name)
            if existing is not None:
                response.status_code = 200
                return _response(existing, label_usage(session, organization_id))
            require_label_capacity(session, organization_id)
            label = Label(id=uuid4(), organization_id=organization_id, name=body.name, color=body.color, version=1)
            session.add(label)
            session.flush()
            _audit(session, request, "label.created", label.id, {"name": label.name, "color": label.color})
            return _response(label, {})

    @router.patch("/{organization_id}/labels/{label_id}", response_model=LabelResponse)
    def update(organization_id: UUID, label_id: UUID, body: LabelUpdate, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LabelResponse:
        with _manager_session(session_factory, organization_id, user) as session:
            label = _locked(session, organization_id, label_id, body.expected_version)
            duplicate = _by_name(session, organization_id, body.name)
            if duplicate is not None and duplicate.id != label.id:
                raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})
            changes = {key: value for key, value in (("name", body.name), ("color", body.color)) if getattr(label, key) != value}
            label.name, label.color = body.name, body.color
            label.version += 1
            _audit(session, request, "label.updated", label.id, changes)
            return _response(label, label_usage(session, organization_id))

    @router.post("/{organization_id}/labels/{label_id}/merge", response_model=LabelResponse)
    def merge(organization_id: UUID, label_id: UUID, body: LabelMerge, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> LabelResponse:
        with _manager_session(session_factory, organization_id, user) as session:
            if body.into_label_id == label_id:
                raise HTTPException(status_code=422, detail="a Label cannot be merged into itself")
            source = _locked(session, organization_id, label_id, body.expected_version)
            target = session.scalar(select(Label).where(Label.id == body.into_label_id, Label.organization_id == organization_id).with_for_update())
            if target is None:
                raise HTTPException(status_code=422, detail="target Label not found")
            affected = label_usage(session, organization_id).get(source.id, 0)
            if not body.confirm:
                raise HTTPException(status_code=409, detail={"reason": "confirmation_required", "usage": affected})
            mark_changed(session, session.scalars(select(EventLabel.event_id).where(EventLabel.label_id == source.id)).all(), "label_merged", {"from": source.name, "into": target.name})
            touch_events_with_label(session, source.id)
            move_label_assignments(session, source.id, target.id)
            session.delete(source)
            target.version += 1
            _audit(session, request, "label.merged", target.id, {"from": source.name, "into": target.name, "affected_events": affected})
            session.flush()
            return _response(target, label_usage(session, organization_id))

    @router.delete("/{organization_id}/labels/{label_id}", status_code=204)
    def delete(organization_id: UUID, label_id: UUID, request: Request, expected_version: int = Query(ge=1), confirm: bool = Query(False), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        with _manager_session(session_factory, organization_id, user) as session:
            label = _locked(session, organization_id, label_id, expected_version)
            affected = label_usage(session, organization_id).get(label.id, 0)
            if not confirm:
                raise HTTPException(status_code=409, detail={"reason": "confirmation_required", "usage": affected})
            mark_changed(session, session.scalars(select(EventLabel.event_id).where(EventLabel.label_id == label.id)).all(), "label_deleted", {"name": label.name})
            touch_events_with_label(session, label.id)
            rewrite_override_labels(session, label.id, None)
            session.delete(label)
            _audit(session, request, "label.deleted", label.id, {"name": label.name, "affected_events": affected})

    return router


@contextmanager
def _member_session(session_factory: sessionmaker, organization_id: UUID, user: AuthenticatedUser):
    with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None:
            raise HTTPException(status_code=404, detail="Organization not found")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        yield session, membership


@contextmanager
def _manager_session(session_factory: sessionmaker, organization_id: UUID, user: AuthenticatedUser):
    with _member_session(session_factory, organization_id, user) as (session, membership):
        if membership.role not in MANAGERS:
            raise HTTPException(status_code=403, detail="Owner or Admin required")
        require_organization_mutation_access(session, organization_id)
        yield session


def _edits_any_yearclock(session: Session, membership: OrganizationMembership) -> bool:
    return edits_any_yearclock(session, membership)


def _by_name(session: Session, organization_id: UUID, name: str) -> Label | None:
    return session.scalar(select(Label).where(Label.organization_id == organization_id, func.lower(Label.name) == name.lower()))


def _locked(session: Session, organization_id: UUID, label_id: UUID, expected_version: int) -> Label:
    label = session.scalar(select(Label).where(Label.id == label_id, Label.organization_id == organization_id).with_for_update())
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")
    if label.version != expected_version:
        raise HTTPException(status_code=409, detail={"latest_version": label.version})
    return label


def _response(label: Label, usage: dict[UUID, int]) -> LabelResponse:
    return LabelResponse(id=label.id, name=label.name, color=label.color, version=label.version, usage=usage.get(label.id, 0))


def _audit(session: Session, request: Request, action: str, target_id: UUID, summary: dict) -> None:
    record_audit_event(session, AuditEventDraft(action=action, target_type="label", target_id=target_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary=summary))
