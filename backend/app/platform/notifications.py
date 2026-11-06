"""Notifications (ADR-019; from Yearclock ``notifications.py``, 6848e72).

A notification says that something changed for one person, never what the
changed thing says. It is written in the transaction of the action that causes
it. Only the generic mechanism lives here: feature code defines its own types,
and registers an email renderer for the types that may also be sent by email.
Preferences and the per-type settings arrive with the first types.
"""

import os
from collections.abc import Callable, Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import Text, delete, func, literal_column, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.users.models import User
from app.core.database import RequestContext, transaction_session
from app.platform.jobs import register_job_handler, register_scheduler
from app.platform.models import BackgroundJob, Notification, OutboxMessage
from app.platform.work_queue import (
    BackgroundJobDraft,
    OutboxMessageDraft,
    enqueue_background_job,
    enqueue_outbox_message,
)

CLEANUP_JOB = "notifications.cleanup"
EMAIL_TOPIC = "notification"

# (params, locale) -> (subject, body)
EmailRenderer = Callable[[dict[str, Any], str], tuple[str, str]]
EMAIL_RENDERERS: dict[str, EmailRenderer] = {}


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None
    if value < 1:
        raise ValueError(f"{name} must be at least 1")
    return value


def retention_days() -> int:
    return _int_env("NOTIFICATION_RETENTION_DAYS", 90)


def outbox_retention_days() -> int:
    return _int_env("OUTBOX_RETENTION_DAYS", 7)


def emails_per_day() -> int:
    return _int_env("NOTIFICATION_EMAILS_PER_DAY", 10)


def register_email_renderer(notification_type: str, renderer: EmailRenderer) -> None:
    if notification_type in EMAIL_RENDERERS:
        raise ValueError(
            f"notification type {notification_type!r} already has a renderer"
        )
    EMAIL_RENDERERS[notification_type] = renderer


@dataclass(frozen=True)
class NotificationDraft:
    recipient_id: int
    type: str
    params: dict[str, Any] = field(default_factory=dict[str, Any])
    # An unread notification with the same key is replaced by the newer one.
    dedupe_key: str | None = None
    # Also send an email (needs a renderer for the type).
    email: bool = False
    # Contractual notice: emailed regardless of the daily limit.
    mandatory: bool = False


@contextmanager
def elevated(session: Session) -> Generator[None, None, None]:
    """Let the next statements touch other people's notification rows.

    Switched on only for the block; the row-level policy that arrives with the
    tenant routes reads this setting. The setting is transaction-local, so after
    an error (the transaction is aborted) it needs no reset.
    """
    session.execute(text("SELECT set_config('app.notification_write', '1', true)"))
    yield
    session.execute(text("SELECT set_config('app.notification_write', '', true)"))


def notify_many(
    session: Session,
    drafts: Iterable[NotificationDraft],
    *,
    actor_id: int | None = None,
) -> int:
    """Write the notifications and queue the emails in the caller's transaction.

    Nobody is told of their own action. Drafts for the same recipient and
    dedupe key collapse into the last one, and a draft that replaces an unread
    notification (same recipient, tenant and key) updates it instead of adding a
    row and sends no second email, unless it is mandatory. Returns the number of
    notifications written. The tenant comes from the transaction's request
    context.
    """
    wanted: dict[tuple[int, str | None, int], NotificationDraft] = {}
    for position, draft in enumerate(drafts):
        if draft.recipient_id == actor_id:
            continue
        # Drafts without a dedupe key are all kept; with one, the last wins.
        slot = position if draft.dedupe_key is None else 0
        wanted[(draft.recipient_id, draft.dedupe_key, slot)] = draft
    chosen = list(wanted.values())
    if not chosen:
        return 0
    missing = {draft.type for draft in chosen if draft.email} - EMAIL_RENDERERS.keys()
    if missing:
        raise LookupError(f"no email renderer for notification types {sorted(missing)}")
    tenant_id = session.scalar(
        text("SELECT NULLIF(current_setting('app.current_tenant_id', true), '')::uuid")
    )
    ids = [uuid4() for _ in chosen]
    rows = [
        {
            "id": row_id,
            "tenant_id": tenant_id,
            "recipient_user_id": draft.recipient_id,
            "type": draft.type,
            "params": draft.params,
            "dedupe_key": draft.dedupe_key,
        }
        for row_id, draft in zip(ids, chosen, strict=True)
    ]
    with elevated(session):
        statement = insert(Notification).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=[
                Notification.recipient_user_id,
                Notification.tenant_id,
                Notification.dedupe_key,
            ],
            index_where=(Notification.read_time.is_(None))
            & (Notification.dedupe_key.is_not(None)),
            set_={
                "type": statement.excluded.type,
                "params": statement.excluded.params,
                "created_time": func.now(),
            },
        )
        written = session.execute(statement.returning(Notification.id)).scalars().all()
        # A replaced row keeps its old id, so it is not among the new ones.
        inserted = set(written) & set(ids)
        _queue_emails(
            session,
            [
                draft
                for row_id, draft in zip(ids, chosen, strict=True)
                if draft.email and (row_id in inserted or draft.mandatory)
            ],
        )
    return len(written)


def _queue_emails(session: Session, emailing: list[NotificationDraft]) -> None:
    """Outbox messages for the drafts that ask for email, up to the daily limit.

    Past the limit a notification stays in the app only; a mandatory one is
    always emailed. The limit is soft: concurrent transactions for the same
    recipient may both pass it.
    """
    if not emailing:
        return
    recipient_ids = {draft.recipient_id for draft in emailing}
    people = {
        person.user_id: person
        for person in session.scalars(
            select(User).where(
                User.user_id.in_(recipient_ids), User.deleted_time.is_(None)
            )
        ).all()
    }
    recipient = literal_column("outbox_messages.payload ->> 'recipient_id'", Text)
    since = func.now() - timedelta(hours=24)
    sent: dict[str, int] = {
        str(key): int(count)
        for key, count in session.execute(
            select(recipient, func.count())
            .where(
                OutboxMessage.topic == EMAIL_TOPIC,
                OutboxMessage.created_time > since,
                recipient.in_([str(identifier) for identifier in recipient_ids]),
            )
            .group_by(recipient)
        ).all()
    }
    limit = emails_per_day()
    for draft in emailing:
        person = people.get(draft.recipient_id)
        key = str(draft.recipient_id)
        if person is None or (not draft.mandatory and sent.get(key, 0) >= limit):
            continue
        subject, body = EMAIL_RENDERERS[draft.type](draft.params, "en")
        enqueue_outbox_message(
            session,
            OutboxMessageDraft(
                topic=EMAIL_TOPIC,
                payload={
                    "to": person.email,
                    "subject": subject,
                    "text": body,
                    "recipient_id": key,
                },
                idempotency_key=f"notification:{uuid4()}",
            ),
        )
        sent[key] = sent.get(key, 0) + 1


def cleanup_notifications(session: Session, job: BackgroundJob, now: datetime) -> None:
    """Delete notifications past their retention and finished outbox messages.

    A finished (completed or failed) outbox message holds a recipient's address
    and the message text, so it is deleted after ``OUTBOX_RETENTION_DAYS``
    (default 7, which also covers the 24 hours the email limit counts).
    """
    session.execute(
        delete(Notification).where(
            Notification.created_time < now - timedelta(days=retention_days())
        )
    )
    session.execute(
        delete(OutboxMessage).where(
            OutboxMessage.status.in_(("completed", "failed")),
            OutboxMessage.created_time < now - timedelta(days=outbox_retention_days()),
        )
    )


def schedule_notification_cleanup(
    session_factory: sessionmaker[Session], now: datetime
) -> int:
    """Queue one cleanup job per day (idempotent)."""
    with transaction_session(
        session_factory, RequestContext(worker_scope="schedule")
    ) as session:
        enqueue_background_job(
            session,
            BackgroundJobDraft(
                job_type=CLEANUP_JOB,
                payload={},
                idempotency_key=f"{CLEANUP_JOB}:{now.date().isoformat()}",
            ),
        )
    return 1


def register_notification_jobs() -> None:
    register_job_handler(CLEANUP_JOB, cleanup_notifications)
    register_scheduler(schedule_notification_cleanup)
