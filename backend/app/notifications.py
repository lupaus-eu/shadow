"""Notifications (Shadow V2 P8, ADR-0031).

A notification says that something changed for one person, never what an Event
says. It is written in the transaction of the action that causes it. Its text
is built when it is read, from the type and parameters, in the reader's
language. The effective-role comparison uses the single access rule.
"""
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import os
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, literal_column, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.database import RequestContext, apply_request_context
from app.limits import Ceiling
from app.models import BackgroundJob, Notification, NotificationPreference, Organization, OrganizationMembership, OrganizationRole, OutboxMessage, UserAccount

RETENTION_DAYS = Ceiling("notification_retention_days", "NOTIFICATION_RETENTION_DAYS", 90)
CLEANUP_JOB = "notifications.cleanup"

EMAIL_TOPIC = "notification"
EMAILS_PER_DAY = Ceiling("notification_emails_per_day", "LIMIT_NOTIFICATION_EMAILS_PER_DAY", 10)

ACCESS_CHANGED = "access_changed"
ROLE_CHANGED = "role_changed"
INVITATION_ACCEPTED = "invitation_accepted"
OWNERSHIP_CHANGED = "ownership_changed"
SUPPORT_ACCESS_REQUESTED = "support_access_requested"
SUPPORT_ACCESS_ENDED = "support_access_ended"
BILLING_PROBLEM = "billing_problem"
DELETION_SCHEDULED = "deletion_scheduled"
SUBSCRIPTION_CANCEL_SCHEDULED = "subscription_cancel_scheduled"
SUBSCRIPTION_CANCEL_UNDONE = "subscription_cancel_undone"
SUBSCRIPTION_RESUMED = "subscription_resumed"
BILLING_CONTACT_CHANGED = "billing_contact_changed"
LEGAL_DOCUMENT_PUBLISHED = "legal_document_published"
# Contractual notices: always in the app and by email, whatever a person has chosen, and outside the daily email limit.
MANDATORY_KEYS = {"legal"}


@dataclass(frozen=True)
class SettingInfo:
    """One switch group in a person's notification settings and its defaults."""
    audience: str  # "everyone" or "managers" (Owners and Admins)
    in_app: bool
    email: bool


# Keys of the settings; ``setting_key`` maps a notification to one of them.
SETTINGS: dict[str, SettingInfo] = {
    "access_changed": SettingInfo("everyone", True, False),
    "access_removed": SettingInfo("everyone", True, True),
    "role_changed": SettingInfo("everyone", True, False),
    "invitation_accepted": SettingInfo("everyone", True, False),
    "ownership_changed": SettingInfo("everyone", True, False),
    "support_access": SettingInfo("managers", True, True),
    "billing": SettingInfo("managers", True, True),
    "deletion": SettingInfo("managers", True, True),
    # Not offered in the settings page: a contractual notice to Owners (see MANDATORY_KEYS).
    "legal": SettingInfo("owners", True, True),
}


def setting_key(notification_type: str, params: dict[str, Any]) -> str:
    if notification_type == ACCESS_CHANGED and params.get("to_role") == "none":
        return "access_removed"
    return {SUPPORT_ACCESS_REQUESTED: "support_access", SUPPORT_ACCESS_ENDED: "support_access", BILLING_PROBLEM: "billing", SUBSCRIPTION_CANCEL_SCHEDULED: "billing", SUBSCRIPTION_CANCEL_UNDONE: "billing", SUBSCRIPTION_RESUMED: "billing", BILLING_CONTACT_CHANGED: "billing", LEGAL_DOCUMENT_PUBLISHED: "legal", DELETION_SCHEDULED: "deletion"}.get(notification_type, notification_type)


@dataclass(frozen=True)
class NotificationDraft:
    recipient_id: UUID
    type: str
    params: dict[str, Any] = field(default_factory=dict)
    dedupe_key: str | None = None


@contextmanager
def elevated(session: Session) -> Iterator[None]:
    """Let the next statements touch other people's notification rows; always switched off again."""
    session.execute(text("SELECT set_config('app.notification_write', '1', true)"))
    try:
        yield
    finally:
        session.execute(text("SELECT set_config('app.notification_write', '', true)"))


def channel_enabled(preference: NotificationPreference | None, key: str, channel: str) -> bool:
    """A person's switch for a settings key and channel (``in_app`` or ``email``), else the default."""
    chosen = ((preference.settings if preference else {}) or {}).get(key, {})
    return bool(chosen.get(channel, getattr(SETTINGS[key], channel)))


def notify_many(session: Session, organization_id: UUID, drafts: Iterable[NotificationDraft], *, actor_id: UUID | None = None) -> int:
    """Write the notifications; nobody is told of their own action, non-members are skipped, and an unread one with the same key is replaced.

    A person whose settings ask for email (and who has had fewer than the daily limit) also gets an outbox message in the same transaction.
    """
    wanted = [draft for draft in drafts if draft.recipient_id != actor_id]
    if not wanted:
        return 0
    with elevated(session):
        members = set(session.scalars(select(OrganizationMembership.user_account_id).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_account_id.in_({draft.recipient_id for draft in wanted}))).all())
        preferences = {item.user_id: item for item in session.scalars(select(NotificationPreference).where(NotificationPreference.organization_id == organization_id, NotificationPreference.user_id.in_(members))).all()} if members else {}
        kept = [draft for draft in wanted if draft.recipient_id in members and (setting_key(draft.type, draft.params) in MANDATORY_KEYS or channel_enabled(preferences.get(draft.recipient_id), setting_key(draft.type, draft.params), "in_app"))]
        if not kept:
            return 0
        rows = [{"id": uuid4(), "organization_id": organization_id, "recipient_user_id": draft.recipient_id, "type": draft.type, "params": draft.params, "dedupe_key": draft.dedupe_key} for draft in kept]
        statement = insert(Notification).values(rows)
        # A newer unread notice for the same Shadow replaces the older one but keeps where the change began.
        statement = statement.on_conflict_do_update(
            index_elements=[Notification.recipient_user_id, Notification.organization_id, Notification.dedupe_key],
            index_where=and_(Notification.read_at.is_(None), Notification.dedupe_key.is_not(None)),
            set_={"params": func.jsonb_set(statement.excluded.params, literal_column("'{from_role}'::text[]"), func.coalesce(Notification.params["from_role"], statement.excluded.params["from_role"]), True), "created_at": func.now()},
        )
        session.execute(statement)
        # A change that ended where it began is no news.
        session.execute(delete(Notification).where(Notification.organization_id == organization_id, Notification.type == ACCESS_CHANGED, Notification.read_at.is_(None), Notification.recipient_user_id.in_({row["recipient_user_id"] for row in rows}), Notification.params["from_role"].astext == Notification.params["to_role"].astext))
        _queue_emails(session, organization_id, kept, preferences)
    return len(rows)


def _queue_emails(session: Session, organization_id: UUID, drafts: list[NotificationDraft], preferences: dict[UUID, NotificationPreference]) -> None:
    """Outbox messages for the drafts whose email switch is on, up to the daily limit per recipient; the rest stay in the app."""
    from app.notification_email import render
    from app.work_queue import OutboxMessageDraft, enqueue_outbox_message

    emailing = [draft for draft in drafts if setting_key(draft.type, draft.params) in MANDATORY_KEYS or channel_enabled(preferences.get(draft.recipient_id), setting_key(draft.type, draft.params), "email")]
    if not emailing:
        return
    recipients = {draft.recipient_id for draft in emailing}
    since = func.now() - timedelta(hours=24)
    recipient = literal_column("outbox_messages.payload ->> 'recipient_id'")
    sent = dict(session.execute(select(recipient, func.count()).where(OutboxMessage.organization_id == organization_id, OutboxMessage.topic == EMAIL_TOPIC, OutboxMessage.created_at > since).group_by(recipient)).all())
    people = {item.id: item for item in session.scalars(select(UserAccount).where(UserAccount.id.in_(recipients))).all()}
    organization = session.get(Organization, organization_id)
    frontend = os.getenv('FRONTEND_URL', 'http://localhost:8173').rstrip('/')
    base = f"{frontend}/organizations/{organization_id}"
    for draft in emailing:
        person = people.get(draft.recipient_id)
        key = str(draft.recipient_id)
        mandatory = setting_key(draft.type, draft.params) in MANDATORY_KEYS
        if person is None or (not mandatory and sent.get(key, 0) >= EMAILS_PER_DAY.maximum):
            continue
        subject, body = render(draft.type, draft.params, locale=person.locale or organization.default_locale, organization_name=organization.name, inbox_url=f"{base}/notifications", settings_url=f"{base}/notification-settings", privacy_url=f"{frontend}/legal/privacy")
        enqueue_outbox_message(session, OutboxMessageDraft(topic=EMAIL_TOPIC, payload={"to": person.email, "subject": subject, "text": body, "recipient_id": key}, idempotency_key=f"notification:{uuid4()}"))
        sent[key] = sent.get(key, 0) + 1


def managers_of(session: Session, organization_id: UUID) -> list[UUID]:
    """The Owners and Admins of the Organization, who receive the Organization notices."""
    return list(session.scalars(select(OrganizationMembership.user_account_id).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.role.in_([OrganizationRole.OWNER.value, OrganizationRole.ADMIN.value]))).all())


def notify_managers(session: Session, organization_id: UUID, notification_type: str, params: dict[str, Any], *, actor_id: UUID | None = None) -> int:
    return notify_many(session, organization_id, [NotificationDraft(user_id, notification_type, params) for user_id in managers_of(session, organization_id)], actor_id=actor_id)


def membership_user(session: Session, membership_id: UUID) -> UUID | None:
    return session.scalar(select(OrganizationMembership.user_account_id).where(OrganizationMembership.id == membership_id))


def cleanup_notifications(session: Session, job: BackgroundJob, now: datetime) -> None:
    """Delete this Organization's notifications past their retention."""
    apply_request_context(session, RequestContext(organization_id=job.organization_id, worker_scope="notifications"))
    session.execute(delete(Notification).where(Notification.organization_id == job.organization_id, Notification.created_at < now - timedelta(days=RETENTION_DAYS.maximum)))


def _person(session: Session, user_account_id: UUID) -> str:
    row = session.execute(select(UserAccount.display_name, UserAccount.email).where(UserAccount.id == user_account_id)).first()
    return (row[0] or row[1]) if row else ""


def notify_role_change(session: Session, organization_id: UUID, *, actor_id: UUID, target_user_id: UUID, from_role: str, to_role: str) -> None:
    """Tell the person their Organization role changed, and the other Owners when ownership was given or taken."""
    if from_role == to_role:
        return
    drafts = [NotificationDraft(target_user_id, ROLE_CHANGED, {"from_role": from_role, "to_role": to_role})]
    if OrganizationRole.OWNER.value in (from_role, to_role):
        owners = session.scalars(select(OrganizationMembership.user_account_id).where(OrganizationMembership.organization_id == organization_id, OrganizationMembership.role == OrganizationRole.OWNER.value)).all()
        params = {"name": _person(session, target_user_id), "owner": to_role == OrganizationRole.OWNER.value}
        drafts += [NotificationDraft(owner, OWNERSHIP_CHANGED, params) for owner in owners if owner != target_user_id]
    notify_many(session, organization_id, drafts, actor_id=actor_id)


def notify_invitation_accepted(session: Session, organization_id: UUID, *, inviter_id: UUID, accepted_by: UUID, role: str) -> None:
    notify_many(session, organization_id, [NotificationDraft(inviter_id, INVITATION_ACCEPTED, {"name": _person(session, accepted_by), "role": role})], actor_id=accepted_by)
