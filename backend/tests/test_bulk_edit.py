"""Bulk Edit (Yearclock V2, P3 ticket 02)."""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.label_routes import LABEL_COLORS
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
    clock = owner.get(base).json()["yearclocks"][0]
    second_lane = owner.post(f"{base}/yearclocks/{clock['id']}/lanes", json={"name": "Finance"}).json()
    url = f"{base}/yearclocks/{clock['id']}"
    return application, owner, organization_id, base, url, clock, second_lane


def _event(client, url, clock, title, **extra):
    response = client.post(f"{url}/events", json={"title": title, "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def _items(*events):
    return [{"id": event["id"], "expected_version": event["version"]} for event in events]


def _audit(client, base):
    return [item for item in client.get(f"{base}/audit-events", params={"prefix": "event"}).json()["items"] if "bulk_id" in (item["change_summary"] or {})]


def test_bulk_move_categorize_label_and_delete_are_audited_with_one_reference(database_url, stack) -> None:
    application, owner, _, base, url, clock, finance = _world(stack, database_url, "bulk-owner")
    board = owner.post(f"{base}/categories", json={"name": "Board", "color": "#1f5f99"}).json()
    draft = owner.post(f"{base}/labels", json={"name": "Draft", "color": LABEL_COLORS[0]}).json()
    final = owner.post(f"{base}/labels", json={"name": "Final", "color": LABEL_COLORS[1]}).json()
    first, second = _event(owner, url, clock, "First", label_ids=[draft["id"]]), _event(owner, url, clock, "Second")

    moved = owner.post(f"{url}/events/bulk", json={"items": _items(first, second), "action": "move", "lane_id": finance["id"]})
    assert moved.status_code == 200, moved.text
    moved = moved.json()
    assert moved["changed"] == 2 and {item["lane_id"] for item in moved["items"]} == {finance["id"]}
    first, second = moved["items"]
    labelled = owner.post(f"{url}/events/bulk", json={"items": _items(first, second), "action": "label", "add_label_ids": [final["id"]], "remove_label_ids": [draft["id"]]}).json()
    assert [sorted(item["label_ids"]) for item in labelled["items"]] == [[final["id"]], [final["id"]]]
    first, second = labelled["items"]
    categorized = owner.post(f"{url}/events/bulk", json={"items": _items(first, second), "action": "categorize", "category_id": board["id"]}).json()
    assert {item["category_id"] for item in categorized["items"]} == {board["id"]}
    first, second = categorized["items"]
    unchanged = owner.post(f"{url}/events/bulk", json={"items": _items(first, second), "action": "categorize", "category_id": board["id"]}).json()
    assert unchanged["changed"] == 0 and [item["version"] for item in unchanged["items"]] == [first["version"], second["version"]]

    deleted = owner.post(f"{url}/events/bulk", json={"items": _items(first, second), "action": "delete"}).json()
    assert deleted["changed"] == 2 and all(item["deleted_at"] for item in deleted["items"])
    assert {item["id"] for item in owner.get(f"{url}/deleted-events").json()} >= {first["id"], second["id"]}
    restored = owner.post(f"{url}/events/{first['id']}/restore", params={"expected_version": deleted["items"][0]["version"]})
    assert restored.status_code == 200

    rows = _audit(owner, base)
    by_bulk = {}
    for row in rows: by_bulk.setdefault(row["change_summary"]["bulk_id"], []).append(row["action"])
    assert sorted(len(actions) for actions in by_bulk.values()) == [2, 2, 2, 2]
    assert {moved["bulk_id"], labelled["bulk_id"], categorized["bulk_id"], deleted["bulk_id"]} == set(by_bulk)
    assert by_bulk[deleted["bulk_id"]] == ["event.deleted", "event.deleted"]
    assert next(row for row in rows if row["change_summary"]["bulk_id"] == labelled["bulk_id"])["change_summary"]["labels_added"] == ["Final"]


def test_bulk_edit_is_all_or_nothing(database_url, stack, monkeypatch) -> None:
    application, owner, _, base, url, clock, finance = _world(stack, database_url, "bulk-atomic")
    first, second = _event(owner, url, clock, "First"), _event(owner, url, clock, "Second")
    owner.patch(f"{url}/events/{second['id']}", json={**{key: second[key] for key in ("title", "lane_id", "starts_on")}, "expected_version": 1})
    stale = owner.post(f"{url}/events/bulk", json={"items": _items(first, second), "action": "move", "lane_id": finance["id"]})
    assert stale.status_code == 409 and stale.json()["detail"] == {"reason": "stale", "ids": [second["id"]]}
    events = {item["id"]: item for item in owner.get(f"{url}/events", params={"window_start": "2026-01-01"}).json()}
    assert events[first["id"]]["lane_id"] == clock["lanes"][0]["id"] and events[first["id"]]["version"] == 1

    series = owner.post(f"{url}/series", json={"title": "Weekly", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-05", "frequency": "WEEKLY"}).json()
    occurrence = next(item for item in owner.get(f"{url}/events", params={"window_start": "2026-01-01"}).json() if item["series_id"] == series["id"])
    refused = owner.post(f"{url}/events/bulk", json={"items": _items(first, occurrence), "action": "delete"})
    assert refused.status_code == 422 and refused.json()["detail"]["reason"] == "recurring_occurrence"
    other = owner.post(f"{base}/yearclocks", json={"name": "Other"}).json()
    foreign = owner.post(f"{base}/yearclocks/{other['id']}/events", json={"title": "Foreign", "lane_id": other["lanes"][0]["id"], "starts_on": "2026-10-01"}).json()
    assert owner.post(f"{url}/events/bulk", json={"items": _items(first, foreign), "action": "delete"}).json()["detail"]["reason"] == "not_in_yearclock"
    assert owner.post(f"{url}/events/bulk", json={"items": _items(first), "action": "move", "lane_id": other["lanes"][0]["id"]}).status_code == 422

    limit = owner.post(f"{base}/labels", json={"name": "Many", "color": LABEL_COLORS[0]}).json()
    crowded = _event(owner, url, clock, "Crowded", label_ids=[owner.post(f"{base}/labels", json={"name": f"L{index}", "color": LABEL_COLORS[0]}).json()["id"] for index in range(10)])
    over = owner.post(f"{url}/events/bulk", json={"items": _items(first, crowded), "action": "label", "add_label_ids": [limit["id"]]})
    assert over.status_code == 409 and over.json()["detail"]["limit"] == "labels_per_event"
    assert next(item for item in owner.get(f"{url}/events", params={"window_start": "2026-01-01"}).json() if item["id"] == first["id"])["label_ids"] == []

    monkeypatch.setenv("LIMIT_BULK_EVENTS", "1")
    too_many = owner.post(f"{url}/events/bulk", json={"items": _items(first, crowded), "action": "delete"})
    assert too_many.status_code == 409 and too_many.json()["detail"] == {"reason": "limit_reached", "limit": "bulk_events", "maximum": 1}
    assert _audit(owner, base) == []


def test_only_editors_bulk_edit_and_read_only_refuses(database_url, stack) -> None:
    application, owner, organization_id, base, url, clock, finance = _world(stack, database_url, "bulk-roles")
    event = _event(owner, url, clock, "Shared")
    viewer_app, viewer_id = join(application, owner, organization_id, subject="bulk-viewer", email="bulk-viewer@example.com")
    editor_app, editor_id = join(application, owner, organization_id, subject="bulk-editor", email="bulk-editor@example.com")
    owner.put(f"{url}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    owner.put(f"{url}/access", json={"user_account_id": editor_id, "role": "editor"})
    body = {"items": _items(event), "action": "move", "lane_id": finance["id"]}
    with TestClient(viewer_app) as viewer:
        login(viewer)
        assert viewer.post(f"{url}/events/bulk", json=body).status_code == 403
    with TestClient(editor_app) as editor:
        login(editor)
        assert editor.post(f"{url}/events/bulk", json=body).status_code == 200
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert owner.post(f"{url}/events/bulk", json={"items": [{"id": event["id"], "expected_version": 2}], "action": "delete"}).status_code == 403
