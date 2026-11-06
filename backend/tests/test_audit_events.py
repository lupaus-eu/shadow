from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.audit import AuditEventDraft, record_audit_event
from app.database import (
    RequestContext,
    create_database_engine,
    create_session_factory,
    transaction_session,
)


def test_audit_event_is_recorded_and_append_only(database_url: str) -> None:
    engine = create_database_engine(database_url)
    session_factory = create_session_factory(engine)
    context = RequestContext(
        user_account_id=uuid4(),
        organization_id=uuid4(),
    )
    target_id = uuid4()

    with transaction_session(session_factory, context) as session:
        audit_event_id = record_audit_event(
            session,
            AuditEventDraft(
                action="foundation.verified",
                target_type="system",
                target_id=target_id,
                request_id="request-123",
                change_summary={"status": "ready"},
            ),
        )

    with engine.connect() as connection:
        event = connection.execute(
            text(
                """
                SELECT
                    actor_user_account_id,
                    organization_id,
                    action,
                    target_type,
                    target_id,
                    request_id,
                    change_summary
                FROM audit_events
                WHERE id = :audit_event_id
                """
            ),
            {"audit_event_id": audit_event_id},
        ).one()

    assert event._mapping == {
        "actor_user_account_id": context.user_account_id,
        "organization_id": context.organization_id,
        "action": "foundation.verified",
        "target_type": "system",
        "target_id": target_id,
        "request_id": "request-123",
        "change_summary": {"status": "ready"},
    }

    with transaction_session(session_factory, context) as session:
        can_update_audit = session.scalar(
            text(
                """
                SELECT has_table_privilege(
                    current_user,
                    'audit_events',
                    'UPDATE'
                )
                """
            )
        )
        can_delete_audit = session.scalar(
            text(
                """
                SELECT has_table_privilege(
                    current_user,
                    'audit_events',
                    'DELETE'
                )
                """
            )
        )
        can_select_audit = session.scalar(
            text(
                """
                SELECT has_table_privilege(
                    current_user,
                    'audit_events',
                    'SELECT'
                )
                """
            )
        )

    assert can_update_audit is False
    assert can_delete_audit is False
    assert can_select_audit is True

    with transaction_session(session_factory, context) as session:
        own = session.execute(text("SELECT id FROM audit_events")).scalars().all()
    with transaction_session(session_factory, RequestContext(user_account_id=uuid4(), organization_id=uuid4())) as session:
        foreign = session.execute(text("SELECT id FROM audit_events WHERE id = :id"), {"id": audit_event_id}).scalars().all()
    with transaction_session(session_factory, RequestContext()) as session:
        without_context = session.execute(text("SELECT id FROM audit_events WHERE id = :id"), {"id": audit_event_id}).scalars().all()
    assert own == [audit_event_id]
    assert foreign == []
    assert without_context == []

    with pytest.raises(DBAPIError), transaction_session(session_factory, context) as session:
        session.execute(
            text("INSERT INTO audit_events (id, organization_id, action, target_type, target_id, request_id, change_summary) VALUES (:id, :org, 'forged', 'system', :id, 'forged', '{}')"),
            {"id": uuid4(), "org": uuid4()},
        )

    with pytest.raises(DBAPIError), transaction_session(
        session_factory,
        context,
    ) as session:
        session.execute(
            text("UPDATE audit_events SET action = 'changed' WHERE id = :id"),
            {"id": audit_event_id},
        )

    with pytest.raises(DBAPIError), transaction_session(
        session_factory,
        context,
    ) as session:
        session.execute(
            text("DELETE FROM audit_events WHERE id = :id"),
            {"id": audit_event_id},
        )
