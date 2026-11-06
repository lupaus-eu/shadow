"""Organization-wide Access (Yearclock V2, P10a ticket 02)."""
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


def _share(client, base, clock_id, role, **extra):
    version = next(item for item in client.get(f"{base}/yearclocks").json() if item["id"] == clock_id)["version"]
    return client.put(f"{base}/yearclocks/{clock_id}/organization-access", json={"role": role, "expected_version": version, **extra})


def test_sharing_reaches_current_and_future_members(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "share-owner")
    url = f"{base}/yearclocks/{clock['id']}"
    owner.post(f"{url}/events", json={"title": "Company day", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-06-01"})
    member_app, member_id = join(application, owner, organization_id, subject="share-member", email="share-member@example.com")
    with TestClient(member_app) as member:
        login(member)
        assert member.get(base).json()["yearclocks"] == []
        shared = _share(owner, base, clock["id"], "viewer")
        assert shared.status_code == 200 and shared.json()["organization_access"] == "viewer"
        seen = member.get(base).json()["yearclocks"]
        assert [(item["id"], item["access_role"]) for item in seen] == [(clock["id"], "viewer")]
        assert [item["title"] for item in member.get(f"{url}/events", params={"window_start": "2026-01-01"}).json()] == ["Company day"]
        assert member.post(f"{url}/events", json={"title": "Nope", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-06-02"}).status_code == 403
        assert member.get(f"{url}/search", params={"q": "company"}).json()["total"] == 1

        unconfirmed = _share(owner, base, clock["id"], "editor")
        assert unconfirmed.status_code == 409 and unconfirmed.json()["detail"] == {"reason": "confirmation_required", "members": 1}
        assert _share(owner, base, clock["id"], "editor", confirm=True).status_code == 200
        assert member.post(f"{url}/events", json={"title": "Now allowed", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-06-02"}).status_code == 201
        assert member.put(f"{url}/organization-access", json={"role": "none", "expected_version": 1}).status_code == 403

    later_app, _ = join(application, owner, organization_id, subject="share-later", email="share-later@example.com")
    with TestClient(later_app) as later:
        login(later)
        assert [item["access_role"] for item in later.get(base).json()["yearclocks"]] == ["editor"]
    owner.put(f"{url}/access", json={"user_account_id": member_id, "role": "viewer"})
    with TestClient(member_app) as member:
        login(member)
        assert member.get(base).json()["yearclocks"][0]["access_role"] == "editor"
        assert _share(owner, base, clock["id"], "none").status_code == 200
        assert member.get(base).json()["yearclocks"][0]["access_role"] == "viewer"
    audits = [item["change_summary"] for item in owner.get(f"{base}/audit-events", params={"prefix": "yearclock"}).json()["items"] if item["action"] == "yearclock.organization_access_changed"]
    assert audits == [{"from": "editor", "to": "none"}, {"from": "viewer", "to": "editor"}, {"from": "none", "to": "viewer"}]


def test_sharing_reaches_linked_lanes_and_respects_read_only(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "share-linked")
    team = owner.post(f"{base}/yearclocks", json={"name": "Team"}).json()
    owner.post(f"{base}/yearclocks/{team['id']}/events", json={"title": "Team plan", "lane_id": team["lanes"][0]["id"], "starts_on": "2026-03-01"})
    owner.post(f"{base}/yearclocks/{clock['id']}/lanes/link", json={"source_lane_id": team["lanes"][0]["id"]})
    _share(owner, base, clock["id"], "viewer")
    member_app, _ = join(application, owner, organization_id, subject="share-linked-member", email="share-linked-member@example.com")
    with TestClient(member_app) as member:
        login(member)
        events = lambda: [item["title"] for item in member.get(f"{base}/yearclocks/{clock['id']}/events", params={"window_start": "2026-01-01"}).json() if item["linked"]]
        assert events() == []
        _share(owner, base, team["id"], "viewer")
        assert events() == ["Team plan"]
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert _share(owner, base, clock["id"], "none").status_code == 403
