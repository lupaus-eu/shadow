"""Event history (Yearclock V2, P4 ticket 02)."""
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


def _history(client, base, clock_id, event_id, **params):
    return client.get(f"{base}/yearclocks/{clock_id}/events/{event_id}/history", params=params)


def test_history_lists_changes_newest_first_with_names_and_actors(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "history-owner")
    url = f"{base}/yearclocks/{clock['id']}"
    lane = clock["lanes"][0]
    second = owner.post(f"{url}/lanes", json={"name": "Finance"}).json()
    board = owner.post(f"{url}/categories", json={"name": "Board", "color": "#336699"}).json()
    label = owner.post(f"{base}/labels", json={"name": "Budget", "color": LABEL_COLORS[0]}).json()
    event = owner.post(f"{url}/events", json={"title": "Board meeting", "lane_id": lane["id"], "starts_on": "2026-03-10", "description": "Agenda"}).json()
    editor_app, editor_id = join(application, owner, organization_id, subject="history-editor", email="history-editor@example.com")
    viewer_app, viewer_id = join(application, owner, organization_id, subject="history-viewer", email="history-viewer@example.com")
    owner.put(f"{url}/access", json={"user_account_id": editor_id, "role": "editor"})
    owner.put(f"{url}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    with TestClient(editor_app) as editor:
        login(editor)
        editor.patch(f"{url}/events/{event['id']}", json={"title": "Board meeting", "lane_id": second["id"], "category_id": board["id"], "label_ids": [label["id"]], "starts_on": "2026-03-17", "description": "New agenda", "expected_version": 1})
    with TestClient(viewer_app) as viewer:
        login(viewer)
        page = _history(viewer, base, clock["id"], event["id"])
        assert page.status_code == 200, page.text
        items = page.json()["items"]
    assert [(item["kind"], item["reason"]) for item in items] == [("updated", "edit"), ("created", "edit")]
    change = {item["field"]: item for item in items[0]["changes"]}
    assert list(change) == ["starts_on", "lane_id", "category_id", "label_ids", "description"]
    assert (change["starts_on"]["before"], change["starts_on"]["after"]) == ("2026-03-10", "2026-03-17")
    assert change["lane_id"]["before"] == {"id": lane["id"], "name": lane["name"]} and change["lane_id"]["after"]["name"] == "Finance"
    assert change["category_id"] == {"field": "category_id", "before": None, "after": {"id": board["id"], "name": "Board"}}
    assert change["label_ids"]["after"] == [{"id": label["id"], "name": "Budget"}]
    assert change["description"] == {"field": "description", "before": None, "after": None}
    assert items[0]["actor"] == {"kind": "member", "name": "history-editor"} and items[1]["actor"]["kind"] == "member" and items[1]["changes"] == []

    membership = next(item for item in owner.get(f"{base}/memberships").json() if item["user_account_id"] == editor_id)
    owner.delete(f"{base}/memberships/{membership['id']}", params={"expected_version": membership["version"]})
    assert _history(owner, base, clock["id"], event["id"]).json()["items"][0]["actor"] == {"kind": "member", "name": None}

    owner.delete(f"{url}/categories/{board['id']}?expected_version=1&confirm=true")
    latest = _history(owner, base, clock["id"], event["id"]).json()["items"]
    assert latest[0]["reason"] == "category_deleted" and latest[0]["reason_detail"] == {"name": "Board"}
    assert latest[1]["changes"][2]["after"] == {"id": board["id"], "name": None}


def test_history_access_paging_occurrences_and_support(database_url, stack, monkeypatch) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "history-access")
    url = f"{base}/yearclocks/{clock['id']}"
    lane = clock["lanes"][0]["id"]
    event = owner.post(f"{url}/events", json={"title": "Edit 0", "lane_id": lane, "starts_on": "2026-03-10"}).json()
    for version in range(1, 55):
        owner.patch(f"{url}/events/{event['id']}", json={"title": f"Edit {version}", "lane_id": lane, "starts_on": "2026-03-10", "expected_version": version})
    first = _history(owner, base, clock["id"], event["id"]).json()
    second = _history(owner, base, clock["id"], event["id"], offset=first["next_offset"]).json()
    assert len(first["items"]) == 50 and first["next_offset"] == 50 and len(second["items"]) == 5 and second["next_offset"] is None
    assert second["items"][-1]["kind"] == "created" and second["items"][0]["changes"][0] == {"field": "title", "before": "Edit 3", "after": "Edit 4"}

    member_app, _ = join(application, owner, organization_id, subject="history-member", email="history-member@example.com")
    with TestClient(member_app) as member:
        login(member)
        assert _history(member, base, clock["id"], event["id"]).status_code in {403, 404}
    other = owner.post(f"{base}/yearclocks", json={"name": "Other"}).json()
    assert _history(owner, base, other["id"], event["id"]).status_code == 404

    series = owner.post(f"{url}/series", json={"title": "Standup", "lane_id": lane, "starts_on": "2026-01-05", "frequency": "WEEKLY"}).json()
    occurrences = [item for item in owner.get(f"{url}/events", params={"window_start": "2026-01-01"}).json() if item["series_id"] == series["id"]]
    owner.post(f"{url}/series/{series['id']}/split", json={"from_occurrence_id": occurrences[0]["occurrence_id"], "expected_version": series["version"], "title": "Daily sync"})
    owner.post(f"{url}/occurrences/{occurrences[0]['occurrence_id']}/skip")
    reasons = [item["reason"] for item in _history(owner, base, clock["id"], occurrences[0]["id"]).json()["items"]]
    assert reasons == ["occurrence_skip", "series_changed", "series_created"]

    agent = stack.enter_context(TestClient(_platform_app(database_url, "history-agent", "support_agent")))
    platform_login(agent)
    grant = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "HISTORY", "scope": "write"}).json()
    owner.post(f"{base}/support-access/{grant['id']}/approve")
    agent.patch(f"/api/v1/platform/support-access/{grant['id']}/yearclocks/{clock['id']}/events/{event['id']}", json={"title": "Fixed by support", "lane_id": lane, "starts_on": "2026-03-10", "expected_version": 55})
    assert _history(owner, base, clock["id"], event["id"]).json()["items"][0]["actor"] == {"kind": "support", "name": None}
    assert agent.get(f"{base}/yearclocks/{clock['id']}/events/{event['id']}/history").status_code in {401, 403, 404}


def test_linked_event_history_follows_source_access(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "history-linked")
    team = owner.post(f"{base}/yearclocks", json={"name": "Team"}).json()
    source_event = owner.post(f"{base}/yearclocks/{team['id']}/events", json={"title": "Sprint", "lane_id": team["lanes"][0]["id"], "starts_on": "2026-03-10"}).json()
    owner.post(f"{base}/yearclocks/{clock['id']}/lanes/link", json={"source_lane_id": team["lanes"][0]["id"]})
    viewer_app, viewer_id = join(application, owner, organization_id, subject="history-linked-viewer", email="history-linked-viewer@example.com")
    owner.put(f"{base}/yearclocks/{clock['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    with TestClient(viewer_app) as viewer:
        login(viewer)
        assert _history(viewer, base, clock["id"], source_event["id"]).status_code == 404
        owner.put(f"{base}/yearclocks/{team['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
        assert [item["kind"] for item in _history(viewer, base, clock["id"], source_event["id"]).json()["items"]] == ["created"]
