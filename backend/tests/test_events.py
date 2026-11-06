"""Event content, validation, concurrency, and audit (ticket 10)."""
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, login


def _setup(database_url: str, subject: str):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    return application, verifier


def test_event_validation_matches_the_approved_limits(database_url: str) -> None:
    application, verifier = _setup(database_url, "events-validation")
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        workspace = client.get(f"/api/v1/organizations/{organization_id}").json()
        yearclock = workspace["yearclocks"][0]
        other = client.post(f"/api/v1/organizations/{organization_id}/yearclocks", json={"name": "Other"}).json()
        foreign_category = client.post(f"/api/v1/organizations/{organization_id}/yearclocks/{other['id']}/categories", json={"name": "Elsewhere"}).json()
        path = f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}/events"
        base = {"title": "Board meeting", "lane_id": yearclock["lanes"][0]["id"], "starts_on": "2026-10-01"}
        cases = {
            "blank title": {**base, "title": "   "},
            "long title": {**base, "title": "x" * 201},
            "end before start": {**base, "ends_on": "2026-09-30"},
            "long description": {**base, "description": "x" * 10_001},
            "non-http link": {**base, "links": [{"title": "x", "url": "javascript:alert(1)"}]},
            "long link": {**base, "links": [{"title": "x", "url": "https://example.com/" + "x" * 2048}]},
            "eleven links": {**base, "links": [{"title": f"l{i}", "url": f"https://example.com/{i}"} for i in range(11)]},
            "duplicate links": {**base, "links": [{"title": "a", "url": "https://example.com/a"}, {"title": "b", "url": "https://example.com/a"}]},
            "untitled link": {**base, "links": [{"title": "  ", "url": "https://example.com/a"}]},
            "long location": {**base, "location": "x" * 201},
            "foreign lane": {**base, "lane_id": other["lanes"][0]["id"]},
            "foreign category": {**base, "category_id": foreign_category["id"]},
        }
        rejected = {name: client.post(path, json=payload).status_code for name, payload in cases.items()}
        accepted = client.post(path, json={**base, "title": "x" * 200, "ends_on": "2026-10-01", "description": "Line one\nLine two", "location": "  Room 4  ", "links": [{"title": "Agenda", "url": "https://example.com/agenda"}]})
    assert rejected == {name: 422 for name in cases}
    assert accepted.status_code == 201
    assert accepted.json()["description"] == "Line one\nLine two"
    assert accepted.json()["location"] == "Room 4" and accepted.json()["links"] == [{"title": "Agenda", "url": "https://example.com/agenda"}]


def test_event_changes_are_versioned_recoverable_and_audited(database_url: str) -> None:
    application, verifier = _setup(database_url, "events-lifecycle")
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        yearclock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        path = f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}/events"
        created = client.post(path, json={"title": "Budget", "lane_id": yearclock["lanes"][0]["id"], "starts_on": "2026-03-01", "ends_on": "2026-03-31"}).json()
        updated = client.patch(f"{path}/{created['id']}", json={"title": "Budget review", "lane_id": created["lane_id"], "starts_on": "2026-03-01", "expected_version": 1})
        stale = client.patch(f"{path}/{created['id']}", json={"title": "Lost update", "lane_id": created["lane_id"], "starts_on": "2026-03-01", "expected_version": 1})
        stale_delete = client.delete(f"{path}/{created['id']}?expected_version=1")
        deleted = client.delete(f"{path}/{created['id']}?expected_version=2")
        listed_after_delete = client.get(f"{path}?window_start=2026-01-01").json()
        recoverable = client.get(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}/deleted-events").json()
        restored = client.post(f"{path}/{created['id']}/restore?expected_version=3")
        listed = client.get(f"{path}?window_start=2026-01-01").json()
    assert updated.status_code == 200 and updated.json()["version"] == 2
    assert updated.json()["ends_on"] is None
    assert stale.status_code == 409 and stale.json()["detail"] == {"latest_version": 2}
    assert stale_delete.status_code == 409
    assert deleted.status_code == 204
    assert listed_after_delete == []
    assert [item["id"] for item in recoverable] == [created["id"]]
    assert restored.status_code == 200 and restored.json()["title"] == "Budget review"
    assert [item["title"] for item in listed] == ["Budget review"]
    with application.state.database_engine.connect() as connection:
        actions = connection.execute(text("SELECT action FROM audit_events WHERE target_id = :id ORDER BY occurred_at"), {"id": created["id"]}).scalars().all()
    assert actions == ["event.created", "event.updated", "event.deleted", "event.restored"]


def test_planning_window_returns_overlapping_events_only(database_url: str) -> None:
    application, verifier = _setup(database_url, "events-window")
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        yearclock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        path = f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}/events"
        lane = yearclock["lanes"][0]["id"]
        for title, starts_on, ends_on in [("Before", "2025-06-01", None), ("Crossing", "2025-12-20", "2026-01-05"), ("Inside", "2026-07-01", None), ("Tail", "2026-12-31", "2027-01-02"), ("After", "2027-01-01", None)]:
            assert client.post(path, json={"title": title, "lane_id": lane, "starts_on": starts_on, "ends_on": ends_on}).status_code == 201
        calendar_year = [item["title"] for item in client.get(f"{path}?window_start=2026-01-01").json()]
        rolling = [item["title"] for item in client.get(f"{path}?window_start=2026-07-15").json()]
    assert calendar_year == ["Crossing", "Inside", "Tail"]
    assert rolling == ["Inside", "Tail", "After"]
