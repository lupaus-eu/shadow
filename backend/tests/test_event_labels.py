"""Labels on Events (Yearclock V2, P2 ticket 03)."""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.label_routes import LABEL_COLORS
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login
from test_platform_operations import _platform_app, platform_login

BLUE = LABEL_COLORS[0]


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


def _label(client, base, name):
    response = client.post(f"{base}/labels", json={"name": name, "color": BLUE})
    assert response.status_code in {200, 201}, response.text
    return response.json()["id"]


def _event_body(clock, title="Board meeting", **extra):
    return {"title": title, "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01", **extra}


def test_editors_label_events_and_changes_are_audited(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "event-labels-owner")
    editor_app, editor_id = join(application, owner, organization_id, subject="event-labels-editor", email="event-labels-editor@example.com")
    viewer_app, viewer_id = join(application, owner, organization_id, subject="event-labels-viewer", email="event-labels-viewer@example.com")
    owner.put(f"{base}/yearclocks/{clock['id']}/access", json={"user_account_id": editor_id, "role": "editor"})
    owner.put(f"{base}/yearclocks/{clock['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    events = f"{base}/yearclocks/{clock['id']}/events"
    decision = _label(owner, base, "Decision needed")
    with TestClient(editor_app) as editor:
        login(editor)
        budget = _label(editor, base, "Budget")
        created = editor.post(events, json=_event_body(clock, label_ids=[decision, budget]))
        assert created.status_code == 201, created.text
        event = created.json()
        assert set(event["label_ids"]) == {decision, budget}
        kept = editor.patch(f"{events}/{event['id']}", json=_event_body(clock, title="Board meeting (moved)", expected_version=1))
        replaced = editor.patch(f"{events}/{event['id']}", json=_event_body(clock, title="Board meeting (moved)", expected_version=2, label_ids=[budget]))
    listed = owner.get(events, params={"window_start": "2026-09-01"}).json()
    assert set(kept.json()["label_ids"]) == {decision, budget}
    assert replaced.status_code == 200 and replaced.json()["label_ids"] == [budget]
    assert next(item for item in listed if item["id"] == event["id"])["label_ids"] == [budget]
    with TestClient(viewer_app) as viewer:
        login(viewer)
        refused = viewer.patch(f"{events}/{event['id']}", json=_event_body(clock, expected_version=3, label_ids=[]))
        seen = viewer.get(events, params={"window_start": "2026-09-01"}).json()
    assert refused.status_code == 403 and next(item for item in seen if item["id"] == event["id"])["label_ids"] == [budget]

    audit = owner.get(f"{base}/audit-events", params={"prefix": "event"}).json()["items"]
    summaries = [item["change_summary"] for item in audit if item["target_id"] == event["id"]]
    assert {"title": "Board meeting", "labels": ["Decision needed", "Budget"]} in summaries
    assert {"title": "Board meeting (moved)", "labels_removed": ["Decision needed"]} in summaries


def test_label_ids_are_validated_and_limited(database_url, stack, monkeypatch) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "event-labels-validation")
    events = f"{base}/yearclocks/{clock['id']}/events"
    first, second, third = (_label(owner, base, name) for name in ("One", "Two", "Three"))
    monkeypatch.setenv("LIMIT_LABELS_PER_EVENT", "2")
    duplicate = owner.post(events, json=_event_body(clock, label_ids=[first, first]))
    too_many = owner.post(events, json=_event_body(clock, label_ids=[first, second, third]))
    stranger_verifier = Verifier()
    stranger = stack.enter_context(TestClient(create_app(database_url=database_url, oidc_client=OIDC("event-labels-stranger", "event-labels-stranger@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=stranger_verifier, clock=lambda: NOW)))
    login(stranger)
    foreign_org = active_org(stranger, stranger_verifier)
    foreign_label = stranger.post(f"/api/v1/organizations/{foreign_org}/labels", json={"name": "Foreign", "color": BLUE}).json()["id"]
    foreign = owner.post(events, json=_event_body(clock, label_ids=[foreign_label]))
    assert duplicate.status_code == 422 and foreign.status_code == 422
    assert too_many.status_code == 409 and too_many.json()["detail"] == {"reason": "limit_reached", "limit": "labels_per_event", "maximum": 2}
    assert owner.post(events, json=_event_body(clock, label_ids=[first, second])).status_code == 201

    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert owner.post(events, json=_event_body(clock, label_ids=[first])).status_code == 403


def test_merge_and_delete_update_events_and_restored_events_keep_labels(database_url, stack) -> None:
    _, owner, _, base, clock = _world(stack, database_url, "event-labels-merge")
    events = f"{base}/yearclocks/{clock['id']}/events"
    budget, finance, draft = (_label(owner, base, name) for name in ("Budget", "Finance", "Draft"))
    both = owner.post(events, json=_event_body(clock, "Both", label_ids=[budget, finance])).json()
    only_budget = owner.post(events, json=_event_body(clock, "Only budget", label_ids=[budget, draft])).json()
    usage = {item["name"]: item["usage"] for item in owner.get(f"{base}/labels").json()}
    assert usage == {"Budget": 2, "Draft": 1, "Finance": 1}
    unconfirmed = owner.post(f"{base}/labels/{budget}/merge", json={"into_label_id": finance, "expected_version": 1})
    assert unconfirmed.json()["detail"] == {"reason": "confirmation_required", "usage": 2}
    merged = owner.post(f"{base}/labels/{budget}/merge", json={"into_label_id": finance, "expected_version": 1, "confirm": True})
    assert merged.status_code == 200 and merged.json()["usage"] == 2
    listed = {item["id"]: item for item in owner.get(events, params={"window_start": "2026-09-01"}).json()}
    assert listed[both["id"]]["label_ids"] == [finance] and listed[both["id"]]["version"] == 2
    assert sorted(listed[only_budget["id"]]["label_ids"]) == sorted([finance, draft])

    assert owner.delete(f"{events}/{only_budget['id']}?expected_version=2").status_code == 204
    assert owner.delete(f"{base}/labels/{draft}?expected_version=1&confirm=true").status_code == 204
    restored = owner.post(f"{events}/{only_budget['id']}/restore?expected_version=4")
    assert restored.status_code == 200 and restored.json()["label_ids"] == [finance]
    deleted_audit = next(item for item in owner.get(f"{base}/audit-events", params={"prefix": "label"}).json()["items"] if item["action"] == "label.deleted")
    assert deleted_audit["change_summary"]["affected_events"] == 1


def test_support_agents_attach_existing_labels_only(database_url, stack) -> None:
    _, owner, organization_id, base, clock = _world(stack, database_url, "event-labels-support")
    finance = _label(owner, base, "Finance")
    agent = stack.enter_context(TestClient(_platform_app(database_url, "event-labels-agent", "support_agent")))
    platform_login(agent)
    grant = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "LABELS", "scope": "write"}).json()
    owner.post(f"{base}/support-access/{grant['id']}/approve")
    support = f"/api/v1/platform/support-access/{grant['id']}/yearclocks"
    clocks = agent.get(support).json()
    created = agent.post(f"{support}/{clock['id']}/events", json=_event_body(clock, "Support fix", label_ids=[finance]))
    listed = agent.get(f"{support}/{clock['id']}/events", params={"window_start": "2026-09-01"}).json()
    assert [item["name"] for item in clocks[0]["labels"]] == ["Finance"]
    assert created.status_code == 201 and created.json()["label_ids"] == [finance]
    assert next(item for item in listed if item["title"] == "Support fix")["label_ids"] == [finance]
    assert agent.post(f"{base}/labels", json={"name": "Agent label", "color": BLUE}).status_code == 403
