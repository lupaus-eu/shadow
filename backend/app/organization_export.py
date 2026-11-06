"""The Organization Export: one JSON file of an Organization's content for its Owner (Yearclock V2 P7, ADR-0030).

It is written piece by piece, one Yearclock at a time, so memory stays bounded
by the largest Yearclock. It leaves out Event History, the Audit Log, billing
data, and the email outbox. Only an Owner can download it, every download is
audited, and a tight hourly limit applies.
"""
import json
from collections.abc import Iterator
from datetime import date, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.audit import AuditEventDraft, record_audit_event
from app.auth import AuthenticatedUser
from app.auth_routes import AuthenticatedUserDependency
from app.database import RequestContext, apply_request_context, transaction_session
from app.exchange import file_name, require_exchange_quota
from app.limits import ORGANIZATION_EXPORTS_PER_HOUR
from app.event_content import time_text
from app.models import (
    Category, Event, EventLabel, EventSeries, Group, GroupMember, Label, Lane, Organization, OrganizationMembership, OrganizationRole, OrganizationStatus,
    SeriesLabel, SeriesOccurrence, UserAccount, Yearclock, YearclockAccessGrant, YearclockGroupGrant,
)

SCHEMA = "yearclock-export/2"
EXPORT_ACTION = "organization.export"
EXPORTABLE = (OrganizationStatus.ACTIVE.value, OrganizationStatus.PENDING_DELETION.value)


def _default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    raise TypeError(f"not serializable: {type(value).__name__}")


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=_default)


def _owner_context(session: Session, organization_id: UUID, user_account_id: UUID) -> Organization:
    """Membership and the Owner role, then the Organization context for row-level security."""
    membership = session.scalar(select(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id == user_account_id))
    if membership is None:
        raise HTTPException(status_code=404, detail="organization not found")
    if membership.role != OrganizationRole.OWNER.value:
        raise HTTPException(status_code=403, detail="owner role required")
    apply_request_context(session, RequestContext(user_account_id=user_account_id, organization_id=organization_id))
    organization = session.get(Organization, organization_id)
    if organization is None or organization.status not in EXPORTABLE:
        raise HTTPException(status_code=404, detail="organization not found")
    return organization


def _counts(session: Session, organization_id: UUID) -> dict[str, int]:
    count = lambda model, *where: session.scalar(select(func.count()).select_from(model).where(model.organization_id == organization_id, *where)) or 0
    return {
        "members": count(OrganizationMembership), "groups": count(Group), "labels": count(Label),
        "yearclocks": count(Yearclock, Yearclock.deleted_at.is_(None)), "events": count(Event, Event.deleted_at.is_(None)), "series": count(EventSeries),
    }


def _yearclock_document(session: Session, clock: Yearclock) -> dict:
    lanes = session.scalars(select(Lane).where(Lane.yearclock_id == clock.id).order_by(Lane.display_order, Lane.id)).all()
    categories = session.scalars(select(Category).where(Category.yearclock_id == clock.id).order_by(Category.display_order, Category.id)).all()
    events = session.scalars(select(Event).where(Event.yearclock_id == clock.id, Event.deleted_at.is_(None)).order_by(Event.starts_on, Event.id)).all()
    event_labels: dict[UUID, list[UUID]] = {}
    for event_id, label_id in session.execute(select(EventLabel.event_id, EventLabel.label_id).join(Event, Event.id == EventLabel.event_id).where(Event.yearclock_id == clock.id, Event.deleted_at.is_(None))).all():
        event_labels.setdefault(event_id, []).append(label_id)
    occurrences = {item.event_id: item for item in session.scalars(select(SeriesOccurrence).join(Event, Event.id == SeriesOccurrence.event_id).where(Event.yearclock_id == clock.id, Event.deleted_at.is_(None))).all()}
    series = session.scalars(select(EventSeries).where(EventSeries.yearclock_id == clock.id).order_by(EventSeries.starts_on, EventSeries.id)).all()
    series_labels: dict[UUID, list[UUID]] = {}
    for series_id, label_id in session.execute(select(SeriesLabel.series_id, SeriesLabel.label_id).join(EventSeries, EventSeries.id == SeriesLabel.series_id).where(EventSeries.yearclock_id == clock.id)).all():
        series_labels.setdefault(series_id, []).append(label_id)
    users = session.execute(select(OrganizationMembership.id, YearclockAccessGrant.role).join(YearclockAccessGrant, YearclockAccessGrant.user_account_id == OrganizationMembership.user_account_id).where(YearclockAccessGrant.yearclock_id == clock.id, OrganizationMembership.organization_id == clock.organization_id)).all()
    groups = session.execute(select(YearclockGroupGrant.group_id, YearclockGroupGrant.role).where(YearclockGroupGrant.yearclock_id == clock.id)).all()
    return {
        "id": clock.id, "name": clock.name, "display_order": clock.display_order, "start_month": clock.start_month, "show_week_ring": clock.show_week_ring, "show_quarter_ring": clock.show_quarter_ring,
        "organization_access": clock.organization_access, "archived_at": clock.archived_at,
        "lanes": [{"id": lane.id, "name": lane.name, "display_order": lane.display_order, "tint": lane.tint, "height": lane.height, "source_lane_id": lane.source_lane_id} for lane in lanes],
        "categories": [{"id": item.id, "name": item.name, "color": item.color, "display_order": item.display_order} for item in categories],
        "series": [{"id": item.id, "lane_id": item.lane_id, "category_id": item.category_id, "title": item.title, "description": item.description, "description_format": item.description_format, "location": item.location, "links": item.links or [], "starts_at": time_text(item.starts_at), "ends_at": time_text(item.ends_at), "starts_on": item.starts_on, "frequency": item.frequency, "interval": item.interval, "until": item.until, "occurrence_count": item.occurrence_count, "last_day": item.last_day, "label_ids": series_labels.get(item.id, [])} for item in series],
        "events": [{
            "id": event.id, "lane_id": event.lane_id, "category_id": event.category_id, "title": event.title, "description": event.description, "description_format": event.description_format, "location": event.location, "links": event.links or [], "starts_at": time_text(event.starts_at), "ends_at": time_text(event.ends_at),
            "starts_on": event.starts_on, "ends_on": event.ends_on, "label_ids": event_labels.get(event.id, []),
            **({"series_id": occurrences[event.id].series_id, "series_date": occurrences[event.id].series_date, "skipped": occurrences[event.id].skipped, "exception": bool(occurrences[event.id].overrides)} if event.id in occurrences else {}),
        } for event in events],
        "access": {"members": [{"membership_id": membership_id, "role": role} for membership_id, role in users], "groups": [{"group_id": group_id, "role": role} for group_id, role in groups]},
    }


def iterate_export(session: Session, organization: Organization, exported_at: datetime) -> Iterator[str]:
    """The document as JSON text pieces; each Yearclock is read, written, and dropped before the next."""
    organization_id = organization.id
    members = session.execute(select(OrganizationMembership, UserAccount).join(UserAccount, UserAccount.id == OrganizationMembership.user_account_id).where(OrganizationMembership.organization_id == organization_id).order_by(OrganizationMembership.created_at, OrganizationMembership.id)).all()
    group_members: dict[UUID, list[UUID]] = {}
    for group_id, membership_id in session.execute(select(GroupMember.group_id, GroupMember.membership_id).where(GroupMember.organization_id == organization_id)).all():
        group_members.setdefault(group_id, []).append(membership_id)
    groups = session.scalars(select(Group).where(Group.organization_id == organization_id).order_by(Group.name, Group.id)).all()
    labels = session.scalars(select(Label).where(Label.organization_id == organization_id).order_by(Label.name, Label.id)).all()
    shared_categories = session.scalars(select(Category).where(Category.organization_id == organization_id, Category.yearclock_id.is_(None)).order_by(Category.display_order, Category.id)).all()
    yield "{" + f'"schema":{_dump(SCHEMA)},"exported_at":{_dump(exported_at)},'
    yield f'"organization":{_dump({"id": organization.id, "name": organization.name, "time_zone": organization.time_zone, "default_locale": organization.default_locale, "status": organization.status})},'
    yield f'"members":{_dump([{"membership_id": membership.id, "user_account_id": account.id, "name": account.display_name, "email": account.email, "role": membership.role, "joined_at": membership.created_at} for membership, account in members])},'
    yield f'"groups":{_dump([{"id": group.id, "name": group.name, "member_ids": group_members.get(group.id, [])} for group in groups])},'
    yield f'"labels":{_dump([{"id": label.id, "name": label.name, "color": label.color} for label in labels])},'
    yield f'"organization_categories":{_dump([{"id": item.id, "name": item.name, "color": item.color, "display_order": item.display_order} for item in shared_categories])},'
    yield '"yearclocks":['
    first = True
    for clock_id in session.scalars(select(Yearclock.id).where(Yearclock.organization_id == organization_id, Yearclock.deleted_at.is_(None)).order_by(Yearclock.display_order, Yearclock.id)).all():
        clock = session.get(Yearclock, clock_id)
        yield ("" if first else ",") + _dump(_yearclock_document(session, clock))
        first = False
        session.expire_all()
    yield "]}"


def create_organization_export_router(*, session_factory: sessionmaker[Session], authenticated_user_dependency: AuthenticatedUserDependency) -> APIRouter:
    router = APIRouter(prefix="/api/v1/organizations", tags=["Export"])

    @router.get("/{organization_id}/export")
    def export_organization(organization_id: UUID, request: Request, user: AuthenticatedUser = Depends(authenticated_user_dependency)) -> StreamingResponse:
        with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as session:
            organization = _owner_context(session, organization_id, user.account.id)
            require_exchange_quota(session, user.account.id, organization_id, (EXPORT_ACTION,), ORGANIZATION_EXPORTS_PER_HOUR)
            record_audit_event(session, AuditEventDraft(action=EXPORT_ACTION, target_type="organization", target_id=organization_id, request_id=(request.headers.get("X-Request-ID") or str(uuid4()))[:120], change_summary={"schema": SCHEMA, **_counts(session, organization_id)}))
            exported_at = session.scalar(select(func.now()))
            name = file_name(organization.name, f"organization-export-{exported_at.date().isoformat()}", "json")

        def stream() -> Iterator[str]:
            with transaction_session(session_factory, RequestContext(user_account_id=user.account.id)) as inner:
                yield from iterate_export(inner, _owner_context(inner, organization_id, user.account.id), exported_at)

        return StreamingResponse(stream(), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})

    return router
