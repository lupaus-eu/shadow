"""Recoverable deletion and purge of Yearclock content (docs/architecture/lifecycle-defaults.md)."""

import os
from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.audit import AuditEventDraft, record_audit_event
from app.notifications import elevated
from app.database import RequestContext, apply_request_context
from app.models import (
    Notification,
    NotificationPreference,
    AuditEvent,
    BackgroundJob,
    Category,
    Event,
    EventSeries,
    Label,
    Lane,
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    OrganizationStatus,
    OutboxMessage,
    SeriesOccurrence,
    SupportAccessRequest,
    Yearclock,
    YearclockAccessGrant,
)


def content_retention() -> timedelta:
    """How long deleted Events and Yearclocks stay recoverable."""
    return timedelta(days=int(os.getenv("DELETED_CONTENT_RETENTION_DAYS", "30")))


def organization_deletion_window() -> timedelta:
    """How long a Pending Deletion Organization stays restorable before purge."""
    return timedelta(days=int(os.getenv("ORGANIZATION_DELETION_RETENTION_DAYS", "30")))


def organization_purge_after(organization: Organization) -> datetime | None:
    if organization.status != OrganizationStatus.PENDING_DELETION.value or organization.deletion_requested_at is None:
        return None
    return organization.deletion_requested_at + organization_deletion_window()


def live_yearclock(session: Session, organization_id: UUID, yearclock_id: UUID, *, lock: bool = False) -> Yearclock:
    """The route Yearclock when it belongs to the Organization and is not deleted; otherwise 404."""
    statement = select(Yearclock).where(Yearclock.id == yearclock_id, Yearclock.organization_id == organization_id, Yearclock.deleted_at.is_(None))
    yearclock = session.scalar(statement.with_for_update() if lock else statement)
    if yearclock is None:
        raise HTTPException(status_code=404, detail="Yearclock not found")
    return yearclock


def purge_yearclock(session: Session, yearclock_id: UUID) -> None:
    """Hard-delete a Yearclock and everything it contains, children first."""
    event_ids = select(Event.id).where(Event.yearclock_id == yearclock_id)
    session.execute(delete(SeriesOccurrence).where(SeriesOccurrence.event_id.in_(event_ids)))
    session.execute(delete(Event).where(Event.yearclock_id == yearclock_id))
    session.execute(delete(EventSeries).where(EventSeries.yearclock_id == yearclock_id))
    session.execute(delete(Category).where(Category.yearclock_id == yearclock_id))
    session.execute(delete(YearclockAccessGrant).where(YearclockAccessGrant.yearclock_id == yearclock_id))
    session.execute(delete(Lane).where(Lane.yearclock_id == yearclock_id))
    session.execute(delete(Yearclock).where(Yearclock.id == yearclock_id))


def purge_deleted_content(session: Session, job: BackgroundJob, now: datetime) -> None:
    """Idempotently purge Events and Yearclocks deleted longer ago than the retention period."""
    cutoff = now - content_retention()
    organization_id = job.organization_id
    request_id = f"job:{job.id}"
    for yearclock in session.scalars(select(Yearclock).where(Yearclock.organization_id == organization_id, Yearclock.deleted_at.is_not(None), Yearclock.deleted_at <= cutoff)).all():
        purge_yearclock(session, yearclock.id)
        record_audit_event(session, AuditEventDraft(action="yearclock.purged", target_type="yearclock", target_id=yearclock.id, request_id=request_id, change_summary={}))
    for event in session.scalars(select(Event).where(Event.organization_id == organization_id, Event.deleted_at.is_not(None), Event.deleted_at <= cutoff)).all():
        session.delete(event)
        record_audit_event(session, AuditEventDraft(action="event.purged", target_type="event", target_id=event.id, request_id=request_id, change_summary={}))


def purge_organization(session: Session, job: BackgroundJob, now: datetime) -> None:
    """Purge a Pending Deletion Organization whose window has ended; a no-op otherwise.

    Removes Yearclocks with all content, Labels, memberships, invitations, Support
    Access requests, and queued email payloads, and empties audit change
    summaries. The Organization row (billing identity and Stripe ids) and the
    audit trail of actions remain as Billing Record and deletion evidence.
    """
    organization_id = job.organization_id
    apply_request_context(session, RequestContext(organization_id=organization_id, worker_scope="purge"))
    organization = session.scalar(select(Organization).where(Organization.id == organization_id).with_for_update())
    purge_after = organization_purge_after(organization) if organization else None
    if purge_after is None or purge_after > now:
        return
    for yearclock_id in session.scalars(select(Yearclock.id).where(Yearclock.organization_id == organization_id)).all():
        purge_yearclock(session, yearclock_id)
    session.execute(delete(Label).where(Label.organization_id == organization_id))
    session.execute(delete(Category).where(Category.organization_id == organization_id))
    session.execute(delete(SupportAccessRequest).where(SupportAccessRequest.organization_id == organization_id))
    session.execute(delete(OrganizationInvitation).where(OrganizationInvitation.organization_id == organization_id))
    session.execute(delete(OrganizationMembership).where(OrganizationMembership.organization_id == organization_id))
    with elevated(session):
        session.execute(delete(Notification).where(Notification.organization_id == organization_id))
        session.execute(delete(NotificationPreference).where(NotificationPreference.organization_id == organization_id))
    session.execute(update(OutboxMessage).where(OutboxMessage.organization_id == organization_id).values(payload={}))
    session.execute(update(AuditEvent).where(AuditEvent.organization_id == organization_id, AuditEvent.change_summary != {}).values(change_summary={}))
    organization.status = OrganizationStatus.PURGED.value
    organization.purged_at = now
    record_audit_event(session, AuditEventDraft(action="organization.purged", target_type="organization", target_id=organization_id, request_id=f"job:{job.id}", change_summary={}))
