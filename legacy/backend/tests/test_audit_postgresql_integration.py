from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import RequestContext, transaction_session
from app.platform.audit import (
    AuditEventDraft,
    audit_source,
    current_source,
    record_audit_event,
)
from app.platform.models import AuditEvent


def _user_id(factory: sessionmaker[Session]) -> int:
    with factory.begin() as session:
        return int(
            session.scalar(
                text(
                    "INSERT INTO users (name, role, email) "
                    "VALUES ('Auditor', 'admin', 'auditor@example.test') "
                    "RETURNING user_id"
                )
            )
            or 0
        )


def _draft(**summary: object) -> AuditEventDraft:
    return AuditEventDraft(
        action="organisation.renamed",
        target_type="organisation",
        target_id=123,
        request_id="req-1",
        change_summary=dict(summary),
    )


def test_event_takes_actor_and_tenant_from_the_request_context(
    schema_session_factory: sessionmaker[Session],
) -> None:
    user_id = _user_id(schema_session_factory)
    tenant_id = uuid4()
    context = RequestContext(user_id=user_id, tenant_id=tenant_id)
    with transaction_session(schema_session_factory, context) as session:
        event_id = record_audit_event(session, _draft(name="new"))

    with schema_session_factory() as session:
        event = session.get(AuditEvent, event_id)
        assert event is not None
        assert event.actor_user_id == user_id
        assert event.tenant_id == tenant_id
        assert event.support_access_id is None
        assert event.target_id == "123"
        assert event.change_summary == {"name": "new"}
        assert event.occurred_time is not None


def test_event_without_context_has_no_actor_or_tenant(
    schema_session_factory: sessionmaker[Session],
) -> None:
    with transaction_session(schema_session_factory, RequestContext()) as session:
        event_id = record_audit_event(session, _draft())
    with schema_session_factory() as session:
        event = session.get(AuditEvent, event_id)
        assert event is not None
        assert (event.actor_user_id, event.tenant_id) == (None, None)


def test_audit_source_is_merged_into_the_summary_and_restored(
    schema_session_factory: sessionmaker[Session],
) -> None:
    assert current_source() is None
    with transaction_session(schema_session_factory, RequestContext()) as session:
        with audit_source(channel="mcp", client="claude"):
            assert current_source() == {"channel": "mcp", "client": "claude"}
            event_id = record_audit_event(session, _draft(name="x"))
    assert current_source() is None
    with schema_session_factory() as session:
        event = session.get(AuditEvent, event_id)
        assert event is not None
        assert event.change_summary == {
            "name": "x",
            "source": {"channel": "mcp", "client": "claude"},
        }


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET action = 'x'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ],
)
def test_events_cannot_be_changed_even_by_the_owner(
    schema_session_factory: sessionmaker[Session], statement: str
) -> None:
    with transaction_session(schema_session_factory, RequestContext()) as session:
        record_audit_event(session, _draft())
    with pytest.raises(DBAPIError, match="append-only"):
        with schema_session_factory.begin() as session:
            session.execute(text(statement))


@pytest.mark.parametrize(
    "statement",
    ["UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"],
)
def test_application_role_has_no_update_or_delete_privilege(
    schema_session_factory: sessionmaker[Session], statement: str
) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        with transaction_session(schema_session_factory, RequestContext()) as session:
            session.execute(text(statement))


def test_application_role_can_read_events(
    schema_session_factory: sessionmaker[Session],
) -> None:
    with transaction_session(schema_session_factory, RequestContext()) as session:
        record_audit_event(session, _draft())
    with transaction_session(schema_session_factory, RequestContext()) as session:
        assert session.scalars(select(AuditEvent)).all()


@pytest.mark.parametrize(
    "overrides",
    [
        {"action": " "},
        {"action": "a" * 121},
        {"target_id": " "},
        {"request_id": "r" * 121},
        {"request_id": " "},
        {"target_id": "t" * 201},
        {"target_type": " "},
        {"target_type": "t" * 121},
    ],
)
def test_invalid_events_are_rejected(
    schema_session_factory: sessionmaker[Session], overrides: dict[str, str]
) -> None:
    values: dict[str, str] = {
        "action": "a.b",
        "target_type": "organisation",
        "target_id": "1",
        "request_id": "req",
    }
    values.update(overrides)
    draft = AuditEventDraft(
        action=values["action"],
        target_type=values["target_type"],
        target_id=values["target_id"],
        request_id=values["request_id"],
    )
    with pytest.raises(IntegrityError):
        with transaction_session(schema_session_factory, RequestContext()) as session:
            record_audit_event(session, draft)
            session.flush()


def test_event_without_a_request_context_is_refused(
    schema_session_factory: sessionmaker[Session],
) -> None:
    with schema_session_factory.begin() as session:
        with pytest.raises(RuntimeError, match="transaction_session"):
            record_audit_event(session, _draft())


def test_support_access_id_comes_from_the_context(
    schema_session_factory: sessionmaker[Session],
) -> None:
    support_id = uuid4()
    context = RequestContext(support_access_id=support_id)
    with transaction_session(schema_session_factory, context) as session:
        event_id = record_audit_event(session, _draft())
    with schema_session_factory() as session:
        event = session.get(AuditEvent, event_id)
        assert event is not None and event.support_access_id == support_id


def test_summary_cannot_forge_or_collide_with_the_source_key(
    schema_session_factory: sessionmaker[Session],
) -> None:
    with transaction_session(schema_session_factory, RequestContext()) as session:
        with pytest.raises(ValueError, match="reserved"):
            record_audit_event(session, _draft(source={"channel": "mcp"}))
        event_id = record_audit_event(session, _draft(channel="mcp", client="x"))
    with schema_session_factory() as session:
        event = session.get(AuditEvent, event_id)
        assert event is not None
        # Without an active audit_source the payload stays plain payload.
        assert event.change_summary == {"channel": "mcp", "client": "x"}


def test_audit_source_nests_restores_after_errors_and_is_immutable() -> None:
    with audit_source(channel="mcp"):
        with pytest.raises(RuntimeError):
            with audit_source(channel="inner"):
                assert current_source() == {"channel": "inner"}
                raise RuntimeError("boom")
        assert current_source() == {"channel": "mcp"}
        snapshot = current_source()
        assert snapshot is not None
        snapshot["channel"] = "tampered"
        assert current_source() == {"channel": "mcp"}
    assert current_source() is None


def test_values_that_are_not_json_fail_at_the_call_site(
    schema_session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(TypeError):
        with audit_source(client=uuid4()):
            pass
    with transaction_session(schema_session_factory, RequestContext()) as session:
        with pytest.raises(TypeError):
            record_audit_event(session, _draft(when=uuid4()))


def test_application_role_cannot_truncate_events(
    schema_session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        with transaction_session(schema_session_factory, RequestContext()) as session:
            session.execute(text("TRUNCATE audit_events"))
