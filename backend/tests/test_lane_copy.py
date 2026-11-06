"""Copy a Lane from another Yearclock (Yearclock V2, P3 ticket 04)."""
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
    target = owner.get(base).json()["yearclocks"][0]
    source = owner.post(f"{base}/yearclocks", json={"name": "HR year"}).json()
    return application, owner, organization_id, base, source, target


def _events(client, base, clock, lane_id=None):
    items = client.get(f"{base}/yearclocks/{clock['id']}/events", params={"window_start": "2026-01-01"}).json()
    return [item for item in items if lane_id is None or item["lane_id"] == lane_id]


def test_a_lane_is_copied_with_events_series_and_matched_categories(database_url, stack) -> None:
    application, owner, _, base, source, target = _world(stack, database_url, "lane-copy-owner")
    src = f"{base}/yearclocks/{source['id']}"
    lane = source["lanes"][0]
    owner.patch(f"{src}/lanes/{lane['id']}", json={"name": "Onboarding", "tint": LABEL_COLORS[2], "height": "tall", "expected_version": lane["version"]})
    board = owner.post(f"{base}/categories", json={"name": "Board", "color": "#1f5f99"}).json()
    welcome = owner.post(f"{src}/categories", json={"name": "Welcome", "color": "#2e7d32"}).json()
    mentoring = owner.post(f"{src}/categories", json={"name": "Mentoring", "color": "#aa5500"}).json()
    existing = owner.post(f"{base}/yearclocks/{target['id']}/categories", json={"name": "mentoring", "color": "#000000"}).json()
    label = owner.post(f"{base}/labels", json={"name": "People", "color": LABEL_COLORS[0]}).json()
    owner.post(f"{src}/events", json={"title": "First day", "lane_id": lane["id"], "starts_on": "2026-03-02", "category_id": welcome["id"], "label_ids": [label["id"]], "description": "Laptop", "links": [{"title": "Day", "url": "https://example.com/day"}]})
    owner.post(f"{src}/events", json={"title": "Mentor match", "lane_id": lane["id"], "starts_on": "2026-03-09", "ends_on": "2026-03-13", "category_id": mentoring["id"]})
    owner.post(f"{src}/events", json={"title": "Board intro", "lane_id": lane["id"], "starts_on": "2026-04-01", "category_id": board["id"]})
    gone = owner.post(f"{src}/events", json={"title": "Deleted", "lane_id": lane["id"], "starts_on": "2026-04-02"}).json()
    owner.delete(f"{src}/events/{gone['id']}?expected_version=1")
    series = owner.post(f"{src}/series", json={"title": "Check-in", "lane_id": lane["id"], "starts_on": "2026-01-05", "frequency": "MONTHLY", "label_ids": [label["id"]]}).json()
    occurrences = [item for item in _events(owner, base, source) if item["series_id"] == series["id"]]
    owner.post(f"{src}/occurrences/{occurrences[1]['occurrence_id']}/skip")
    owner.patch(f"{src}/occurrences/{occurrences[2]['occurrence_id']}", json={"title": "Moved check-in", "expected_version": occurrences[2]["version"]})

    copied = owner.post(f"{base}/yearclocks/{target['id']}/lanes/copy", json={"source_lane_id": lane["id"], "include_events": True})
    assert copied.status_code == 201, copied.text
    copied = copied.json()
    assert (copied["events"], copied["series"], copied["categories_created"]) == (3, 1, 1)
    assert copied["lane"]["name"] == "Onboarding" and copied["lane"]["tint"] == LABEL_COLORS[2] and copied["lane"]["height"] == "tall"
    categories = {item["name"]: item for item in owner.get(f"{base}/yearclocks/{target['id']}/categories").json()}
    assert set(categories) == {"Board", "mentoring", "Welcome"}
    events = {item["title"]: item for item in _events(owner, base, target, copied["lane"]["id"]) if not item["series_id"]}
    assert set(events) == {"First day", "Mentor match", "Board intro"}
    assert events["First day"]["category_id"] == categories["Welcome"]["id"] and events["First day"]["label_ids"] == [label["id"]] and events["First day"]["links"] == [{"title": "Day", "url": "https://example.com/day"}]
    assert events["Mentor match"]["category_id"] == existing["id"] and events["Mentor match"]["ends_on"] == "2026-03-13"
    assert events["Board intro"]["category_id"] == board["id"]
    recurring = [item for item in _events(owner, base, target, copied["lane"]["id"]) if item["series_id"]]
    assert recurring and all(item["title"] == "Check-in" and item["label_ids"] == [label["id"]] and not item["exception"] for item in recurring)
    assert len(recurring) == len(occurrences)

    owner.patch(f"{src}/events/{next(item for item in _events(owner, base, source) if item['title'] == 'First day')['id']}", json={"title": "Changed at source", "lane_id": lane["id"], "starts_on": "2026-03-02", "expected_version": 1})
    assert "First day" in {item["title"] for item in _events(owner, base, target)}
    audit = next(item for item in owner.get(f"{base}/audit-events", params={"prefix": "lane"}).json()["items"] if item["action"] == "lane.copied")
    assert audit["change_summary"] == {"name": "Onboarding", "source_yearclock_id": source["id"], "source_lane_id": lane["id"], "events": 3, "series": 1, "categories_created": ["Welcome"]}

    bare = owner.post(f"{base}/yearclocks/{target['id']}/lanes/copy", json={"source_lane_id": lane["id"], "include_events": False}).json()
    assert (bare["events"], bare["series"]) == (0, 0) and _events(owner, base, target, bare["lane"]["id"]) == []
    same = owner.post(f"{base}/yearclocks/{source['id']}/lanes/copy", json={"source_lane_id": lane["id"], "include_events": False})
    assert same.status_code == 201


def test_access_limits_and_read_only(database_url, stack, monkeypatch) -> None:
    application, owner, organization_id, base, source, target = _world(stack, database_url, "lane-copy-roles")
    lane = source["lanes"][0]
    src = f"{base}/yearclocks/{source['id']}"
    owner.post(f"{src}/events", json={"title": "One", "lane_id": lane["id"], "starts_on": "2026-03-02"})
    owner.post(f"{src}/categories", json={"name": "Local", "color": "#2e7d32"})
    editor_app, editor_id = join(application, owner, organization_id, subject="lane-copy-editor", email="lane-copy-editor@example.com")
    owner.put(f"{base}/yearclocks/{target['id']}/access", json={"user_account_id": editor_id, "role": "editor"})
    body = {"source_lane_id": lane["id"], "include_events": True}
    with TestClient(editor_app) as editor:
        login(editor)
        assert editor.post(f"{base}/yearclocks/{target['id']}/lanes/copy", json=body).status_code == 404
        owner.put(f"{src}/access", json={"user_account_id": editor_id, "role": "viewer"})
        assert editor.post(f"{base}/yearclocks/{target['id']}/lanes/copy", json=body).status_code == 201
        assert editor.post(f"{src}/lanes/copy", json=body).status_code == 403

    monkeypatch.setenv("LIMIT_EVENTS_PER_YEARCLOCK", "1")
    before = len(owner.get(base).json()["yearclocks"][0]["lanes"])
    limited = owner.post(f"{base}/yearclocks/{target['id']}/lanes/copy", json=body)
    assert limited.status_code == 409 and limited.json()["detail"]["limit"] == "events_per_yearclock"
    assert len(owner.get(base).json()["yearclocks"][0]["lanes"]) == before
    monkeypatch.setenv("LIMIT_LANES_PER_YEARCLOCK", str(before))
    assert owner.post(f"{base}/yearclocks/{target['id']}/lanes/copy", json={**body, "include_events": False}).json()["detail"]["limit"] == "lanes_per_yearclock"
    monkeypatch.delenv("LIMIT_LANES_PER_YEARCLOCK")
    monkeypatch.delenv("LIMIT_EVENTS_PER_YEARCLOCK")
    version = next(item for item in owner.get(base).json()["yearclocks"] if item["id"] == source["id"])["version"]
    assert owner.delete(f"{src}?expected_version={version}").status_code == 204
    assert owner.post(f"{base}/yearclocks/{target['id']}/lanes/copy", json=body).status_code == 404
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert owner.post(f"{base}/yearclocks/{target['id']}/lanes/copy", json=body).status_code == 403
