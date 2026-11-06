"""Shared Yearclock layout (Yearclock V2, P1 tickets 02–04)."""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

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
    return application, owner, organization_id, base, clock


def test_editors_set_the_start_month_with_versions_and_audit(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "layout-start")
    assert clock["start_month"] == 1
    editor_app, editor_id = join(application, owner, organization_id, subject="layout-editor", email="layout-editor@example.com")
    viewer_app, viewer_id = join(application, owner, organization_id, subject="layout-viewer", email="layout-viewer@example.com")
    owner.put(f"{base}/yearclocks/{clock['id']}/access", json={"user_account_id": editor_id, "role": "editor"})
    owner.put(f"{base}/yearclocks/{clock['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    event = owner.post(f"{base}/yearclocks/{clock['id']}/events", json={"title": "Term starts", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-08-10"}).json()
    layout = f"{base}/yearclocks/{clock['id']}/layout"
    with TestClient(editor_app) as editor:
        login(editor)
        changed = editor.patch(layout, json={"start_month": 8, "expected_version": clock["version"]})
        stale = editor.patch(layout, json={"start_month": 9, "expected_version": clock["version"]})
    with TestClient(viewer_app) as viewer:
        login(viewer)
        refused = viewer.patch(layout, json={"start_month": 3, "expected_version": changed.json()["version"]})
        seen = next(item for item in viewer.get(base).json()["yearclocks"] if item["id"] == clock["id"])
    assert changed.status_code == 200 and changed.json()["start_month"] == 8 and changed.json()["version"] == clock["version"] + 1
    assert stale.status_code == 409 and stale.json()["detail"] == {"latest_version": changed.json()["version"]}
    assert refused.status_code == 403 and seen["start_month"] == 8
    assert owner.patch(layout, json={"start_month": 13, "expected_version": changed.json()["version"]}).status_code == 422
    unmoved = next(item for item in owner.get(f"{base}/yearclocks/{clock['id']}/events", params={"window_start": "2026-08-01"}).json() if item["id"] == event["id"])
    assert unmoved["starts_on"] == "2026-08-10" and unmoved["version"] == 1
    audit = next(item for item in owner.get(f"{base}/audit-events", params={"prefix": "yearclock"}).json()["items"] if item["action"] == "yearclock.layout_changed")
    assert audit["change_summary"] == {"start_month": 8}

    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    assert owner.patch(layout, json={"start_month": 1, "expected_version": changed.json()["version"]}).status_code == 403


def test_week_and_quarter_rings_are_shared_layout(database_url, stack) -> None:
    _, owner, _, base, clock = _world(stack, database_url, "layout-rings")
    assert (clock["show_week_ring"], clock["show_quarter_ring"]) == (False, False)
    layout = f"{base}/yearclocks/{clock['id']}/layout"
    both = owner.patch(layout, json={"show_week_ring": True, "show_quarter_ring": True, "expected_version": clock["version"]})
    weeks_off = owner.patch(layout, json={"show_week_ring": False, "expected_version": both.json()["version"]})
    unchanged = owner.patch(layout, json={"show_quarter_ring": True, "expected_version": weeks_off.json()["version"]})
    assert both.status_code == 200 and (both.json()["show_week_ring"], both.json()["show_quarter_ring"]) == (True, True)
    assert weeks_off.json()["show_week_ring"] is False and weeks_off.json()["show_quarter_ring"] is True
    assert unchanged.json()["version"] == weeks_off.json()["version"]
    summary = next(item for item in owner.get(base).json()["yearclocks"] if item["id"] == clock["id"])
    assert (summary["show_week_ring"], summary["show_quarter_ring"]) == (False, True)
    audits = [item["change_summary"] for item in owner.get(f"{base}/audit-events", params={"prefix": "yearclock"}).json()["items"] if item["action"] == "yearclock.layout_changed"]
    assert {"show_week_ring": True, "show_quarter_ring": True} in audits and {"show_week_ring": False} in audits


def test_lanes_take_a_palette_tint_and_a_height(database_url, stack) -> None:
    application, owner, organization_id, base, clock = _world(stack, database_url, "layout-lanes")
    lane = clock["lanes"][0]
    assert (lane["tint"], lane["height"]) == (None, "normal")
    url = f"{base}/yearclocks/{clock['id']}/lanes/{lane['id']}"
    styled = owner.patch(url, json={"name": lane["name"], "tint": "#1F5F99", "height": "tall", "expected_version": lane["version"]})
    assert styled.status_code == 200 and (styled.json()["tint"], styled.json()["height"]) == ("#1f5f99", "tall")
    renamed = owner.patch(url, json={"name": "Board", "expected_version": styled.json()["version"]})
    assert (renamed.json()["name"], renamed.json()["tint"], renamed.json()["height"]) == ("Board", "#1f5f99", "tall")
    cleared = owner.patch(url, json={"name": "Board", "tint": None, "expected_version": renamed.json()["version"]})
    assert cleared.json()["tint"] is None and cleared.json()["height"] == "tall"
    assert owner.patch(url, json={"name": "Board", "tint": "#123456", "expected_version": cleared.json()["version"]}).status_code == 422
    assert owner.patch(url, json={"name": "Board", "height": "huge", "expected_version": cleared.json()["version"]}).status_code == 422
    assert owner.patch(url, json={"name": "Board", "height": "normal", "expected_version": 1}).status_code == 409
    summary = next(item for item in owner.get(base).json()["yearclocks"] if item["id"] == clock["id"])["lanes"][0]
    assert (summary["tint"], summary["height"]) == (None, "tall")
    audits = [item["change_summary"] for item in owner.get(f"{base}/audit-events", params={"prefix": "lane"}).json()["items"] if item["action"] == "lane.updated"]
    assert {"tint": "#1f5f99", "height": "tall"} in audits and {"tint": None} in audits

    viewer_app, viewer_id = join(application, owner, organization_id, subject="layout-lane-viewer", email="layout-lane-viewer@example.com")
    owner.put(f"{base}/yearclocks/{clock['id']}/access", json={"user_account_id": viewer_id, "role": "viewer"})
    with TestClient(viewer_app) as viewer:
        login(viewer)
        assert viewer.patch(url, json={"name": "Board", "height": "normal", "expected_version": cleared.json()["version"]}).status_code == 403
