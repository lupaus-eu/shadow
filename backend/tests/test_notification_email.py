"""Notification email, settings, and Owner/Admin notices (Yearclock V2, P8 ticket 03)."""
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


def test_defaults_send_email_only_for_removed_access_and_notices(database_url, stack) -> None:
    world = World(stack, database_url, "ntfe-defaults")
    member, user_id, _ = world.person("member")
    grant = world.grant(user_id, "viewer")
    assert emails(world) == []  # in the app only
    assert world.owner.delete(f"{world.base}/access/{user_id}", params={"expected_version": grant["version"]}).status_code == 204
    [mail] = emails(world)
    payload = mail["payload"]
    assert payload["to"] == "ntfe-defaults-member@example.com"
    assert "You no longer have access to" in payload["subject"] and world.clock["name"] in payload["text"]
    assert f"{world.org.removeprefix('/api/v1')}/notifications" in payload["text"] and "/notification-settings" in payload["text"]
    assert "http" in payload["text"] and "pixel" not in payload["text"].lower()
    assert world.notices(member, "access_changed") == []  # the grant and its removal cancel out in the app, but the email was already sent


def test_settings_turn_channels_on_and_off_per_type(database_url, stack) -> None:
    world = World(stack, database_url, "ntfe-settings")
    member, user_id, _ = world.person("member")
    initial = {item["key"]: item for item in member.get(f"{world.org}/notification-settings").json()["items"]}
    assert set(initial) == {"access_changed", "access_removed", "role_changed", "invitation_accepted", "ownership_changed"}
    assert initial["access_changed"] == {"key": "access_changed", "audience": "everyone", "in_app": True, "email": False}
    assert initial["access_removed"]["email"] is True
    owner_keys = {item["key"] for item in world.owner.get(f"{world.org}/notification-settings").json()["items"]}
    assert {"support_access", "billing", "deletion"} <= owner_keys
    assert member.put(f"{world.org}/notification-settings", json={"settings": {"billing": {"in_app": True, "email": True}}}).status_code == 422
    assert member.put(f"{world.org}/notification-settings", json={"settings": {"nonsense": {"in_app": True, "email": True}}}).status_code == 422
    put_settings(member, world, access_changed={"in_app": True, "email": True}, role_changed={"in_app": False, "email": False})
    world.grant(user_id, "viewer")
    [mail] = emails(world)
    assert "You can now view" in mail["payload"]["subject"]
    membership = next(item for item in world.owner.get(f"{world.org}/memberships").json() if item["user_account_id"] == user_id)
    assert world.owner.patch(f"{world.org}/memberships/{membership['id']}", json={"role": "admin", "expected_version": membership["version"]}).status_code == 200
    assert world.notices(member, "role_changed") == []
    assert world.notices(member, "access_changed")
    assert member.get(f"{world.org}/notification-settings").json()["items"][0]["key"] == "access_changed"
    assert world.owner.get(f"{world.org}/notification-settings").status_code == 200


def test_the_email_is_in_the_recipients_language(database_url, stack) -> None:
    world = World(stack, database_url, "ntfe-language")
    member, user_id, _ = world.person("member")
    with world.application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE user_accounts SET locale = 'fi' WHERE id = :id"), {"id": user_id})
    put_settings(member, world, access_changed={"in_app": True, "email": True})
    world.grant(user_id, "editor")
    [mail] = emails(world)
    assert "Voit nyt muokata vuosikelloa" in mail["payload"]["subject"] and "Avaa ilmoituksesi" in mail["payload"]["text"]
    assert "Tietosuojaseloste: http" in mail["payload"]["text"] and mail["payload"]["text"].rstrip().endswith("/legal/privacy")


def test_at_most_the_daily_limit_of_emails_per_recipient_and_the_rest_stay_in_the_app(database_url, stack, monkeypatch) -> None:
    monkeypatch.setenv("LIMIT_NOTIFICATION_EMAILS_PER_DAY", "2")
    world = World(stack, database_url, "ntfe-cap")
    member, user_id, _ = world.person("member")
    put_settings(member, world, access_changed={"in_app": True, "email": True})
    for number in range(4):
        clock = world.owner.post(f"{world.org}/yearclocks", json={"name": f"Clock {number}"}).json()
        assert world.owner.put(f"{world.org}/yearclocks/{clock['id']}/access", json={"user_account_id": user_id, "role": "viewer"}).status_code == 200
    assert len(emails(world)) == 2
    assert len(world.notices(member, "access_changed")) == 4
    invitation_mails = emails(world, "organization.invitation")
    assert len(invitation_mails) == 1  # the member's own invitation is not counted


def test_the_worker_sends_notification_email_through_the_outbox(database_url, stack) -> None:
    world = World(stack, database_url, "ntfe-worker")
    member, user_id, _ = world.person("member")
    put_settings(member, world, access_changed={"in_app": True, "email": True})
    world.grant(user_id, "viewer")
    sender = Sender()
    factory = world.application.state.session_factory
    delivered = 0
    while deliver_one_email(factory, sender):
        delivered += 1
        assert delivered < 500
    topics = {message.recipient for message in sender.sent}
    assert "ntfe-worker-member@example.com" in topics
    assert any("You can now view" in message.subject for message in sender.sent)


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
