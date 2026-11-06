"""The access overview (Yearclock V2, P10a ticket 06)."""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def test_people_and_yearclocks_show_the_strongest_role_and_every_source(database_url, stack) -> None:
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC("overview-owner", "overview-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=6)
    base = f"/api/v1/organizations/{organization_id}"
    budget = owner.get(base).json()["yearclocks"][0]
    company = owner.post(f"{base}/yearclocks", json={"name": "Company"}).json()
    hidden = owner.post(f"{base}/yearclocks", json={"name": "Hidden"}).json()
    member_app, member_id = join(application, owner, organization_id, subject="overview-member", email="overview-member@example.com")
    admin_app, admin_id = join(application, owner, organization_id, subject="overview-admin", email="overview-admin@example.com", role="admin")
    memberships = {item["user_account_id"]: item for item in owner.get(f"{base}/memberships").json()}
    member = memberships[member_id]
    board = owner.post(f"{base}/groups", json={"name": "Board"}).json()
    owner.put(f"{base}/groups/{board['id']}/members/{member['id']}")
    owner.put(f"{base}/yearclocks/{budget['id']}/group-access", json={"group_id": board["id"], "role": "editor"})
    owner.put(f"{base}/yearclocks/{budget['id']}/access", json={"user_account_id": member_id, "role": "viewer"})
    version = next(item for item in owner.get(f"{base}/yearclocks").json() if item["id"] == company["id"])["version"]
    owner.put(f"{base}/yearclocks/{company['id']}/organization-access", json={"role": "viewer", "expected_version": version})

    person = owner.get(f"{base}/access-overview/people/{member['id']}")
    assert person.status_code == 200, person.text
    person = person.json()
    assert person["person"] == {"membership_id": member["id"], "name": "overview-member", "email": "overview-member@example.com", "organization_role": "member"}
    clocks = {item["name"]: item for item in person["yearclocks"]}
    assert set(clocks) == {budget["name"], "Company"} and "Hidden" not in clocks
    assert clocks[budget["name"]]["role"] == "editor"
    assert sorted((source["kind"], source["role"], source.get("group_name")) for source in clocks[budget["name"]]["sources"]) == [("direct", "viewer", None), ("group", "editor", "Board")]
    assert clocks["Company"]["sources"] == [{"kind": "organization", "role": "viewer", "organization_role": None, "group_id": None, "group_name": None}]

    admin = owner.get(f"{base}/access-overview/people/{memberships[admin_id]['id']}").json()
    assert {item["name"] for item in admin["yearclocks"]} == {budget["name"], "Company", "Hidden"}
    assert admin["yearclocks"][0]["sources"][0]["kind"] == "role" and admin["yearclocks"][0]["sources"][0]["organization_role"] == "admin"

    who = owner.get(f"{base}/access-overview/yearclocks/{hidden['id']}").json()
    assert [(item["name"], item["role"]) for item in who["people"]] == [("overview-admin", "editor"), ("overview-owner", "editor")]
    who = {item["name"]: item for item in owner.get(f"{base}/access-overview/yearclocks/{company['id']}").json()["people"]}
    assert who["overview-member"]["role"] == "viewer" and who["overview-member"]["sources"][0]["kind"] == "organization"

    with TestClient(member_app) as client:
        login(client)
        assert client.get(f"{base}/access-overview/people/{member['id']}").status_code == 403
        assert client.get(f"{base}/access-overview/yearclocks/{budget['id']}").status_code == 403
    with TestClient(admin_app) as client:
        login(client)
        assert client.get(f"{base}/access-overview/yearclocks/{budget['id']}").status_code == 200
    assert owner.get(f"{base}/access-overview/people/00000000-0000-4000-8000-000000000000").status_code == 404
    owner.delete(f"{base}/memberships/{member['id']}", params={"expected_version": member["version"]})
    assert owner.get(f"{base}/groups").json()[0]["members"] == []
    assert owner.get(f"{base}/yearclocks/{budget['id']}/access").json() == []
