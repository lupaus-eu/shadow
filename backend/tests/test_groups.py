"""Groups (Yearclock V2, P10a ticket 03)."""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _world(stack, database_url, subject):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=6)
    base = f"/api/v1/organizations/{organization_id}"
    return application, owner, organization_id, base


def _membership(client, base, user_id):
    return next(item for item in client.get(f"{base}/memberships").json() if item["user_account_id"] == user_id)


def test_owners_and_admins_manage_groups_and_members_see_their_own(database_url, stack) -> None:
    application, owner, organization_id, base = _world(stack, database_url, "groups-owner")
    board = owner.post(f"{base}/groups", json={"name": "  Board  "})
    assert board.status_code == 201 and board.json()["name"] == "Board"
    board = board.json()
    assert owner.post(f"{base}/groups", json={"name": "board"}).json()["detail"] == {"reason": "duplicate_name"}
    admin_app, admin_id = join(application, owner, organization_id, subject="groups-admin", email="groups-admin@example.com", role="admin")
    member_app, member_id = join(application, owner, organization_id, subject="groups-member", email="groups-member@example.com")
    member = _membership(owner, base, member_id)
    with TestClient(admin_app) as admin:
        login(admin)
        finance = admin.post(f"{base}/groups", json={"name": "Finance team"}).json()
        added = admin.put(f"{base}/groups/{finance['id']}/members/{member['id']}")
        assert added.status_code == 200 and [item["name"] for item in added.json()["members"]] == ["groups-member"]
        admin.put(f"{base}/groups/{board['id']}/members/{member['id']}")
        renamed = admin.patch(f"{base}/groups/{finance['id']}", json={"name": "Finance", "expected_version": added.json()["version"]})
        assert renamed.json()["name"] == "Finance"
        assert admin.patch(f"{base}/groups/{finance['id']}", json={"name": "Again", "expected_version": 1}).status_code == 409
    listed = owner.get(f"{base}/groups").json()
    assert [(item["name"], len(item["members"])) for item in listed] == [("Board", 1), ("Finance", 1)]
    with TestClient(member_app) as client:
        login(client)
        assert client.get(f"{base}/groups").status_code == 403
        assert client.post(f"{base}/groups", json={"name": "Mine"}).status_code == 403
        assert [item["name"] for item in client.get(f"{base}/me/groups").json()] == ["Board", "Finance"]
    removed = owner.delete(f"{base}/groups/{finance['id']}/members/{member['id']}").json()
    assert removed["members"] == []
    unconfirmed = owner.delete(f"{base}/groups/{board['id']}?expected_version={owner.get(f'{base}/groups').json()[0]['version']}")
    assert unconfirmed.status_code == 409 and unconfirmed.json()["detail"] == {"reason": "confirmation_required", "members": 1, "yearclocks": 0, "losing_access": []}
    version = owner.get(f"{base}/groups").json()[0]["version"]
    assert owner.delete(f"{base}/groups/{board['id']}?expected_version={version}&confirm=true").status_code == 204
    empty = owner.get(f"{base}/groups").json()[0]
    assert owner.delete(f"{base}/groups/{empty['id']}?expected_version={empty['version']}").status_code == 204
    actions = [item["action"] for item in owner.get(f"{base}/audit-events", params={"prefix": "group"}).json()["items"]]
    assert sorted(set(actions)) == ["group.created", "group.deleted", "group.member_added", "group.member_removed", "group.renamed"]


def test_limits_membership_removal_read_only_and_isolation(database_url, stack, monkeypatch) -> None:
    application, owner, organization_id, base = _world(stack, database_url, "groups-rules")
    group = owner.post(f"{base}/groups", json={"name": "Sales"}).json()
    _, member_id = join(application, owner, organization_id, subject="groups-leaver", email="groups-leaver@example.com")
    member = _membership(owner, base, member_id)
    owner.put(f"{base}/groups/{group['id']}/members/{member['id']}")
    assert owner.delete(f"{base}/memberships/{member['id']}", params={"expected_version": member["version"]}).status_code == 204
    assert owner.get(f"{base}/groups").json()[0]["members"] == []
    monkeypatch.setenv("LIMIT_GROUPS_PER_ORGANIZATION", "1")
    limited = owner.post(f"{base}/groups", json={"name": "Second"})
    assert limited.status_code == 409 and limited.json()["detail"]["limit"] == "groups_per_organization"
    monkeypatch.delenv("LIMIT_GROUPS_PER_ORGANIZATION")
    other_verifier = Verifier()
    stranger_app = create_app(database_url=database_url, oidc_client=OIDC("groups-stranger", "groups-stranger@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=other_verifier, clock=lambda: NOW)
    with TestClient(stranger_app) as stranger:
        login(stranger)
        other_org = active_org(stranger, other_verifier)
        other_group = stranger.post(f"/api/v1/organizations/{other_org}/groups", json={"name": "Foreign"}).json()
    assert owner.put(f"{base}/groups/{other_group['id']}/members/{_membership(owner, base, owner.get('/api/v1/auth/session').json()['user_account']['id'])['id']}").status_code == 404
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert owner.post(f"{base}/groups", json={"name": "Nope"}).status_code == 403
    assert owner.get(f"{base}/groups").status_code == 200
