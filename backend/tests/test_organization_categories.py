"""Organization Categories (Yearclock V2, P2 ticket 05)."""
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
    organization_id = active_org(owner, verifier, seats=4)
    base = f"/api/v1/organizations/{organization_id}"
    first = owner.get(base).json()["yearclocks"][0]
    second = owner.post(f"{base}/yearclocks", json={"name": "HR year"}).json()
    return application, owner, organization_id, base, first, second


def test_organization_categories_are_shared_locked_and_deleted_with_confirmation(database_url, stack) -> None:
    application, owner, organization_id, base, first, second = _world(stack, database_url, "org-categories-owner")
    board = owner.post(f"{base}/categories", json={"name": "Board", "color": "#1f5f99"})
    hr = owner.post(f"{base}/categories", json={"name": "HR", "color": "#2e7d32"}).json()
    assert board.status_code == 201 and board.json()["scope"] == "organization"
    board = board.json()
    assert owner.post(f"{base}/categories", json={"name": "board", "color": "#000000"}).json()["detail"] == {"reason": "duplicate_name"}
    local = owner.post(f"{base}/yearclocks/{first['id']}/categories", json={"name": "Local", "color": "#336699"}).json()

    listed = owner.get(f"{base}/yearclocks/{first['id']}/categories").json()
    other = owner.get(f"{base}/yearclocks/{second['id']}/categories").json()
    assert [(item["name"], item["scope"]) for item in listed] == [("Board", "organization"), ("HR", "organization"), ("Local", "yearclock")]
    assert [item["name"] for item in other] == ["Board", "HR"]

    events = []
    for clock in (first, second):
        response = owner.post(f"{base}/yearclocks/{clock['id']}/events", json={"title": f"{clock['name']} review", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01", "category_id": board["id"]})
        assert response.status_code == 201, response.text
        events.append(response.json())
    foreign_local = owner.post(f"{base}/yearclocks/{second['id']}/events", json={"title": "Wrong", "lane_id": second["lanes"][0]["id"], "starts_on": "2026-10-01", "category_id": local["id"]})
    assert foreign_local.status_code == 422

    # Editors change Categories from the Yearclock only when they are the Yearclock's own.
    assert owner.patch(f"{base}/yearclocks/{first['id']}/categories/{board['id']}", json={"name": "Renamed", "color": "#000000", "expected_version": 1}).status_code == 404
    assert owner.delete(f"{base}/yearclocks/{first['id']}/categories/{board['id']}?expected_version=1&confirm=true").status_code == 404

    usage = {item["name"]: item["usage"] for item in owner.get(f"{base}/categories").json()}
    assert usage == {"Board": 2, "HR": 0}
    reordered = owner.put(f"{base}/categories/order", json={"ordered_ids": [hr["id"], board["id"]], "expected_versions": {hr["id"]: 1, board["id"]: 1}})
    assert [item["name"] for item in reordered.json()] == ["HR", "Board"]
    board_version = next(item for item in reordered.json() if item["id"] == board["id"])["version"]
    unconfirmed = owner.delete(f"{base}/categories/{board['id']}?expected_version={board_version}")
    assert unconfirmed.status_code == 409 and unconfirmed.json()["detail"] == {"reason": "confirmation_required", "usage": 2}
    assert owner.delete(f"{base}/categories/{board['id']}?expected_version={board_version}&confirm=true").status_code == 204
    for clock, event in zip((first, second), events):
        refreshed = next(item for item in owner.get(f"{base}/yearclocks/{clock['id']}/events", params={"window_start": "2026-09-01"}).json() if item["id"] == event["id"])
        assert refreshed["category_id"] is None and refreshed["version"] == 2
    removed = next(item for item in owner.get(f"{base}/audit-events", params={"prefix": "category"}).json()["items"] if item["action"] == "category.removed")
    assert removed["change_summary"] == {"name": "Board", "uncategorized_events": 2, "scope": "organization"}


def test_only_owners_and_admins_manage_and_limits_hold(database_url, stack, monkeypatch) -> None:
    application, owner, organization_id, base, first, _ = _world(stack, database_url, "org-categories-roles")
    admin_app, _ = join(application, owner, organization_id, subject="org-categories-admin", email="org-categories-admin@example.com", role="admin")
    editor_app, editor_id = join(application, owner, organization_id, subject="org-categories-editor", email="org-categories-editor@example.com")
    owner.put(f"{base}/yearclocks/{first['id']}/access", json={"user_account_id": editor_id, "role": "editor"})
    with TestClient(admin_app) as admin:
        login(admin)
        assert admin.post(f"{base}/categories", json={"name": "Finance", "color": "#1f5f99"}).status_code == 201
    finance = owner.get(f"{base}/categories").json()[0]
    with TestClient(editor_app) as editor:
        login(editor)
        assert [item["name"] for item in editor.get(f"{base}/categories").json()] == ["Finance"]
        assert editor.post(f"{base}/categories", json={"name": "Nope", "color": "#1f5f99"}).status_code == 403
        assert editor.patch(f"{base}/categories/{finance['id']}", json={"name": "Nope", "color": "#1f5f99", "expected_version": 1}).status_code == 403
        assert editor.delete(f"{base}/categories/{finance['id']}?expected_version=1&confirm=true").status_code == 403
        used = editor.post(f"{base}/yearclocks/{first['id']}/events", json={"title": "Editor event", "lane_id": first["lanes"][0]["id"], "starts_on": "2026-10-01", "category_id": finance["id"]})
        assert used.status_code == 201

    monkeypatch.setenv("LIMIT_ORGANIZATION_CATEGORIES", "1")
    limited = owner.post(f"{base}/categories", json={"name": "Second", "color": "#1f5f99"})
    assert limited.status_code == 409 and limited.json()["detail"]["limit"] == "organization_categories"
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert owner.patch(f"{base}/categories/{finance['id']}", json={"name": "Finance 2", "color": "#1f5f99", "expected_version": 1}).status_code == 403
    assert len(owner.get(f"{base}/categories").json()) == 1
