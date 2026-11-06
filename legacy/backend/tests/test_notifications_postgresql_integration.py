from collections.abc import Callable, Generator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import RequestContext, transaction_session
from app.platform import notifications
from app.platform.email_delivery import EmailDeliveryError, EmailMessage
from app.platform.jobs import run_one_background_job
from app.platform.models import BackgroundJob, Notification, OutboxMessage
from app.platform.notifications import (
    CLEANUP_JOB,
    EMAIL_TOPIC,
    NotificationDraft,
    cleanup_notifications,
    notify_many,
    register_email_renderer,
    schedule_notification_cleanup,
)
from app.platform.worker import MAX_EMAIL_ATTEMPTS, deliver_one_email

Factory = sessionmaker[Session]


def _user(factory: Factory, name: str, email: str | None = None) -> int:
    with factory.begin() as session:
        return int(
            session.scalar(
                text(
                    "INSERT INTO users (name, role, email) "
                    "VALUES (:name, 'consultant', :email) RETURNING user_id"
                ),
                {"name": name, "email": email or f"{name.lower()}@example.test"},
            )
            or 0
        )


@pytest.fixture(autouse=True)
def renderers(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setattr(notifications, "EMAIL_RENDERERS", {})
    register_email_renderer(
        "demo.changed",
        lambda params, locale: (f"Changed {params['what']}", "see the app"),
    )
    yield


def _notify(
    factory: Factory,
    drafts: list[NotificationDraft],
    *,
    actor: int | None = None,
    tenant: UUID | None = None,
    user_id: int | None = None,
) -> int:
    with transaction_session(
        factory, RequestContext(user_id=user_id, tenant_id=tenant)
    ) as session:
        return notify_many(session, drafts, actor_id=actor)


def _rows(factory: Factory) -> list[Notification]:
    with factory() as session:
        return list(
            session.scalars(select(Notification).order_by(Notification.created_time))
        )


def test_notify_writes_rows_for_recipients_but_not_for_the_actor(
    schema_session_factory: Factory,
) -> None:
    actor, other = (
        _user(schema_session_factory, "Actor"),
        _user(schema_session_factory, "Other"),
    )
    tenant = uuid4()

    count = _notify(
        schema_session_factory,
        [
            NotificationDraft(actor, "demo.changed", {"what": "a"}),
            NotificationDraft(other, "demo.changed", {"what": "a"}),
        ],
        actor=actor,
        tenant=tenant,
    )

    assert count == 1
    (row,) = _rows(schema_session_factory)
    assert (row.recipient_user_id, row.type, row.tenant_id) == (
        other,
        "demo.changed",
        tenant,
    )
    assert row.params == {"what": "a"} and row.read_time is None
    assert _notify(schema_session_factory, [], actor=actor) == 0


def test_a_newer_unread_notification_with_the_same_key_replaces_the_older(
    schema_session_factory: Factory,
) -> None:
    person = _user(schema_session_factory, "Person")

    def draft(what: str) -> NotificationDraft:
        return NotificationDraft(
            person, "demo.changed", {"what": what}, dedupe_key="thing-1"
        )

    _notify(schema_session_factory, [draft("first")])
    _notify(schema_session_factory, [draft("second")])
    (row,) = _rows(schema_session_factory)
    assert row.params == {"what": "second"}

    with schema_session_factory.begin() as session:
        session.execute(update(Notification).values(read_time=datetime.now(UTC)))
    _notify(schema_session_factory, [draft("third")])
    assert len(_rows(schema_session_factory)) == 2  # a read one is not replaced


def test_dedupe_is_scoped_to_the_tenant(schema_session_factory: Factory) -> None:
    person = _user(schema_session_factory, "Person")
    draft = NotificationDraft(person, "demo.changed", {"what": "x"}, dedupe_key="k")
    _notify(schema_session_factory, [draft], tenant=uuid4())
    _notify(schema_session_factory, [draft], tenant=uuid4())
    assert len(_rows(schema_session_factory)) == 2


def test_email_is_queued_only_when_asked_and_carries_the_rendered_text(
    schema_session_factory: Factory,
) -> None:
    person = _user(schema_session_factory, "Person", "person@example.test")
    quiet = NotificationDraft(person, "demo.changed", {"what": "q"})
    loud = NotificationDraft(person, "demo.changed", {"what": "l"}, email=True)
    _notify(schema_session_factory, [quiet, loud])
    with schema_session_factory() as session:
        (message,) = session.scalars(select(OutboxMessage)).all()
    assert message.topic == EMAIL_TOPIC
    assert message.payload == {
        "to": "person@example.test",
        "subject": "Changed l",
        "text": "see the app",
        "recipient_id": str(person),
    }


def test_daily_email_limit_applies_except_to_mandatory_notices(
    schema_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOTIFICATION_EMAILS_PER_DAY", "2")
    person = _user(schema_session_factory, "Person")
    for index in range(4):
        _notify(
            schema_session_factory,
            [
                NotificationDraft(
                    person, "demo.changed", {"what": str(index)}, email=True
                )
            ],
        )
    _notify(
        schema_session_factory,
        [
            NotificationDraft(
                person, "demo.changed", {"what": "legal"}, email=True, mandatory=True
            )
        ],
    )
    with schema_session_factory() as session:
        assert len(session.scalars(select(OutboxMessage)).all()) == 3
    assert len(_rows(schema_session_factory)) == 5  # every one is still in the app


def test_deleted_recipient_gets_no_email_and_missing_renderer_is_an_error(
    schema_session_factory: Factory,
) -> None:
    gone = _user(schema_session_factory, "Gone")
    with schema_session_factory.begin() as session:
        session.execute(
            text("UPDATE users SET deleted_time = now() WHERE user_id = :id"),
            {"id": gone},
        )
    _notify(
        schema_session_factory,
        [NotificationDraft(gone, "demo.changed", {"what": "x"}, email=True)],
    )
    with schema_session_factory() as session:
        assert session.scalars(select(OutboxMessage)).all() == []
    with pytest.raises(LookupError, match="no email renderer"):
        _notify(
            schema_session_factory,
            [NotificationDraft(gone, "demo.unknown", {}, email=True)],
        )


def test_cleanup_job_removes_old_notifications_and_is_scheduled_once_a_day(
    schema_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOTIFICATION_RETENTION_DAYS", "30")
    person = _user(schema_session_factory, "Person")
    _notify(
        schema_session_factory,
        [NotificationDraft(person, "demo.changed", {"what": "old"})],
    )
    _notify(
        schema_session_factory,
        [NotificationDraft(person, "demo.changed", {"what": "new"})],
    )
    with schema_session_factory.begin() as session:
        session.execute(
            update(Notification)
            .where(Notification.params["what"].as_string() == "old")
            .values(created_time=datetime.now(UTC) - timedelta(days=31))
        )

    now = datetime.now(UTC)
    assert schedule_notification_cleanup(schema_session_factory, now) == 1
    assert schedule_notification_cleanup(schema_session_factory, now) == 1
    with schema_session_factory() as session:
        assert len(session.scalars(select(BackgroundJob)).all()) == 1
    ran = run_one_background_job(
        schema_session_factory, handlers={CLEANUP_JOB: cleanup_notifications}
    )
    assert ran
    assert [row.params["what"] for row in _rows(schema_session_factory)] == ["new"]


class _Sender:
    def __init__(self, fail_times: int = 0) -> None:
        self.sent: list[EmailMessage] = []
        self.fail_times = fail_times

    def send(self, message: EmailMessage) -> str:
        if self.fail_times:
            self.fail_times -= 1
            raise EmailDeliveryError("provider down")
        self.sent.append(message)
        return f"provider-{len(self.sent)}"


def _queue_email(factory: Factory) -> UUID:
    person = _user(factory, "Person", "person@example.test")
    _notify(
        factory, [NotificationDraft(person, "demo.changed", {"what": "x"}, email=True)]
    )
    with factory() as session:
        return session.scalars(select(OutboxMessage.id)).one()


def _outbox(factory: Factory, message_id: UUID) -> OutboxMessage:
    with factory() as session:
        message = session.get(OutboxMessage, message_id)
        assert message is not None
        return message


def test_worker_delivers_a_queued_email_once(schema_session_factory: Factory) -> None:
    message_id = _queue_email(schema_session_factory)
    sender = _Sender()
    assert deliver_one_email(schema_session_factory, sender) is True
    assert deliver_one_email(schema_session_factory, sender) is False
    (sent,) = sender.sent
    assert (sent.recipient, sent.subject, sent.text) == (
        "person@example.test",
        "Changed x",
        "see the app",
    )
    stored = _outbox(schema_session_factory, message_id)
    assert (stored.status, stored.provider_message_id) == ("completed", "provider-1")
    assert sent.idempotency_key == stored.idempotency_key


def test_failed_delivery_is_retried_with_backoff_then_failed_without_content(
    schema_session_factory: Factory,
) -> None:
    message_id = _queue_email(schema_session_factory)
    sender = _Sender(fail_times=10)
    stored = _outbox(schema_session_factory, message_id)
    for attempt in range(1, MAX_EMAIL_ATTEMPTS + 1):
        with schema_session_factory.begin() as session:  # make it due again
            session.execute(
                update(OutboxMessage).values(
                    available_time=datetime.now(UTC) - timedelta(seconds=1)
                )
            )
        assert deliver_one_email(schema_session_factory, sender) is True
        stored = _outbox(schema_session_factory, message_id)
        assert (
            stored.attempts == attempt
            and stored.last_error == "EmailDeliveryError: provider down"
        )
        assert stored.status == (
            "pending" if attempt < MAX_EMAIL_ATTEMPTS else "failed"
        )
    assert sender.sent == []
    assert "person@example.test" not in (stored.last_error or "")


def test_invalid_payload_fails_the_message_not_the_worker(
    schema_session_factory: Factory,
) -> None:
    with transaction_session(schema_session_factory, RequestContext()) as session:
        from app.platform.work_queue import OutboxMessageDraft, enqueue_outbox_message

        message_id = enqueue_outbox_message(
            session, OutboxMessageDraft(EMAIL_TOPIC, {"to": "x@example.test"}, "bad-1")
        )
    assert deliver_one_email(schema_session_factory, _Sender()) is True
    assert "invalid email payload" in (
        _outbox(schema_session_factory, message_id).last_error or ""
    )


def test_notifications_belong_to_their_recipient_and_vanish_with_the_user(
    schema_session_factory: Factory,
) -> None:
    person = _user(schema_session_factory, "Person")
    _notify(
        schema_session_factory,
        [NotificationDraft(person, "demo.changed", {"what": "x"})],
    )
    with schema_session_factory.begin() as session:
        session.execute(text("DELETE FROM users WHERE user_id = :id"), {"id": person})
    assert _rows(schema_session_factory) == []


def test_invalid_environment_values_are_clear_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, call in (
        ("NOTIFICATION_RETENTION_DAYS", notifications.retention_days),
        ("NOTIFICATION_EMAILS_PER_DAY", notifications.emails_per_day),
    ):
        for value in ("many", "0"):
            monkeypatch.setenv(name, value)
            with pytest.raises(ValueError, match=name):
                call()


def test_register_email_renderer_rejects_duplicates() -> None:
    renderer: Callable[[dict[str, Any], str], tuple[str, str]] = lambda p, l: ("s", "b")  # noqa: E731, E741
    with pytest.raises(ValueError, match="already"):
        register_email_renderer("demo.changed", renderer)


def test_drafts_for_one_recipient_and_key_collapse_into_the_last_one(
    schema_session_factory: Factory,
) -> None:
    person = _user(schema_session_factory, "Person")
    count = _notify(
        schema_session_factory,
        [
            NotificationDraft(person, "demo.changed", {"what": "a"}, dedupe_key="k"),
            NotificationDraft(person, "demo.changed", {"what": "b"}, dedupe_key="k"),
            NotificationDraft(person, "demo.changed", {"what": "c"}),
            NotificationDraft(person, "demo.changed", {"what": "d"}),
        ],
    )
    assert count == 3
    assert sorted(row.params["what"] for row in _rows(schema_session_factory)) == [
        "b",
        "c",
        "d",
    ]


def test_a_replaced_notification_updates_type_and_sends_no_second_email(
    schema_session_factory: Factory,
) -> None:
    register_email_renderer("demo.other", lambda params, locale: ("Other", "text"))
    person = _user(schema_session_factory, "Person")
    first = NotificationDraft(
        person, "demo.changed", {"what": "1"}, dedupe_key="k", email=True
    )
    second = NotificationDraft(
        person, "demo.other", {"what": "2"}, dedupe_key="k", email=True
    )
    assert _notify(schema_session_factory, [first]) == 1
    assert _notify(schema_session_factory, [second]) == 1
    (row,) = _rows(schema_session_factory)
    assert (row.type, row.params) == ("demo.other", {"what": "2"})
    with schema_session_factory() as session:
        assert len(session.scalars(select(OutboxMessage)).all()) == 1
    mandatory = NotificationDraft(
        person, "demo.other", {"what": "3"}, dedupe_key="k", email=True, mandatory=True
    )
    _notify(schema_session_factory, [mandatory])
    with schema_session_factory() as session:
        assert len(session.scalars(select(OutboxMessage)).all()) == 2


def test_cleanup_deletes_finished_outbox_messages_after_their_retention(
    schema_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OUTBOX_RETENTION_DAYS", "7")
    person = _user(schema_session_factory, "Person", "person@example.test")
    for index in range(4):
        _notify(
            schema_session_factory,
            [
                NotificationDraft(
                    person, "demo.changed", {"what": str(index)}, email=True
                )
            ],
        )
    with schema_session_factory.begin() as session:
        ids = list(
            session.scalars(
                select(OutboxMessage.id).order_by(OutboxMessage.created_time)
            )
        )
        old = datetime.now(UTC) - timedelta(days=8)
        for message_id, status, created in (
            (ids[0], "completed", old),
            (ids[1], "failed", old),
            (ids[2], "pending", old),
            (ids[3], "completed", datetime.now(UTC)),
        ):
            session.execute(
                update(OutboxMessage)
                .where(OutboxMessage.id == message_id)
                .values(status=status, created_time=created)
            )
    with transaction_session(schema_session_factory, RequestContext()) as session:
        job = BackgroundJob(job_type=CLEANUP_JOB, payload={}, idempotency_key="x")
        cleanup_notifications(session, job, datetime.now(UTC))
    with schema_session_factory() as session:
        remaining = set(session.scalars(select(OutboxMessage.id)))
    assert remaining == {ids[2], ids[3]}


def test_a_permanent_failure_fails_at_once_and_unknown_errors_leave_no_content(
    schema_session_factory: Factory,
) -> None:
    message_id = _queue_email(schema_session_factory)

    class Rejecting:
        def send(self, message: EmailMessage) -> str:
            raise EmailDeliveryError("Scaleway answered HTTP 422", permanent=True)

    assert deliver_one_email(schema_session_factory, Rejecting()) is True
    stored = _outbox(schema_session_factory, message_id)
    assert (stored.status, stored.attempts) == ("failed", 1)
    assert stored.last_error == "EmailDeliveryError: Scaleway answered HTTP 422"

    other_id = _queue_email_for(schema_session_factory, "second@example.test")

    class Leaky:
        def send(self, message: EmailMessage) -> str:
            raise RuntimeError(f"could not reach {message.recipient}")

    assert deliver_one_email(schema_session_factory, Leaky()) is True
    assert _outbox(schema_session_factory, other_id).last_error == "RuntimeError"


def _queue_email_for(factory: Factory, address: str) -> UUID:
    person = _user(factory, "Second", address)
    _notify(
        factory, [NotificationDraft(person, "demo.changed", {"what": "y"}, email=True)]
    )
    with factory() as session:
        return session.scalars(
            select(OutboxMessage.id).where(
                OutboxMessage.payload["to"].as_string() == address
            )
        ).one()
