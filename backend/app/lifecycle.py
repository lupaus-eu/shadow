"""Recoverable deletion and purge of Shadow content (docs/architecture/lifecycle-defaults.md)."""

import os
from datetime import datetime, timedelta
from uuid import UUID

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
    Organization,
    OrganizationInvitation,
    OrganizationMembership,
    OrganizationStatus,
    OutboxMessage,
    SupportAccessRequest,
)


def content_retention() -> timedelta:
    """How long deleted Events and Shadows stay recoverable."""
    return timedelta(days=int(os.getenv("DELETED_CONTENT_RETENTION_DAYS", "30")))


def organization_deletion_window() -> timedelta:
    """How long a Pending Deletion Organization stays restorable before purge."""
    return timedelta(days=int(os.getenv("ORGANIZATION_DELETION_RETENTION_DAYS", "30")))


def organization_purge_after(organization: Organization) -> datetime | None:
    if organization.status != OrganizationStatus.PENDING_DELETION.value or organization.deletion_requested_at is None:
        return None
    return organization.deletion_requested_at + organization_deletion_window()


def purge_deleted_content(session: Session, job: BackgroundJob, now: datetime) -> None:
    """Idempotently purge product content deleted longer ago than the retention period.

    The platform base has no product content yet; each feature registers its purge here.
    """


def purge_organization(session: Session, job: BackgroundJob, now: datetime) -> None:
    """Purge a Pending Deletion Organization whose window has ended; a no-op otherwise.

    Removes product content, memberships, invitations, Support
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
    # Product content is purged here, children first, as features are added.
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
