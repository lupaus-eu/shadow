from fastapi.testclient import TestClient

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, invitation_token, login


def test_editor_grant_limits_lane_changes_to_one_yearclock(database_url: str) -> None:
    verifier = Verifier()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("access-owner", "owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        invitation = owner.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "editor@example.com"})
        token = invitation_token(owner_app.state.database_engine, invitation.json()["id"])

    editor_app = create_app(database_url=database_url, oidc_client=OIDC("access-editor", "editor@example.com"), clock=lambda: NOW)
    with TestClient(editor_app) as editor:
        login(editor)
        assert editor.post("/api/v1/invitations/accept", json={"token": token}).status_code == 200
        editor_id = editor.get("/api/v1/auth/session").json()["user_account"]["id"]

    with TestClient(owner_app) as owner:
        login(owner)
        workspace = owner.get(f"/api/v1/organizations/{organization_id}").json()
        yearclock_id = workspace["yearclocks"][0]["id"]
        granted = owner.put(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/access", json={"user_account_id": editor_id, "role": "editor"})
        assert granted.status_code == 200
        grants = owner.get(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/access")
        assert grants.json() == [{"id": granted.json()["id"], "user_account_id": editor_id, "role": "editor", "version": 1}]

    with TestClient(editor_app) as editor:
        login(editor)
        lane = editor.post(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/lanes", json={"name": "Editor lane"})
        event = editor.post(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/events", json={"title": "Board meeting", "lane_id": lane.json()["id"], "starts_on": "2026-09-01"})
        category = editor.post(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/categories", json={"name": "Governance", "color": "#336699"})
        changed_category = editor.patch(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/categories/{category.json()['id']}", json={"name": "Board", "color": "#663399", "expected_version": 1})
        forbidden_clock = editor.post(f"/api/v1/organizations/{organization_id}/yearclocks", json={"name": "Forbidden"})
    assert lane.status_code == 201
    assert event.status_code == 201
    assert changed_category.status_code == 200
    assert forbidden_clock.status_code == 403

    with TestClient(owner_app) as owner:
        login(owner)
        viewer = owner.put(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/access", json={"user_account_id": editor_id, "role": "viewer", "expected_version": 1})
        assert viewer.status_code == 200
    with TestClient(editor_app) as editor:
        login(editor)
        forbidden_lane = editor.post(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/lanes", json={"name": "Not allowed"})
        forbidden_event = editor.delete(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/events/{event.json()['id']}?expected_version={event.json()['version']}")
    assert forbidden_lane.status_code == 403
    assert forbidden_event.status_code == 403
