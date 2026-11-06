from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, invitation_token, join, login


def test_only_owners_can_grant_or_change_ownership(database_url: str) -> None:
    verifier = Verifier()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("owner", "owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        invitation = owner.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "new-owner@example.com", "role": "owner"})
    assert invitation.status_code == 201
    token = invitation_token(owner_app.state.database_engine, invitation.json()["id"])
    new_owner_app = create_app(database_url=database_url, oidc_client=OIDC("new-owner", "new-owner@example.com"), clock=lambda: NOW)
    with TestClient(new_owner_app) as new_owner:
        login(new_owner)
        assert new_owner.post("/api/v1/invitations/accept", json={"token": token}).status_code == 200
        memberships = new_owner.get(f"/api/v1/organizations/{organization_id}/memberships")
        new_owner_id = new_owner.get("/api/v1/auth/session").json()["user_account"]["id"]
        original = next(item for item in memberships.json() if item["user_account_id"] != new_owner_id)
        changed = new_owner.patch(f"/api/v1/organizations/{organization_id}/memberships/{original['id']}", json={"role": "admin", "expected_version": original["version"]})
    assert changed.status_code == 200
    with TestClient(owner_app) as former_owner:
        login(former_owner)
        assert former_owner.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "blocked@example.com", "role": "owner"}).status_code == 403


def test_last_owner_cannot_leave_or_be_removed(database_url: str) -> None:
    verifier = Verifier()
    app = create_app(database_url=database_url, oidc_client=OIDC("sole-owner", "sole@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        membership = owner.get(f"/api/v1/organizations/{organization_id}/memberships").json()[0]
        response = owner.delete(f"/api/v1/organizations/{organization_id}/memberships/{membership['id']}?expected_version={membership['version']}")
    assert response.status_code == 409


def test_admin_cannot_invite_an_owner(database_url: str) -> None:
    verifier = Verifier()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("inviting-owner", "inviting-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        invitation = owner.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "admin@example.com", "role": "admin"})
    assert invitation.status_code == 201
    token = invitation_token(owner_app.state.database_engine, invitation.json()["id"])
    admin_app = create_app(database_url=database_url, oidc_client=OIDC("admin", "admin@example.com"), clock=lambda: NOW)
    with TestClient(admin_app) as admin:
        login(admin)
        assert admin.post("/api/v1/invitations/accept", json={"token": token}).status_code == 200
        response = admin.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "owner@example.com", "role": "owner"})
    assert response.status_code == 403


def _membership_of(client: TestClient, organization_id: str, user_id: str) -> dict:
    return next(item for item in client.get(f"/api/v1/organizations/{organization_id}/memberships").json() if item["user_account_id"] == user_id)


def test_member_cannot_list_change_or_remove_memberships_but_can_leave(database_url: str) -> None:
    verifier = Verifier()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("roles-owner", "roles-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier, seats=3)
        member_app, member_id = join(owner_app, owner, organization_id, subject="roles-member", email="roles-member@example.com")
        other_app, other_id = join(owner_app, owner, organization_id, subject="roles-other", email="roles-other@example.com")
        listed = owner.get(f"/api/v1/organizations/{organization_id}/memberships").json()
        mine = _membership_of(owner, organization_id, member_id)
        other = _membership_of(owner, organization_id, other_id)
    assert {item["email"] for item in listed} == {"roles-owner@example.com", "roles-member@example.com", "roles-other@example.com"}

    with TestClient(member_app) as member:
        login(member)
        members_path = f"/api/v1/organizations/{organization_id}/memberships"
        assert member.get(members_path).status_code == 403
        self_promotion = member.patch(f"{members_path}/{mine['id']}", json={"role": "admin", "expected_version": mine["version"]})
        other_promotion = member.patch(f"{members_path}/{other['id']}", json={"role": "admin", "expected_version": other["version"]})
        removal = member.delete(f"{members_path}/{other['id']}?expected_version={other['version']}")
        leaving = member.delete(f"{members_path}/{mine['id']}?expected_version={mine['version']}")
    assert self_promotion.status_code == 403
    assert other_promotion.status_code == 403
    assert removal.status_code == 403
    assert leaving.status_code == 204

    with TestClient(owner_app) as owner:
        login(owner)
        remaining = {item["user_account_id"]: item["role"] for item in owner.get(f"/api/v1/organizations/{organization_id}/memberships").json()}
    with owner_app.state.database_engine.connect() as connection:
        audit = connection.execute(text("SELECT action FROM audit_events WHERE organization_id = :id"), {"id": organization_id}).scalars().all()
    assert member_id not in remaining
    assert remaining[other_id] == "member"
    assert "organization.membership_left" in audit


def test_admin_manages_other_admins_but_not_owners(database_url: str) -> None:
    verifier = Verifier()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("admins-owner", "admins-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier, seats=3)
        admin_app, _admin_id = join(owner_app, owner, organization_id, subject="admins-first", email="admins-first@example.com", role="admin")
        _second_app, second_id = join(owner_app, owner, organization_id, subject="admins-second", email="admins-second@example.com", role="admin")
        owner_id = owner.get("/api/v1/auth/session").json()["user_account"]["id"]
    members_path = f"/api/v1/organizations/{organization_id}/memberships"
    with TestClient(admin_app) as admin:
        login(admin)
        second = _membership_of(admin, organization_id, second_id)
        demoted = admin.patch(f"{members_path}/{second['id']}", json={"role": "member", "expected_version": second["version"]})
        promoted = admin.patch(f"{members_path}/{second['id']}", json={"role": "admin", "expected_version": demoted.json()["version"]})
        owner_membership = _membership_of(admin, organization_id, owner_id)
        to_owner = admin.patch(f"{members_path}/{second['id']}", json={"role": "owner", "expected_version": promoted.json()["version"]})
        demote_owner = admin.patch(f"{members_path}/{owner_membership['id']}", json={"role": "admin", "expected_version": owner_membership["version"]})
        remove_owner = admin.delete(f"{members_path}/{owner_membership['id']}?expected_version={owner_membership['version']}")
        removed = admin.delete(f"{members_path}/{second['id']}?expected_version={promoted.json()['version']}")
    assert demoted.status_code == 200 and demoted.json()["role"] == "member"
    assert promoted.status_code == 200 and promoted.json()["role"] == "admin"
    assert to_owner.status_code == 403
    assert demote_owner.status_code == 403
    assert remove_owner.status_code == 403
    assert removed.status_code == 204


