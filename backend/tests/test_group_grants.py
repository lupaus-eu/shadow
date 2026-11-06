"""Group grants (Yearclock V2, P10a ticket 04)."""
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
    clock = owner.get(base).json()["yearclocks"][0]
    return application, owner, organization_id, base, clock


def _membership(client, base, user_id):
    return next(item for item in client.get(f"{base}/memberships").json() if item["user_account_id"] == user_id)


def _role(client, base, clock_id):
    return next((item["access_role"] for item in client.get(base).json()["yearclocks"] if item["id"] == clock_id), None)


def test_group_access_follows_membership_and_the_strongest_source_wins(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "grants-owner")
    url = f"{base}/yearclocks/{clock['id']}"
    finance = owner.post(f"{base}/groups", json={"name": "Finance"}).json()
    first_app, first_id = join(application, owner, organization_id, subject="grants-first", email="grants-first@example.com")
    second_app, second_id = join(application, owner, organization_id, subject="grants-second", email="grants-second@example.com")
    first, second = _membership(owner, base, first_id), _membership(owner, base, second_id)
    owner.put(f"{base}/groups/{finance['id']}/members/{first['id']}")
    granted = owner.put(f"{url}/group-access", json={"group_id": finance["id"], "role": "editor"})
    assert granted.status_code == 200 and granted.json()["role"] == "editor"
    assert owner.get(f"{url}/group-access").json() == [{"group_id": finance["id"], "name": "Finance", "role": "editor", "version": 1}]
    with TestClient(first_app) as client:
        login(client)
        assert _role(client, base, clock["id"]) == "editor"
        assert client.post(f"{url}/events", json={"title": "Budget", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-03-01"}).status_code == 201
        assert client.get(f"{base}/me/groups").json() == [{"id": finance["id"], "name": "Finance", "access": [{"yearclock_id": clock["id"], "yearclock_name": clock["name"], "role": "editor"}]}]
    with TestClient(second_app) as client:
        login(client)
        assert _role(client, base, clock["id"]) is None
        owner.put(f"{base}/groups/{finance['id']}/members/{second['id']}")
        assert _role(client, base, clock["id"]) == "editor"
        owner.put(f"{url}/access", json={"user_account_id": second_id, "role": "viewer"})
        owner.put(f"{url}/group-access", json={"group_id": finance["id"], "role": "viewer", "expected_version": 1})
        assert _role(client, base, clock["id"]) == "viewer"
        assert client.post(f"{url}/events", json={"title": "Nope", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-03-02"}).status_code == 403
        assert client.put(f"{url}/group-access", json={"group_id": finance["id"], "role": "editor", "expected_version": 2}).status_code == 403

    impact = owner.delete(f"{base}/groups/{finance['id']}?expected_version={owner.get(f'{base}/groups').json()[0]['version']}")
    assert impact.status_code == 409 and impact.json()["detail"] == {"reason": "confirmation_required", "members": 2, "yearclocks": 1, "losing_access": [{"name": "grants-first", "yearclock_name": clock["name"]}]}
    owner.delete(f"{base}/groups/{finance['id']}/members/{first['id']}")
    with TestClient(first_app) as client:
        login(client)
        assert _role(client, base, clock["id"]) is None and client.get(f"{url}/events").status_code == 403
    assert owner.delete(f"{url}/group-access/{finance['id']}?expected_version=2").status_code == 204
    actions = [item["action"] for item in owner.get(f"{base}/audit-events", params={"prefix": "yearclock"}).json()["items"]]
    assert actions.count("yearclock.group_access_granted") == 2 and actions.count("yearclock.group_access_revoked") == 1


def test_group_access_reaches_linked_lanes_search_and_stops_when_read_only(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "grants-linked")
    team = owner.post(f"{base}/yearclocks", json={"name": "Team"}).json()
    owner.post(f"{base}/yearclocks/{team['id']}/events", json={"title": "Team sprint", "lane_id": team["lanes"][0]["id"], "starts_on": "2026-03-01"})
    owner.post(f"{base}/yearclocks/{clock['id']}/lanes/link", json={"source_lane_id": team["lanes"][0]["id"]})
    readers = owner.post(f"{base}/groups", json={"name": "Readers"}).json()
    member_app, member_id = join(application, owner, organization_id, subject="grants-reader", email="grants-reader@example.com")
    owner.put(f"{base}/groups/{readers['id']}/members/{_membership(owner, base, member_id)['id']}")
    owner.put(f"{base}/yearclocks/{clock['id']}/group-access", json={"group_id": readers["id"], "role": "viewer"})
    with TestClient(member_app) as client:
        login(client)
        search = lambda: [item["title"] for item in client.get(f"{base}/yearclocks/{clock['id']}/search", params={"q": "sprint"}).json()["items"]]
        assert search() == []
        owner.put(f"{base}/yearclocks/{team['id']}/group-access", json={"group_id": readers["id"], "role": "viewer"})
        assert search() == ["Team sprint"]
    other = owner.post(f"{base}/yearclocks", json={"name": "Other"}).json()
    foreign_verifier = Verifier()
    stranger = create_app(database_url=database_url, oidc_client=OIDC("grants-stranger", "grants-stranger@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=foreign_verifier, clock=lambda: NOW)
    with TestClient(stranger) as foreign:
        login(foreign)
        foreign_org = active_org(foreign, foreign_verifier)
        foreign_group = foreign.post(f"/api/v1/organizations/{foreign_org}/groups", json={"name": "Foreign"}).json()
    assert owner.put(f"{base}/yearclocks/{other['id']}/group-access", json={"group_id": foreign_group["id"], "role": "viewer"}).status_code == 422
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert owner.put(f"{base}/yearclocks/{other['id']}/group-access", json={"group_id": readers["id"], "role": "viewer"}).status_code == 403
    assert len(owner.get(f"{base}/yearclocks/{clock['id']}/group-access").json()) == 1
