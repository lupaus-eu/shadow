"""Restore an earlier version of an Event (Yearclock V2, P4 ticket 03)."""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.label_routes import LABEL_COLORS
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login
from test_platform_operations import _platform_app, platform_login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _world(stack, database_url, subject):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=5)
    base = f"/api/v1/organizations/{organization_id}"
    clock = owner.get(base).json()["yearclocks"][0]
    return application, owner, organization_id, base, clock


def _history(client, url, event_id):
    return client.get(f"{url}/events/{event_id}/history").json()["items"]


def test_restoring_returns_to_an_earlier_version_as_a_new_one(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "restore-owner")
    url = f"{base}/yearclocks/{clock['id']}"
    lane = clock["lanes"][0]["id"]
    board = owner.post(f"{url}/categories", json={"name": "Board", "color": "#336699"}).json()
    other = owner.post(f"{url}/categories", json={"name": "Other", "color": "#aa5500"}).json()
    budget = owner.post(f"{base}/labels", json={"name": "Budget", "color": LABEL_COLORS[0]}).json()
    event = owner.post(f"{url}/events", json={"title": "Budget review", "lane_id": lane, "starts_on": "2026-03-10", "category_id": board["id"], "label_ids": [budget["id"]], "description": "Old"}).json()
    owner.patch(f"{url}/events/{event['id']}", json={"title": "Budget review!", "lane_id": lane, "starts_on": "2026-03-17", "category_id": other["id"], "label_ids": [], "description": "New", "expected_version": 1})
    original = _history(owner, url, event["id"])[-1]

    preview = owner.get(f"{url}/events/{event['id']}/history/{original['id']}/restore-preview").json()
    assert [change["field"] for change in preview["changes"]] == ["title", "starts_on", "category_id", "label_ids", "description"]
    assert preview["changes"][2]["after"] == {"id": board["id"], "name": "Board"} and preview["category_removed"] is False and preview["lane_missing"] is False
    stale = owner.post(f"{url}/events/{event['id']}/history/{original['id']}/restore", json={"expected_version": 1})
    assert stale.status_code == 409
    restored = owner.post(f"{url}/events/{event['id']}/history/{original['id']}/restore", json={"expected_version": 2})
    assert restored.status_code == 200, restored.text
    restored = restored.json()
    assert (restored["title"], restored["starts_on"], restored["category_id"], restored["label_ids"], restored["description"], restored["version"]) == ("Budget review", "2026-03-10", board["id"], [budget["id"]], "Old", 3)
    entries = _history(owner, url, event["id"])
    assert [(item["kind"], item["reason"]) for item in entries] == [("version_restored", "restore"), ("updated", "edit"), ("created", "edit")]
    audit = next(item for item in owner.get(f"{base}/audit-events", params={"prefix": "event"}).json()["items"] if item["action"] == "event.version_restored")
    assert audit["change_summary"]["fields"] == ["title", "starts_on", "category_id", "label_ids", "description"]


def test_missing_references_are_left_out_or_chosen(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "restore-missing")
    url = f"{base}/yearclocks/{clock['id']}"
    general = clock["lanes"][0]["id"]
    temporary = owner.post(f"{url}/lanes", json={"name": "Temporary"}).json()
    category = owner.post(f"{url}/categories", json={"name": "Gone", "color": "#336699"}).json()
    label = owner.post(f"{base}/labels", json={"name": "Gone too", "color": LABEL_COLORS[0]}).json()
    event = owner.post(f"{url}/events", json={"title": "Moved", "lane_id": temporary["id"], "starts_on": "2026-03-10", "category_id": category["id"], "label_ids": [label["id"]]}).json()
    owner.patch(f"{url}/events/{event['id']}", json={"title": "Moved", "lane_id": general, "starts_on": "2026-03-10", "category_id": category["id"], "label_ids": [label["id"]], "expected_version": 1})
    first = _history(owner, url, event["id"])[-1]
    owner.delete(f"{url}/lanes/{temporary['id']}?expected_version={temporary['version']}")
    owner.delete(f"{url}/categories/{category['id']}?expected_version=1&confirm=true")
    owner.delete(f"{base}/labels/{label['id']}?expected_version=1&confirm=true")
    preview = owner.get(f"{url}/events/{event['id']}/history/{first['id']}/restore-preview").json()
    assert preview["lane_missing"] is True and preview["category_removed"] is True and preview["labels_removed"] == 1 and preview["changes"] == []
    version = owner.get(f"{url}/events", params={"window_start": "2026-01-01"}).json()[0]["version"]
    assert owner.post(f"{url}/events/{event['id']}/history/{first['id']}/restore", json={"expected_version": version}).json()["detail"] == {"reason": "lane_required"}
    second = owner.post(f"{url}/lanes", json={"name": "Chosen"}).json()
    done = owner.post(f"{url}/events/{event['id']}/history/{first['id']}/restore", json={"expected_version": version, "lane_id": second["id"]})
    assert done.status_code == 200 and done.json()["lane_id"] == second["id"] and done.json()["category_id"] is None and done.json()["label_ids"] == []


def test_restore_is_refused_by_role_state_and_kind(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "restore-refused")
    url = f"{base}/yearclocks/{clock['id']}"
    lane = clock["lanes"][0]["id"]
    event = owner.post(f"{url}/events", json={"title": "One", "lane_id": lane, "starts_on": "2026-03-10"}).json()
    owner.patch(f"{url}/events/{event['id']}", json={"title": "Two", "lane_id": lane, "starts_on": "2026-03-10", "expected_version": 1})
    first = _history(owner, url, event["id"])[-1]
    body = {"expected_version": 2}
    viewer_app, viewer_id = join(application, owner, organization_id, subject="restore-viewer", email="restore-viewer@example.com")
    owner.put(f"{url}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    with TestClient(viewer_app) as viewer:
        login(viewer)
        assert viewer.post(f"{url}/events/{event['id']}/history/{first['id']}/restore", json=body).status_code == 403
        assert viewer.get(f"{url}/events/{event['id']}/history/{first['id']}/restore-preview").status_code == 403

    series = owner.post(f"{url}/series", json={"title": "Weekly", "lane_id": lane, "starts_on": "2026-01-05", "frequency": "WEEKLY"}).json()
    occurrence = next(item for item in owner.get(f"{url}/events", params={"window_start": "2026-01-01"}).json() if item["series_id"] == series["id"])
    revision = _history(owner, url, occurrence["id"])[-1]
    assert owner.post(f"{url}/events/{occurrence['id']}/history/{revision['id']}/restore", json={"expected_version": occurrence["version"]}).json()["detail"]["reason"] == "recurring_occurrence"

    team = owner.post(f"{base}/yearclocks", json={"name": "Team"}).json()
    linked_event = owner.post(f"{base}/yearclocks/{team['id']}/events", json={"title": "Team plan", "lane_id": team["lanes"][0]["id"], "starts_on": "2026-03-01"}).json()
    owner.post(f"{url}/lanes/link", json={"source_lane_id": team["lanes"][0]["id"]})
    linked_revision = _history(owner, url, linked_event["id"])[-1]
    assert owner.post(f"{url}/events/{linked_event['id']}/history/{linked_revision['id']}/restore", json={"expected_version": 1}).json()["detail"]["reason"] == "linked_event"

    other = owner.post(f"{url}/events", json={"title": "Other", "lane_id": lane, "starts_on": "2026-04-01"}).json()
    assert owner.post(f"{url}/events/{other['id']}/history/{first['id']}/restore", json={"expected_version": 1}).status_code == 404
    owner.delete(f"{url}/events/{other['id']}?expected_version=1")
    assert owner.post(f"{url}/events/{other['id']}/history/{_history(owner, url, other['id'])[-1]['id']}/restore", json={"expected_version": 2}).json()["detail"]["reason"] == "deleted"

    agent = stack.enter_context(TestClient(_platform_app(database_url, "restore-agent", "support_agent")))
    platform_login(agent)
    assert agent.post(f"{url}/events/{event['id']}/history/{first['id']}/restore", json=body).status_code in {401, 403, 404}
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert owner.post(f"{url}/events/{event['id']}/history/{first['id']}/restore", json=body).status_code == 403
    assert owner.get(f"{url}/events/{event['id']}/history").status_code == 200
