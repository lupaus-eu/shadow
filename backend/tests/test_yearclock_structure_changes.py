"""Category and Lane structure changes (ticket 11)."""
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


def test_categories_are_versioned_audited_and_leave_events_uncategorized(database_url: str) -> None:
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC("categories-owner", "categories-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        yearclock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        base = f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}"
        board = client.post(f"{base}/categories", json={"name": "Board", "color": "#336699"}).json()
        audit = client.post(f"{base}/categories", json={"name": "Audit"}).json()
        invalid_color = client.post(f"{base}/categories", json={"name": "Bad", "color": "blue"})
        recolored = client.patch(f"{base}/categories/{board['id']}", json={"name": "Board of directors", "color": "#663399", "expected_version": 1})
        stale_rename = client.patch(f"{base}/categories/{board['id']}", json={"name": "Lost", "expected_version": 1})
        versions = {board["id"]: recolored.json()["version"], audit["id"]: audit["version"]}
        reordered = client.put(f"{base}/categories/order", json={"ordered_ids": [audit["id"], board["id"]], "expected_versions": versions})
        stale_order = client.put(f"{base}/categories/order", json={"ordered_ids": [board["id"], audit["id"]], "expected_versions": versions})
        event = client.post(f"{base}/events", json={"title": "Board meeting", "lane_id": yearclock["lanes"][0]["id"], "category_id": board["id"], "starts_on": "2026-05-05"}).json()
        latest_board = next(item for item in client.get(f"{base}/categories").json() if item["id"] == board["id"])
        unconfirmed = client.delete(f"{base}/categories/{board['id']}?expected_version={latest_board['version']}")
        removed = client.delete(f"{base}/categories/{board['id']}?expected_version={latest_board['version']}&confirm=true")
        after = next(item for item in client.get(f"{base}/events?window_start=2026-01-01").json() if item["id"] == event["id"])
    assert invalid_color.status_code == 422
    assert recolored.status_code == 200 and recolored.json()["color"] == "#663399"
    assert stale_rename.status_code == 409
    assert [item["name"] for item in reordered.json()] == ["Audit", "Board of directors"]
    assert stale_order.status_code == 409
    assert unconfirmed.status_code == 400
    assert removed.status_code == 204
    assert after["category_id"] is None and after["version"] == 2
    with application.state.database_engine.connect() as connection:
        actions = connection.execute(text("SELECT action FROM audit_events WHERE organization_id = :id AND action LIKE 'category.%'"), {"id": organization_id}).scalars().all()
    assert sorted(actions) == sorted(["category.created", "category.created", "category.updated", "category.reordered", "category.removed"])


def test_a_lane_with_events_is_removed_only_after_an_explicit_move(database_url: str) -> None:
    verifier = Verifier()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("lanes-owner", "lanes-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier, seats=3)
        editor_app, editor_id = join(owner_app, owner, organization_id, subject="lanes-editor", email="lanes-editor@example.com")
        viewer_app, viewer_id = join(owner_app, owner, organization_id, subject="lanes-viewer", email="lanes-viewer@example.com")
        yearclock = owner.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        base = f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}"
        owner.put(f"{base}/access", json={"user_account_id": editor_id, "role": "editor"})
        owner.put(f"{base}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    general = yearclock["lanes"][0]
    with TestClient(editor_app) as editor:
        login(editor)
        finance = editor.post(f"{base}/lanes", json={"name": "Finance"}).json()
        event = editor.post(f"{base}/events", json={"title": "Close books", "lane_id": finance["id"], "starts_on": "2026-06-30"}).json()
        deleted = editor.post(f"{base}/events", json={"title": "Old draft", "lane_id": finance["id"], "starts_on": "2026-06-01"}).json()
        editor.delete(f"{base}/events/{deleted['id']}?expected_version=1")
        series = editor.post(f"{base}/series", json={"title": "Monthly close", "lane_id": finance["id"], "starts_on": "2026-01-31", "frequency": "MONTHLY"})
        blocked = editor.delete(f"{base}/lanes/{finance['id']}?expected_version={finance['version']}")
    assert series.status_code == 201
    assert blocked.status_code == 409 and blocked.json()["detail"]["reason"] == "lane_has_events"
    assert blocked.json()["detail"]["series"] == 1 and blocked.json()["detail"]["events"] >= 3

    with TestClient(viewer_app) as viewer:
        login(viewer)
        forbidden = viewer.post(f"{base}/lanes/{finance['id']}/move-events", json={"target_lane_id": general["id"], "expected_version": finance["version"]})
    assert forbidden.status_code == 403

    with TestClient(editor_app) as editor:
        login(editor)
        same_lane = editor.post(f"{base}/lanes/{finance['id']}/move-events", json={"target_lane_id": finance["id"], "expected_version": finance["version"]})
        moved = editor.post(f"{base}/lanes/{finance['id']}/move-events", json={"target_lane_id": general["id"], "expected_version": finance["version"]})
        removed = editor.delete(f"{base}/lanes/{finance['id']}?expected_version={moved.json()['lane']['version']}")
        lanes = [lane["name"] for lane in editor.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]["lanes"]]
        events = editor.get(f"{base}/events?window_start=2026-01-01").json()
        only_lane = editor.delete(f"{base}/lanes/{general['id']}?expected_version={moved.json()['target_lane']['version']}")
    assert same_lane.status_code == 422
    assert moved.status_code == 200 and moved.json()["moved_series"] == 1
    assert removed.status_code == 204
    assert lanes == ["General"]
    assert {item["lane_id"] for item in events} == {general["id"]}
    assert any(item["id"] == event["id"] and item["starts_on"] == "2026-06-30" for item in events)
    assert only_lane.status_code == 409 and only_lane.json()["detail"]["reason"] == "last_lane"


def test_structure_routes_reject_a_yearclock_from_another_organization(database_url: str) -> None:
    verifier = Verifier()
    first = create_app(database_url=database_url, oidc_client=OIDC("cross-first", "cross-first@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    second = create_app(database_url=database_url, oidc_client=OIDC("cross-second", "cross-second@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(second) as other:
        login(other)
        foreign_org = active_org(other, verifier)
        foreign_clock = other.get(f"/api/v1/organizations/{foreign_org}").json()["yearclocks"][0]
    with TestClient(first) as client:
        login(client)
        organization_id = active_org(client, verifier)
        base = f"/api/v1/organizations/{organization_id}/yearclocks/{foreign_clock['id']}"
        category = client.post(f"{base}/categories", json={"name": "Intrusion"})
        lane = client.post(f"{base}/lanes", json={"name": "Intrusion"})
        listed = client.get(f"{base}/categories")
    assert category.status_code == 404
    assert lane.status_code == 404
    assert listed.status_code == 404
