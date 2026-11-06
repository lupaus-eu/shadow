"""Notification email, settings, and Owner/Admin notices (Shadow V2, P8 ticket 03)."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.worker import deliver_one_email
from test_invitations import NOW
from test_notifications import World, stack  # noqa: F401 - the fixture
from test_subscription_lifecycle import _event, _post
from test_support_access import _agent


class Sender:
    def __init__(self) -> None:
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        return f"provider-{len(self.sent)}"


def emails(world, topic="notification"):
    with world.application.state.database_engine.begin() as connection:
        return [dict(row._mapping) for row in connection.execute(text("SELECT payload, status FROM outbox_messages WHERE topic = :topic AND organization_id = :org ORDER BY created_at"), {"topic": topic, "org": world.organization_id})]


def put_settings(client, world, **settings):
    response = client.put(f"{world.org}/notification-settings", json={"settings": settings})
    assert response.status_code == 200, response.text
    return {item["key"]: item for item in response.json()["items"]}


def test_deletion_support_access_and_billing_notices_reach_owners_and_admins_only(database_url, stack) -> None:
    world = World(stack, database_url, "ntfe-notices")
    member, _, _ = world.person("member")
    admin, _, _ = world.person("admin", role="admin")
    agent = _agent(stack, database_url, "ntfe-agent")
    grant = agent.post("/api/v1/platform/support-access", json={"organization_id": world.organization_id, "case_reference": "CASE-9", "hours": 2}).json()
    assert [item["params"]["case_reference"] for item in world.notices(world.owner, "support_access_requested")] == ["CASE-9"]
    assert len(world.notices(admin, "support_access_requested")) == 1 and world.notices(member) == []
    assert any("CASE-9" in mail["payload"]["text"] and "Platform support" in mail["payload"]["text"] for mail in emails(world))
    assert world.owner.post(f"{world.org}/support-access/{grant['id']}/approve", json={"hours": 1}).status_code == 200
    assert world.owner.post(f"{world.org}/support-access/{grant['id']}/revoke").status_code == 200
    assert world.notices(world.owner, "support_access_ended") == [] and len(world.notices(admin, "support_access_ended")) == 1
    # A failed renewal payment and a deletion request.
    _post(world.owner, world.verifier, _event(world.organization_id, "invoice.payment_failed", "evt_ntfe_failed", datetime.now(UTC) - timedelta(days=1), billing_reason="subscription_cycle"))
    assert len(world.notices(world.owner, "billing_problem")) == 1 and len(world.notices(admin, "billing_problem")) == 1 and world.notices(member, "billing_problem") == []
    assert world.owner.post(f"{world.org}/deletion", json={"confirm": True}).status_code == 200
    with world.application.state.database_engine.begin() as connection:
        rows = connection.execute(text("SELECT recipient_user_id, type FROM notifications WHERE organization_id = :org AND type = 'deletion_scheduled'"), {"org": world.organization_id}).all()
    assert len(rows) == 1  # the other manager, the Admin; the actor is not told of their own action


def test_an_expired_grant_notifies_every_owner_and_admin(database_url, stack) -> None:
    from uuid import UUID

    from app.support_access_routes import expire_due_grants

    world = World(stack, database_url, "ntfe-expiry")
    admin, _, _ = world.person("admin", role="admin")
    agent = _agent(stack, database_url, "ntfe-expiry-agent")
    grant = agent.post("/api/v1/platform/support-access", json={"organization_id": world.organization_id, "case_reference": "CASE-7", "hours": 1}).json()
    assert world.owner.post(f"{world.org}/support-access/{grant['id']}/approve", json={"hours": 1}).status_code == 200
    with world.application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE support_access_requests SET expires_at = now() - interval '1 minute' WHERE id = :id"), {"id": grant["id"]})
    assert expire_due_grants(world.application.state.session_factory, UUID(world.organization_id)) == 1
    for client in (world.owner, admin):
        [notice] = world.notices(client, "support_access_ended")
        assert notice["params"] == {"case_reference": "CASE-7", "how": "expired"}


def test_the_notification_email_links_to_the_privacy_notice() -> None:
    from app.notification_email import render

    _, body = render("unknown", {}, locale="en", organization_name="Northwind", inbox_url="https://x/i", settings_url="https://x/s", privacy_url="https://x/legal/privacy")
    assert body.endswith("Privacy notice: https://x/legal/privacy")
    _, plain = render("unknown", {}, locale="en", organization_name="Northwind", inbox_url="https://x/i", settings_url="https://x/s")
    assert "Privacy notice" not in plain


def test_the_invitation_email_links_to_the_privacy_notice() -> None:
    from app.invitations import INVITATION_EMAIL

    for locale in ("en", "fi"):
        _, body = INVITATION_EMAIL[locale]
        text = body.format(organization="N", url="https://x/invitations/t", privacy_url="https://x/legal/privacy")
        assert "https://x/legal/privacy" in text and "Lupaus Palvelut Oy" in text
