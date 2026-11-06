"""Changes since the last visit (Yearclock V2, P4 ticket 04)."""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient

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
    organization_id = active_org(owner, verifier, seats=5)
    base = f"/api/v1/organizations/{organization_id}"
    clock = owner.get(base).json()["yearclocks"][0]
    return application, owner, organization_id, base, clock


def test_changes_by_others_since_the_previous_visit(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "changes-owner")
    url = f"{base}/yearclocks/{clock['id']}"
    lane = clock["lanes"][0]["id"]
    kept = owner.post(f"{url}/events", json={"title": "Kept", "lane_id": lane, "starts_on": "2026-03-01"}).json()
    changed = owner.post(f"{url}/events", json={"title": "To change", "lane_id": lane, "starts_on": "2026-03-02"}).json()
    removed = owner.post(f"{url}/events", json={"title": "To delete", "lane_id": lane, "starts_on": "2026-03-03"}).json()
    series = owner.post(f"{url}/series", json={"title": "Weekly", "lane_id": lane, "starts_on": "2026-01-05", "frequency": "WEEKLY"}).json()
    first = owner.post(f"{url}/visit")
    assert first.status_code == 200 and first.json() == {"previous_visited_at": None}

    editor_app, editor_id = join(application, owner, organization_id, subject="changes-editor", email="changes-editor@example.com")
    owner.put(f"{url}/access", json={"user_account_id": editor_id, "role": "editor"})
    with TestClient(editor_app) as editor:
        login(editor)
        added = editor.post(f"{url}/events", json={"title": "Added", "lane_id": lane, "starts_on": "2026-03-04"}).json()
        editor.patch(f"{url}/events/{changed['id']}", json={"title": "Changed", "lane_id": lane, "starts_on": "2026-03-02", "expected_version": 1})
        editor.delete(f"{url}/events/{removed['id']}?expected_version=1")
        occurrences = [item for item in editor.get(f"{url}/events", params={"window_start": "2026-01-01"}).json() if item["series_id"] == series["id"]]
        editor.post(f"{url}/series/{series['id']}/split", json={"from_occurrence_id": occurrences[0]["occurrence_id"], "expected_version": series["version"], "title": "Weekly sync"})
    owner.patch(f"{url}/events/{kept['id']}", json={"title": "Kept (mine)", "lane_id": lane, "starts_on": "2026-03-01", "expected_version": 1})

    second = owner.post(f"{url}/visit").json()
    assert second["previous_visited_at"] is not None
    page = owner.get(f"{url}/changes", params={"since": second["previous_visited_at"]}).json()
    by_kind = {}
    for item in page["items"]:
        by_kind.setdefault(item["kind"], []).append(item)
    assert [item["title"] for item in by_kind["new"]] == ["Added"] and by_kind["new"][0]["event_id"] == added["id"]
    assert [item["title"] for item in by_kind["changed"]] == ["Changed"] and [item["title"] for item in by_kind["deleted"]] == ["To delete"]
    assert len(by_kind["series_changed"]) == 1 and by_kind["series_changed"][0]["count"] >= len(occurrences) and by_kind["series_changed"][0]["title"] == "Weekly sync"
    assert all(item["actor"] == {"kind": "member", "name": "changes-editor"} for item in page["items"]) and "Kept (mine)" not in {item["title"] for item in page["items"]}
    assert page["total"] == 4 and page["more"] is False and page["latest_at"] is not None
    one = owner.get(f"{url}/changes", params={"since": second["previous_visited_at"], "limit": 1}).json()
    assert len(one["items"]) == 1 and one["more"] is True and one["total"] == 4
    assert owner.get(f"{url}/changes", params={"since": page["latest_at"]}).json()["items"] == []
    third = owner.post(f"{url}/visit").json()
    assert third["previous_visited_at"] > second["previous_visited_at"]


def test_linked_changes_follow_source_access(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "changes-linked")
    team = owner.post(f"{base}/yearclocks", json={"name": "Team"}).json()
    owner.post(f"{base}/yearclocks/{clock['id']}/lanes/link", json={"source_lane_id": team["lanes"][0]["id"]})
    viewer_app, viewer_id = join(application, owner, organization_id, subject="changes-viewer", email="changes-viewer@example.com")
    owner.put(f"{base}/yearclocks/{clock['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    with TestClient(viewer_app) as viewer:
        login(viewer)
        since = viewer.post(f"{base}/yearclocks/{clock['id']}/visit").json()["previous_visited_at"] or "2000-01-01T00:00:00Z"
        owner.post(f"{base}/yearclocks/{team['id']}/events", json={"title": "Team plan", "lane_id": team["lanes"][0]["id"], "starts_on": "2026-03-01"})
        assert viewer.get(f"{base}/yearclocks/{clock['id']}/changes", params={"since": since}).json()["items"] == []
        owner.put(f"{base}/yearclocks/{team['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
        assert [item["title"] for item in viewer.get(f"{base}/yearclocks/{clock['id']}/changes", params={"since": since}).json()["items"]] == ["Team plan"]
    member_app, _ = join(application, owner, organization_id, subject="changes-member", email="changes-member@example.com")
    with TestClient(member_app) as member:
        login(member)
        assert member.get(f"{base}/yearclocks/{clock['id']}/changes", params={"since": "2000-01-01T00:00:00Z"}).status_code in {403, 404}
