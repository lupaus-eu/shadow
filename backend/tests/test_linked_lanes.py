"""Linked Lanes and roll-up Yearclocks (Yearclock V2, P3 ticket 05)."""
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.jobs import run_one_background_job, schedule_purge_jobs
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
    rollup = owner.get(base).json()["yearclocks"][0]
    team = owner.post(f"{base}/yearclocks", json={"name": "Team year"}).json()
    return application, owner, organization_id, base, team, rollup


def _clock(client, base, clock_id):
    return next(item for item in client.get(base).json()["yearclocks"] if item["id"] == clock_id)


def _events(client, base, clock_id):
    return client.get(f"{base}/yearclocks/{clock_id}/events", params={"window_start": "2026-01-01"}).json()


def _link(client, base, clock_id, source_lane_id):
    return client.post(f"{base}/yearclocks/{clock_id}/lanes/link", json={"source_lane_id": source_lane_id})


def test_a_linked_lane_shows_its_source_live_and_read_only(database_url, stack) -> None:
    application, owner, organization_id, base, team, rollup = _world(stack, database_url, "linked-owner")
    team_url, rollup_url = f"{base}/yearclocks/{team['id']}", f"{base}/yearclocks/{rollup['id']}"
    source = team["lanes"][0]
    local = owner.post(f"{team_url}/categories", json={"name": "Sprint", "color": "#2e7d32"}).json()
    label = owner.post(f"{base}/labels", json={"name": "Team", "color": LABEL_COLORS[0]}).json()
    single = owner.post(f"{team_url}/events", json={"title": "Sprint review", "lane_id": source["id"], "starts_on": "2026-03-10", "category_id": local["id"], "label_ids": [label["id"]]}).json()
    owner.post(f"{team_url}/series", json={"title": "Retro", "lane_id": source["id"], "starts_on": "2026-01-07", "frequency": "MONTHLY"})

    linked = _link(owner, base, rollup["id"], source["id"])
    assert linked.status_code == 201, linked.text
    linked = linked.json()
    assert linked["source_lane_id"] == source["id"] and linked["source"] == {"available": True, "reason": None, "yearclock_id": team["id"], "yearclock_name": "Team year", "lane_name": source["name"]}
    summary = next(lane for lane in _clock(owner, base, rollup["id"])["lanes"] if lane["id"] == linked["id"])
    assert summary["source"]["available"] is True

    events = _events(owner, base, rollup["id"])
    shown = [item for item in events if item["linked"]]
    assert {item["title"] for item in shown} == {"Sprint review", "Retro"} and all(item["lane_id"] == linked["id"] and item["source_yearclock_id"] == team["id"] for item in shown)
    review = next(item for item in shown if item["id"] == single["id"])
    assert review["category_id"] == local["id"] and review["label_ids"] == [label["id"]]
    categories = {item["name"]: item for item in owner.get(f"{rollup_url}/categories").json()}
    assert categories["Sprint"]["scope"] == "linked" and categories["Sprint"]["source_yearclock_name"] == "Team year"

    owner.patch(f"{team_url}/events/{single['id']}", json={"title": "Sprint demo", "lane_id": source["id"], "starts_on": "2026-03-10", "expected_version": 1})
    assert "Sprint demo" in {item["title"] for item in _events(owner, base, rollup["id"])}
    assert owner.post(f"{rollup_url}/events", json={"title": "Nope", "lane_id": linked["id"], "starts_on": "2026-03-01"}).json()["detail"]["reason"] == "linked_lane"
    assert owner.patch(f"{rollup_url}/events/{single['id']}", json={"title": "Nope", "lane_id": rollup["lanes"][0]["id"], "starts_on": "2026-03-10", "expected_version": 2}).status_code == 404
    assert owner.post(f"{rollup_url}/events/bulk", json={"items": [{"id": single["id"], "expected_version": 2}], "action": "delete"}).json()["detail"]["reason"] == "not_in_yearclock"
    assert owner.post(f"{rollup_url}/series", json={"title": "Nope", "lane_id": linked["id"], "starts_on": "2026-01-01", "frequency": "WEEKLY"}).status_code == 422

    styled = owner.patch(f"{rollup_url}/lanes/{linked['id']}", json={"name": "Renamed", "tint": LABEL_COLORS[3], "height": "tall", "expected_version": 1}).json()
    assert styled["name"] == source["name"] and styled["tint"] == LABEL_COLORS[3] and styled["height"] == "tall"
    copied = owner.post(f"{rollup_url}/lanes/copy", json={"source_lane_id": linked["id"], "include_events": True}).json()
    assert copied["events"] == 1 and copied["series"] == 1 and copied["lane"]["source_lane_id"] is None

    audits = {item["action"]: item["change_summary"] for item in owner.get(f"{base}/audit-events", params={"prefix": "lane"}).json()["items"]}
    assert audits["lane.linked"]["source_yearclock_id"] == team["id"] and audits["lane.linked_elsewhere"]["linked_into_yearclock_name"] == rollup["name"]


def test_links_are_checked_limited_and_removable(database_url, stack, monkeypatch) -> None:
    application, owner, organization_id, base, team, rollup = _world(stack, database_url, "linked-rules")
    rollup_url = f"{base}/yearclocks/{rollup['id']}"
    source = team["lanes"][0]
    linked = _link(owner, base, rollup["id"], source["id"]).json()
    assert _link(owner, base, rollup["id"], source["id"]).json()["detail"]["reason"] == "already_linked"
    assert _link(owner, base, team["id"], source["id"]).json()["detail"]["reason"] == "same_yearclock"
    assert _link(owner, base, team["id"], linked["id"]).json()["detail"]["reason"] == "linked_source"
    monkeypatch.setenv("LIMIT_LANES_PER_YEARCLOCK", "2")
    other = owner.post(f"{base}/yearclocks/{team['id']}/lanes", json={"name": "Second"}).json()
    assert _link(owner, base, rollup["id"], other["id"]).json()["detail"]["limit"] == "lanes_per_yearclock"
    monkeypatch.delenv("LIMIT_LANES_PER_YEARCLOCK")

    own = rollup["lanes"][0]
    assert owner.delete(f"{rollup_url}/lanes/{own['id']}?expected_version={own['version']}").status_code == 204
    remaining = _clock(owner, base, rollup["id"])["lanes"]
    assert [lane["id"] for lane in remaining] == [linked["id"]]
    assert owner.delete(f"{rollup_url}/lanes/{linked['id']}?expected_version={remaining[0]['version']}").json()["detail"]["reason"] == "last_lane"
    second = _link(owner, base, rollup["id"], other["id"]).json()
    owner.post(f"{base}/yearclocks/{team['id']}/events", json={"title": "Keeps", "lane_id": source["id"], "starts_on": "2026-02-02"})
    assert owner.delete(f"{rollup_url}/lanes/{linked['id']}?expected_version={remaining[0]['version']}").status_code == 204
    actions = [item["action"] for item in owner.get(f"{base}/audit-events", params={"prefix": "lane"}).json()["items"]]
    assert "lane.unlinked" in actions and "lane.unlinked_elsewhere" in actions
    assert owner.delete(f"{base}/yearclocks/{team['id']}/lanes/{other['id']}?expected_version={other['version']}").status_code == 204
    assert second["id"] not in {lane["id"] for lane in _clock(owner, base, rollup["id"])["lanes"]}

    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert _link(owner, base, rollup["id"], source["id"]).status_code == 403


def test_each_viewer_sees_only_sources_they_may_read(database_url, stack) -> None:
    application, owner, organization_id, base, team, rollup = _world(stack, database_url, "linked-access")
    source = team["lanes"][0]
    owner.post(f"{base}/yearclocks/{team['id']}/events", json={"title": "Private plan", "lane_id": source["id"], "starts_on": "2026-04-01"})
    owner.post(f"{base}/yearclocks/{team['id']}/categories", json={"name": "Hidden", "color": "#2e7d32"})
    linked = _link(owner, base, rollup["id"], source["id"]).json()
    viewer_app, viewer_id = join(application, owner, organization_id, subject="linked-viewer", email="linked-viewer@example.com")
    owner.put(f"{base}/yearclocks/{rollup['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    with TestClient(viewer_app) as viewer:
        login(viewer)
        lane = next(item for item in _clock(viewer, base, rollup["id"])["lanes"] if item["id"] == linked["id"])
        assert lane["source"] == {"available": False, "reason": "no_access", "yearclock_id": None, "yearclock_name": None, "lane_name": None}
        assert [item for item in _events(viewer, base, rollup["id"]) if item["linked"]] == []
        assert "Hidden" not in {item["name"] for item in viewer.get(f"{base}/yearclocks/{rollup['id']}/categories").json()}
        owner.put(f"{base}/yearclocks/{team['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
        assert {item["title"] for item in _events(viewer, base, rollup["id"]) if item["linked"]} == {"Private plan"}
        assert next(item for item in _clock(viewer, base, rollup["id"])["lanes"] if item["id"] == linked["id"])["source"]["available"] is True

    team_version = _clock(owner, base, team["id"])["version"]
    assert owner.delete(f"{base}/yearclocks/{team['id']}?expected_version={team_version}").status_code == 204
    lane = next(item for item in _clock(owner, base, rollup["id"])["lanes"] if item["id"] == linked["id"])
    assert lane["source"]["available"] is False and lane["source"]["reason"] == "deleted" and lane["source"]["yearclock_name"] == "Team year"
    assert [item for item in _events(owner, base, rollup["id"]) if item["linked"]] == []
    deleted = next(item for item in owner.get(f"{base}/yearclocks", params={"include_deleted": True}).json() if item["id"] == team["id"])
    assert owner.post(f"{base}/yearclocks/{team['id']}/recover", params={"expected_version": deleted["version"]}).status_code == 200
    assert {item["title"] for item in _events(owner, base, rollup["id"]) if item["linked"]} == {"Private plan"}

    deleted = _clock(owner, base, team["id"])
    owner.delete(f"{base}/yearclocks/{team['id']}?expected_version={deleted['version']}")
    now = datetime.now(UTC)
    engine, factory = application.state.database_engine, application.state.session_factory
    with engine.begin() as connection:
        connection.execute(text("UPDATE yearclocks SET deleted_at = :at WHERE id = :id"), {"at": now - timedelta(days=31), "id": team["id"]})
    schedule_purge_jobs(factory, today=now.date())
    while run_one_background_job(factory, organization_id=UUID(organization_id)):
        pass
    assert linked["id"] not in {item["id"] for item in _clock(owner, base, rollup["id"])["lanes"]}


def test_search_finds_linked_events_only_for_readers_of_the_source(database_url, stack) -> None:
    application, owner, organization_id, base, team, rollup = _world(stack, database_url, "linked-search")
    source = team["lanes"][0]
    owner.post(f"{base}/yearclocks/{team['id']}/events", json={"title": "Budget workshop", "lane_id": source["id"], "starts_on": "2025-11-04"})
    owner.post(f"{base}/yearclocks/{rollup['id']}/events", json={"title": "Budget approval", "lane_id": rollup["lanes"][0]["id"], "starts_on": "2026-02-01"})
    linked = _link(owner, base, rollup["id"], source["id"]).json()
    found = owner.get(f"{base}/yearclocks/{rollup['id']}/search", params={"q": "budget"}).json()
    assert [(item["title"], item["linked"]) for item in found["items"]] == [("Budget workshop", True), ("Budget approval", False)]
    assert found["items"][0]["lane_id"] == linked["id"] and found["items"][0]["source_yearclock_id"] == team["id"]
    viewer_app, viewer_id = join(application, owner, organization_id, subject="linked-search-viewer", email="linked-search-viewer@example.com")
    owner.put(f"{base}/yearclocks/{rollup['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    with TestClient(viewer_app) as viewer:
        login(viewer)
        assert [item["title"] for item in viewer.get(f"{base}/yearclocks/{rollup['id']}/search", params={"q": "budget"}).json()["items"]] == ["Budget approval"]
