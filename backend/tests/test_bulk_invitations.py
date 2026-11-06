"""Bulk invitations and invitation Groups (Yearclock V2, P10a ticket 05)."""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, invitation_token, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _world(stack, database_url, subject, seats):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=seats)
    return application, owner, organization_id, f"/api/v1/organizations/{organization_id}"


def test_the_preview_skips_what_cannot_be_invited_and_counts_seats(database_url, stack) -> None:
    application, owner, organization_id, base = _world(stack, database_url, "bulk-invite-owner", seats=3)
    join(application, owner, organization_id, subject="bulk-existing", email="existing@example.com")
    owner.post(f"{base}/invitations", json={"email": "pending@example.com"})
    emails = ["Ann@Example.com", "not-an-address", "ann@example.com", "existing@example.com", "pending@example.com", "ben@example.com", "cat@example.com"]
    preview = owner.post(f"{base}/invitations/bulk", json={"emails": emails, "role": "member"})
    assert preview.status_code == 200, preview.text
    assert preview.json() == {
        "invite": ["ann@example.com", "ben@example.com", "cat@example.com"],
        "skipped": [{"email": "not-an-address", "reason": "invalid"}, {"email": "ann@example.com", "reason": "duplicate"}, {"email": "existing@example.com", "reason": "member"}, {"email": "pending@example.com", "reason": "invited"}],
        "seats_needed": 3,
        "created": 0,
    }
    refused = owner.post(f"{base}/invitations/bulk", json={"emails": emails, "role": "member", "dry_run": False})
    assert refused.status_code == 409 and refused.json()["detail"] == {"reason": "seats_needed", "seats_needed": 3}
    assert [item["email"] for item in owner.get(f"{base}/invitations").json() if item["status"] == "pending"] == ["pending@example.com"]
    assert owner.post(f"{base}/invitations/bulk", json={"emails": [f"p{index}@example.com" for index in range(51)]}).status_code == 422


def test_bulk_invitations_join_groups_on_acceptance(database_url, stack) -> None:
    application, owner, organization_id, base = _world(stack, database_url, "bulk-groups-owner", seats=6)
    sales = owner.post(f"{base}/groups", json={"name": "Sales"}).json()
    temporary = owner.post(f"{base}/groups", json={"name": "Temporary"}).json()
    sent = owner.post(f"{base}/invitations/bulk", json={"emails": ["dan@example.com", "eve@example.com"], "role": "member", "group_ids": [sales["id"], temporary["id"]], "dry_run": False})
    assert sent.status_code == 200 and sent.json()["created"] == 2
    invitations = {item["email"]: item for item in owner.get(f"{base}/invitations").json()}
    assert owner.get(f"{base}/billing/seats").json()["reserved"] == 2
    owner.delete(f"{base}/groups/{temporary['id']}?expected_version=1&confirm=true")
    for email, subject in (("dan@example.com", "bulk-dan"), ("eve@example.com", "bulk-eve")):
        token = invitation_token(application.state.database_engine, invitations[email]["id"])
        member_app = create_app(database_url=str(application.state.database_engine.url.render_as_string(hide_password=False)), oidc_client=OIDC(subject, email), clock=lambda: NOW)
        with TestClient(member_app) as member:
            login(member)
            assert member.post("/api/v1/invitations/accept", json={"token": token}).status_code == 200
            assert [item["name"] for item in member.get(f"{base}/me/groups").json()] == ["Sales"]
    assert sorted(item["email"] for item in owner.get(f"{base}/groups").json()[0]["members"]) == ["dan@example.com", "eve@example.com"]
    single = owner.post(f"{base}/invitations", json={"email": "fay@example.com", "group_ids": [sales["id"]]})
    assert single.status_code == 201
    resent = owner.post(f"{base}/invitations/{single.json()['id']}/resend", params={"expected_version": single.json()["version"]}).json()
    token = invitation_token(application.state.database_engine, resent["id"])
    member_app = create_app(database_url=str(application.state.database_engine.url.render_as_string(hide_password=False)), oidc_client=OIDC("bulk-fay", "fay@example.com"), clock=lambda: NOW)
    with TestClient(member_app) as member:
        login(member)
        member.post("/api/v1/invitations/accept", json={"token": token})
        assert [item["name"] for item in member.get(f"{base}/me/groups").json()] == ["Sales"]
    audit = next(item for item in owner.get(f"{base}/audit-events", params={"prefix": "organization"}).json()["items"] if item["action"] == "organization.invitation_created" and item["change_summary"].get("email") == "fay@example.com")
    assert audit["change_summary"]["groups"] == ["Sales"]


def test_roles_foreign_groups_and_read_only(database_url, stack) -> None:
    application, owner, organization_id, base = _world(stack, database_url, "bulk-roles-owner", seats=6)
    admin_app, _ = join(application, owner, organization_id, subject="bulk-admin", email="bulk-admin@example.com", role="admin")
    member_app, _ = join(application, owner, organization_id, subject="bulk-member", email="bulk-member@example.com")
    with TestClient(admin_app) as admin:
        login(admin)
        assert admin.post(f"{base}/invitations/bulk", json={"emails": ["x@example.com"], "role": "member"}).status_code == 200
        assert admin.post(f"{base}/invitations/bulk", json={"emails": ["x@example.com"], "role": "owner"}).status_code == 403
    with TestClient(member_app) as member:
        login(member)
        assert member.post(f"{base}/invitations/bulk", json={"emails": ["x@example.com"]}).status_code == 403
    assert owner.post(f"{base}/invitations/bulk", json={"emails": ["x@example.com"], "group_ids": ["00000000-0000-4000-8000-000000000000"]}).status_code == 422
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert owner.post(f"{base}/invitations/bulk", json={"emails": ["x@example.com"]}).status_code == 403
