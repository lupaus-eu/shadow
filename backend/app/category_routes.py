from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from app.limits import require_category_capacity, require_organization_category_capacity
from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.models import Category, Event, EventSeries, OrganizationMembership, OrganizationRole, SeriesOccurrence, Yearclock
from app.lifecycle import live_yearclock
from app.access import role_on
from app.revisions import set_revision_reason
from app.yearclock_reading import readable_links
from app.subscription_access import require_organization_mutation_access

class CategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    color: str | None = None
    expected_version: int | None = None
    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not (value := value.strip()): raise ValueError("must not be blank")
        return value
    @field_validator("color")
    @classmethod
    def valid_color(cls, value: str | None) -> str | None:
        if value is not None and (len(value) != 7 or not value.startswith("#") or any(char not in "0123456789abcdefABCDEF" for char in value[1:])): raise ValueError("must be a #RRGGBB color")
        return value
class CategoryResponse(BaseModel):
    id: UUID; name: str; color: str | None; display_order: int; version: int; scope: str = "yearclock"; usage: int | None = None
    source_yearclock_id: UUID | None = None; source_yearclock_name: str | None = None
class CategoryOrderRequest(BaseModel): ordered_ids: list[UUID]; expected_versions: dict[UUID, int]

def categories_of(session_factory: sessionmaker[Session], organization_id: UUID, yearclock_id: UUID, user: AuthenticatedUser) -> list[CategoryResponse]:
    with _session(session_factory, organization_id, yearclock_id, user, mutate=False) as session:
        own = [_response(x) for x in session.scalars(select(Category).where(Category.organization_id == organization_id, Category.yearclock_id.is_(None)).order_by(Category.display_order, Category.id)).all()] + [_response(x) for x in session.scalars(select(Category).where(Category.yearclock_id == yearclock_id).order_by(Category.display_order)).all()]
        # Readable Linked Lanes bring their source Yearclocks' own Categories, as read-only colours and filters.
        sources = {source_clock for _, source_clock in readable_links(session, organization_id, yearclock_id, user.account.id).values()}
        names = dict(session.execute(select(Yearclock.id, Yearclock.name).where(Yearclock.id.in_(sources))).all()) if sources else {}
        linked = session.scalars(select(Category).where(Category.yearclock_id.in_(sources)).order_by(Category.yearclock_id, Category.display_order)).all() if sources else []
        return own + [_response(x).model_copy(update={"scope": "linked", "source_yearclock_id": x.yearclock_id, "source_yearclock_name": names.get(x.yearclock_id)}) for x in linked]

def create_category_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Categories"])
    @router.get("/{organization_id}/yearclocks/{yearclock_id}/categories", response_model=list[CategoryResponse])
    def list_categories(organization_id: UUID, yearclock_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[CategoryResponse]:
        return categories_of(session_factory, organization_id, yearclock_id, user)
    @router.post("/{organization_id}/yearclocks/{yearclock_id}/categories", response_model=CategoryResponse, status_code=201)
    def create(organization_id: UUID, yearclock_id: UUID, body: CategoryRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> CategoryResponse:
        with _session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            require_category_capacity(session, yearclock_id)
            item = Category(id=uuid4(), organization_id=organization_id, yearclock_id=yearclock_id, name=body.name, color=body.color, display_order=session.scalar(select(func.count()).select_from(Category).where(Category.yearclock_id == yearclock_id)) or 0, version=1); session.add(item); _audit(session, request, "category.created", item.id, {"scope": "yearclock"}); return _response(item)
    @router.patch("/{organization_id}/yearclocks/{yearclock_id}/categories/{category_id}", response_model=CategoryResponse)
    def update(organization_id: UUID, yearclock_id: UUID, category_id: UUID, body: CategoryRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> CategoryResponse:
        with _session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            item = session.get(Category, category_id)
            if item is None or item.yearclock_id != yearclock_id: raise HTTPException(status_code=404, detail="Category not found")
            if body.expected_version != item.version: raise HTTPException(status_code=409, detail={"latest_version": item.version})
            item.name = body.name; item.color = body.color; item.version += 1; _audit(session, request, "category.updated", item.id, {"name": item.name, "color": item.color, "scope": "yearclock"}); return _response(item)
    @router.put("/{organization_id}/yearclocks/{yearclock_id}/categories/order", response_model=list[CategoryResponse])
    def reorder(organization_id: UUID, yearclock_id: UUID, body: CategoryOrderRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[CategoryResponse]:
        with _session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            items = session.scalars(select(Category).where(Category.yearclock_id == yearclock_id).with_for_update()).all()
            if len(body.ordered_ids) != len(set(body.ordered_ids)) or set(body.ordered_ids) != {item.id for item in items}: raise HTTPException(status_code=422, detail="ordered_ids must contain every Category once")
            by_id = {item.id: item for item in items}
            stale = {str(item.id): item.version for item in items if body.expected_versions.get(item.id) != item.version}
            if stale: raise HTTPException(status_code=409, detail={"latest_versions": stale})
            for index, item_id in enumerate(body.ordered_ids): by_id[item_id].display_order = index; by_id[item_id].version += 1
            if not body.ordered_ids: return []
            _audit(session, request, "category.reordered", body.ordered_ids[0], {"ordered_ids": [str(item) for item in body.ordered_ids]}); return [_response(by_id[item_id]) for item_id in body.ordered_ids]
    @router.delete("/{organization_id}/yearclocks/{yearclock_id}/categories/{category_id}", status_code=204)
    def delete(organization_id: UUID, yearclock_id: UUID, category_id: UUID, request: Request, expected_version: int = Query(ge=1), confirm: bool = Query(False), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        if not confirm: raise HTTPException(status_code=400, detail="category deletion requires confirmation")
        with _session(session_factory, organization_id, yearclock_id, user, mutate=True) as session:
            item = session.get(Category, category_id)
            if item is None or item.yearclock_id != yearclock_id: raise HTTPException(status_code=404, detail="Category not found")
            if expected_version != item.version: raise HTTPException(status_code=409, detail={"latest_version": item.version})
            affected = session.scalars(select(Event).where(Event.category_id == category_id)).all()
            set_revision_reason(session, "category_deleted", {"name": item.name})
            for event in affected: event.category_id = None; event.version += 1
            for series in session.scalars(select(EventSeries).where(EventSeries.category_id == category_id)).all(): series.category_id = None
            session.delete(item); _audit(session, request, "category.removed", item.id, {"uncategorized_events": len(affected), "scope": "yearclock"})
    return router
from contextlib import contextmanager
@contextmanager
def _session(factory: sessionmaker[Session], organization_id: UUID, yearclock_id: UUID, user: AuthenticatedUser, *, mutate: bool):
    with transaction_session(factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None: raise HTTPException(status_code=404, detail="Yearclock not found")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        if mutate:
            require_organization_mutation_access(session, organization_id)
        live_yearclock(session, organization_id, yearclock_id)
        role = role_on(session, membership, yearclock_id)
        if role is None or (mutate and role != "editor"): raise HTTPException(status_code=403, detail="Editor access required")
        yield session
def _response(item: Category, usage: int | None = None) -> CategoryResponse: return CategoryResponse(id=item.id, name=item.name, color=item.color, display_order=item.display_order, version=item.version, scope="organization" if item.yearclock_id is None else "yearclock", usage=usage)
def _audit(session: Session, request: Request, action: str, target: UUID, summary: dict) -> None: record_audit_event(session, AuditEventDraft(action=action, target_type="category", target_id=target, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary=summary))



def create_organization_category_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    """Organization Categories (Yearclock V2): every member reads them; Owners and Admins manage them."""
    router = APIRouter(prefix="/api/v1/organizations", tags=["Categories"])

    @router.get("/{organization_id}/categories", response_model=list[CategoryResponse])
    def list_organization_categories(organization_id: UUID, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[CategoryResponse]:
        with _organization_session(session_factory, organization_id, user, manage=False) as session:
            usage = _category_usage(session, organization_id)
            return [_response(item, usage.get(item.id, 0)) for item in _organization_categories(session, organization_id)]

    @router.post("/{organization_id}/categories", response_model=CategoryResponse, status_code=201)
    def create_organization_category(organization_id: UUID, body: CategoryRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> CategoryResponse:
        with _organization_session(session_factory, organization_id, user, manage=True) as session:
            require_organization_category_capacity(session, organization_id)
            _refuse_duplicate(session, organization_id, body.name, None)
            item = Category(id=uuid4(), organization_id=organization_id, yearclock_id=None, name=body.name, color=body.color, display_order=len(_organization_categories(session, organization_id)), version=1)
            session.add(item)
            session.flush()
            _audit(session, request, "category.created", item.id, {"name": item.name, "scope": "organization"})
            return _response(item, 0)

    @router.patch("/{organization_id}/categories/{category_id}", response_model=CategoryResponse)
    def update_organization_category(organization_id: UUID, category_id: UUID, body: CategoryRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> CategoryResponse:
        with _organization_session(session_factory, organization_id, user, manage=True) as session:
            item = _organization_category(session, organization_id, category_id)
            if body.expected_version != item.version: raise HTTPException(status_code=409, detail={"latest_version": item.version})
            _refuse_duplicate(session, organization_id, body.name, item.id)
            item.name = body.name; item.color = body.color; item.version += 1
            _audit(session, request, "category.updated", item.id, {"name": item.name, "color": item.color, "scope": "organization"})
            return _response(item, _category_usage(session, organization_id).get(item.id, 0))

    @router.put("/{organization_id}/categories/order", response_model=list[CategoryResponse])
    def reorder_organization_categories(organization_id: UUID, body: CategoryOrderRequest, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> list[CategoryResponse]:
        with _organization_session(session_factory, organization_id, user, manage=True) as session:
            items = _organization_categories(session, organization_id, lock=True)
            if len(body.ordered_ids) != len(set(body.ordered_ids)) or set(body.ordered_ids) != {item.id for item in items}: raise HTTPException(status_code=422, detail="ordered_ids must contain every Organization Category once")
            stale = {str(item.id): item.version for item in items if body.expected_versions.get(item.id) != item.version}
            if stale: raise HTTPException(status_code=409, detail={"latest_versions": stale})
            by_id = {item.id: item for item in items}
            for index, item_id in enumerate(body.ordered_ids): by_id[item_id].display_order = index; by_id[item_id].version += 1
            if body.ordered_ids: _audit(session, request, "category.reordered", body.ordered_ids[0], {"ordered_ids": [str(item) for item in body.ordered_ids], "scope": "organization"})
            usage = _category_usage(session, organization_id)
            return [_response(by_id[item_id], usage.get(item_id, 0)) for item_id in body.ordered_ids]

    @router.delete("/{organization_id}/categories/{category_id}", status_code=204)
    def delete_organization_category(organization_id: UUID, category_id: UUID, request: Request, expected_version: int = Query(ge=1), confirm: bool = Query(False), user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> None:
        with _organization_session(session_factory, organization_id, user, manage=True) as session:
            item = _organization_category(session, organization_id, category_id)
            if expected_version != item.version: raise HTTPException(status_code=409, detail={"latest_version": item.version})
            affected = session.scalars(select(Event).where(Event.category_id == category_id).with_for_update()).all()
            if not confirm: raise HTTPException(status_code=409, detail={"reason": "confirmation_required", "usage": len(affected)})
            set_revision_reason(session, "category_deleted", {"name": item.name})
            for event in affected: event.category_id = None; event.version += 1
            for series in session.scalars(select(EventSeries).where(EventSeries.category_id == category_id)).all(): series.category_id = None
            _clear_category_overrides(session, category_id)
            session.delete(item)
            _audit(session, request, "category.removed", item.id, {"name": item.name, "uncategorized_events": len(affected), "scope": "organization"})

    return router


@contextmanager
def _organization_session(factory: sessionmaker[Session], organization_id: UUID, user: AuthenticatedUser, *, manage: bool):
    with transaction_session(factory, RequestContext(user_account_id=user.account.id)) as session:
        membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user.account.id))
        if membership is None: raise HTTPException(status_code=404, detail="Organization not found")
        apply_request_context(session, RequestContext(user_account_id=user.account.id, organization_id=organization_id))
        if manage:
            if membership.role not in {OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value}: raise HTTPException(status_code=403, detail="Owner or Admin required")
            require_organization_mutation_access(session, organization_id)
        yield session


def _organization_categories(session: Session, organization_id: UUID, *, lock: bool = False) -> list[Category]:
    statement = select(Category).where(Category.organization_id == organization_id, Category.yearclock_id.is_(None)).order_by(Category.display_order, Category.id)
    return list(session.scalars(statement.with_for_update() if lock else statement).all())


def _organization_category(session: Session, organization_id: UUID, category_id: UUID) -> Category:
    item = session.scalar(select(Category).where(Category.id == category_id, Category.organization_id == organization_id, Category.yearclock_id.is_(None)).with_for_update())
    if item is None: raise HTTPException(status_code=404, detail="Category not found")
    return item


def _refuse_duplicate(session: Session, organization_id: UUID, name: str, own_id: UUID | None) -> None:
    other = session.scalar(select(Category.id).where(Category.organization_id == organization_id, Category.yearclock_id.is_(None), func.lower(Category.name) == name.lower()))
    if other is not None and other != own_id: raise HTTPException(status_code=409, detail={"reason": "duplicate_name"})


def _category_usage(session: Session, organization_id: UUID) -> dict[UUID, int]:
    rows = session.execute(select(Event.category_id, func.count()).where(Event.organization_id == organization_id, Event.category_id.is_not(None)).group_by(Event.category_id)).all()
    return {category_id: count for category_id, count in rows}


def _clear_category_overrides(session: Session, category_id: UUID) -> None:
    """Occurrences that overrode their Category to this one now override it to none."""
    for occurrence in session.scalars(select(SeriesOccurrence).where(SeriesOccurrence.overrides["category_id"].astext == str(category_id))).all():
        occurrence.overrides = {**occurrence.overrides, "category_id": None}
