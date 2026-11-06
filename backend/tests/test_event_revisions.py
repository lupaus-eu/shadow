"""Event Revisions are recorded for every change (Yearclock V2, P4 ticket 01)."""
from contextlib import ExitStack
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.label_routes import LABEL_COLORS
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, login
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
    organization_id = active_org(owner, verifier, seats=4)
    base = f"/api/v1/organizations/{organization_id}"
    clock = owner.get(base).json()["yearclocks"][0]
    return application, owner, organization_id, base, clock


def _revisions(application, event_id):
    with application.state.database_engine.connect() as connection:
        rows = connection.execute(text("SELECT kind, reason, reason_detail, actor_kind, actor_account_id, changed_fields, snapshot FROM event_revisions WHERE event_id = :id ORDER BY created_at, id"), {"id": event_id}).mappings().all()
    return [dict(row) for row in rows]


def _assert_history_is_current(application, organization_id) -> None:
    """Guard: whatever route changed an Event, its latest revision equals its current state."""
    from sqlalchemy import select

    from app.models import Event, EventRevision
    from app.revisions import _normalize, snapshot_of

    with application.state.session_factory() as session:
        events = session.scalars(select(Event).where(Event.organization_id == organization_id)).all()
        current = snapshot_of(session, list(events))
        for item in events:
            latest = session.scalars(select(EventRevision).where(EventRevision.event_id == item.id).order_by(EventRevision.created_at.desc(), EventRevision.id.desc()).limit(1)).first()
            assert latest is not None and _normalize(latest.snapshot) == current[item.id], (item.title, latest and latest.snapshot, current[item.id])


def _event(client, base, clock, title, **extra):
    response = client.post(f"{base}/yearclocks/{clock['id']}/events", json={"title": title, "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01", **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_direct_changes_record_state_actor_and_reason(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "revisions-direct")
    url = f"{base}/yearclocks/{clock['id']}"
    label = owner.post(f"{base}/labels", json={"name": "Budget", "color": LABEL_COLORS[0]}).json()
    event = _event(owner, base, clock, "Board meeting", label_ids=[label["id"]])
    updated = owner.patch(f"{url}/events/{event['id']}", json={"title": "Board meeting (moved)", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-08", "expected_version": 1}).json()
    owner.patch(f"{url}/events/{event['id']}", json={"title": "Board meeting (moved)", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-08", "expected_version": updated["version"]})
    deleted = owner.delete(f"{url}/events/{event['id']}?expected_version={updated['version'] + 1}")
    assert deleted.status_code == 204, deleted.text
    restored = owner.post(f"{url}/events/{event['id']}/restore", params={"expected_version": updated["version"] + 2})
    assert restored.status_code == 200, restored.text
    rows = _revisions(application, event["id"])
    assert [(row["kind"], row["reason"]) for row in rows] == [("created", "edit"), ("updated", "edit"), ("deleted", "edit"), ("restored", "edit")]
    assert rows[0]["actor_kind"] == "member" and rows[0]["actor_account_id"] is not None
    assert rows[0]["snapshot"]["label_ids"] == [label["id"]] and rows[0]["changed_fields"] == []
    assert rows[1]["changed_fields"] == ["title", "starts_on"] and rows[1]["snapshot"]["title"] == "Board meeting (moved)"
    assert rows[2]["changed_fields"] == ["deleted"]

    duplicate = _event(owner, base, clock, "Board meeting copy", origin="duplicate")
    assert _revisions(application, duplicate["id"])[0]["reason"] == "duplicate"
    bulk = owner.post(f"{url}/events/bulk", json={"items": [{"id": duplicate["id"], "expected_version": 1}], "action": "label", "add_label_ids": [label["id"]]}).json()
    last = _revisions(application, duplicate["id"])[-1]
    assert last["reason"] == "bulk" and last["reason_detail"] == {"bulk_id": bulk["bulk_id"]} and last["changed_fields"] == ["label_ids"]
    planned = owner.post(f"{url}/plan-again", json={"season_start": "2026-01-01", "lane_ids": [clock["lanes"][0]["id"]], "dry_run": False}).json()
    assert {_revisions(application, item)[0]["reason"] for item in planned["created_ids"]} == {"plan_again"}

    other = owner.post(f"{base}/yearclocks", json={"name": "Copy target"}).json()
    copied = owner.post(f"{base}/yearclocks/{other['id']}/lanes/copy", json={"source_lane_id": clock["lanes"][0]["id"], "include_events": True}).json()
    with application.state.database_engine.connect() as connection:
        reasons = connection.execute(text("SELECT DISTINCT reason, reason_detail->>'yearclock_name' FROM event_revisions WHERE yearclock_id = :id"), {"id": other["id"]}).all()
    assert copied["events"] >= 2 and reasons == [("lane_copy", clock["name"])]
    _assert_history_is_current(application, organization_id)


def test_indirect_changes_are_recorded_with_their_cause(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "revisions-indirect")
    url = f"{base}/yearclocks/{clock['id']}"
    draft = owner.post(f"{base}/labels", json={"name": "Draft", "color": LABEL_COLORS[0]}).json()
    final = owner.post(f"{base}/labels", json={"name": "Final", "color": LABEL_COLORS[1]}).json()
    old = owner.post(f"{base}/labels", json={"name": "Old", "color": LABEL_COLORS[2]}).json()
    category = owner.post(f"{url}/categories", json={"name": "Temporary", "color": "#336699"}).json()
    event = _event(owner, base, clock, "Review", label_ids=[draft["id"], old["id"]], category_id=category["id"])
    owner.post(f"{base}/labels/{draft['id']}/merge", json={"into_label_id": final["id"], "expected_version": 1, "confirm": True})
    owner.delete(f"{base}/labels/{old['id']}?expected_version=1&confirm=true")
    owner.delete(f"{url}/categories/{category['id']}?expected_version=1&confirm=true")
    second = owner.post(f"{url}/lanes", json={"name": "Second"}).json()
    lane = owner.get(base).json()["yearclocks"][0]["lanes"][0]
    moved = owner.post(f"{url}/lanes/{lane['id']}/move-events", json={"target_lane_id": second["id"], "expected_version": lane["version"]})
    assert moved.status_code == 200, moved.text
    rows = _revisions(application, event["id"])
    assert [(row["reason"], row["reason_detail"]) for row in rows[1:]] == [
        ("label_merged", {"from": "Draft", "into": "Final"}),
        ("label_deleted", {"name": "Old"}),
        ("category_deleted", {"name": "Temporary"}),
        ("lane_moved", {"lane_name": lane["name"]}),
    ]
    assert rows[1]["snapshot"]["label_ids"] == sorted([final["id"], old["id"]]) and rows[2]["snapshot"]["label_ids"] == [final["id"]]
    assert rows[3]["snapshot"]["category_id"] is None and rows[4]["snapshot"]["lane_id"] == second["id"]
    _assert_history_is_current(application, organization_id)


def test_occurrences_record_their_own_changes_and_series_changes(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "revisions-series")
    url = f"{base}/yearclocks/{clock['id']}"
    series = owner.post(f"{url}/series", json={"title": "Standup", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-01-05", "frequency": "WEEKLY"}).json()
    occurrences = [item for item in owner.get(f"{url}/events", params={"window_start": "2026-01-01"}).json() if item["series_id"] == series["id"]]
    first, second, later = occurrences[0], occurrences[1], occurrences[5]
    owner.patch(f"{url}/occurrences/{first['occurrence_id']}", json={"title": "Standup (long)", "expected_version": first["version"]})
    owner.post(f"{url}/occurrences/{second['occurrence_id']}/skip")
    owner.post(f"{url}/occurrences/{first['occurrence_id']}/restore")
    owner.post(f"{url}/series/{series['id']}/split", json={"from_occurrence_id": occurrences[4]["occurrence_id"], "expected_version": series["version"], "title": "Daily sync"})
    assert [(row["kind"], row["reason"]) for row in _revisions(application, first["id"])] == [("created", "series_created"), ("updated", "occurrence_edit"), ("updated", "occurrence_restore")]
    skipped = _revisions(application, second["id"])
    assert skipped[-1]["reason"] == "occurrence_skip" and skipped[-1]["changed_fields"] == ["skipped"] and skipped[-1]["snapshot"]["skipped"] is True
    moved = _revisions(application, later["id"])
    assert moved[-1]["reason"] == "series_changed" and moved[-1]["changed_fields"] == ["title"] and moved[0]["reason"] == "series_created"
    _assert_history_is_current(application, organization_id)


def test_support_changes_pruning_and_isolation(database_url, stack, monkeypatch) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "revisions-support")
    agent = stack.enter_context(TestClient(_platform_app(database_url, "revisions-agent", "support_agent")))
    platform_login(agent)
    grant = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "REVISIONS", "scope": "write"}).json()
    owner.post(f"{base}/support-access/{grant['id']}/approve")
    created = agent.post(f"/api/v1/platform/support-access/{grant['id']}/yearclocks/{clock['id']}/events", json={"title": "Support fix", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01"}).json()
    assert _revisions(application, created["id"])[0]["actor_kind"] == "support"

    monkeypatch.setenv("LIMIT_REVISIONS_PER_EVENT", "3")
    event = _event(owner, base, clock, "Edited often")
    for version in range(1, 6):
        owner.patch(f"{base}/yearclocks/{clock['id']}/events/{event['id']}", json={"title": f"Edit {version}", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01", "expected_version": version})
    rows = _revisions(application, event["id"])
    assert [row["snapshot"]["title"] for row in rows] == ["Edit 3", "Edit 4", "Edit 5"]

    with application.state.database_engine.begin() as connection:
        connection.execute(text("SET LOCAL ROLE yearclock_app"))
        connection.execute(text("SELECT set_config('app.current_organization_id', :id, true)"), {"id": "00000000-0000-4000-8000-000000000000"})
        assert connection.execute(text("SELECT count(*) FROM event_revisions")).scalar_one() == 0


def test_the_migration_gives_existing_events_a_baseline(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "revisions-baseline")
    label = owner.post(f"{base}/labels", json={"name": "Kept", "color": LABEL_COLORS[0]}).json()
    event = _event(owner, base, clock, "Before history", label_ids=[label["id"]])
    config = Config(Path(__file__).resolve().parents[1] / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.downgrade(config, "0038")
    command.upgrade(config, "head")
    rows = _revisions(application, event["id"])
    assert [(row["kind"], row["reason"], row["actor_kind"]) for row in rows] == [("created", "baseline", "system")]
    assert rows[0]["snapshot"]["title"] == "Before history" and rows[0]["snapshot"]["label_ids"] == [label["id"]] and rows[0]["snapshot"]["deleted"] is False
