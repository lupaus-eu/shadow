"""Per-Yearclock authorization matrix (ticket 09, ADR-0007)."""
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


def _event(client: TestClient, organization_id: str, yearclock: dict, title: str):
    return client.post(f"/api/v1/organizations/{organization_id}/yearclocks/{yearclock['id']}/events", json={"title": title, "lane_id": yearclock["lanes"][0]["id"], "starts_on": "2026-10-01"})


def test_yearclock_roles_follow_the_matrix(database_url: str) -> None:
    verifier = Verifier()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("matrix-owner", "matrix-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier, seats=4)
        member_app, member_id = join(owner_app, owner, organization_id, subject="matrix-member", email="matrix-member@example.com")
        admin_app, admin_id = join(owner_app, owner, organization_id, subject="matrix-admin", email="matrix-admin@example.com", role="admin")
        idle_app, _idle_id = join(owner_app, owner, organization_id, subject="matrix-idle", email="matrix-idle@example.com")
        base = f"/api/v1/organizations/{organization_id}/yearclocks"
        planning = owner.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        board = owner.post(base, json={"name": "Board"}).json()
        editor_grant = owner.put(f"{base}/{planning['id']}/access", json={"user_account_id": member_id, "role": "editor"}).json()
        owner.put(f"{base}/{board['id']}/access", json={"user_account_id": member_id, "role": "viewer"})
        owner.put(f"{base}/{board['id']}/access", json={"user_account_id": admin_id, "role": "viewer"})
        board_event = _event(owner, organization_id, board, "Board meeting").json()

    with TestClient(member_app) as member:
        login(member)
        workspace = {item["name"]: item["access_role"] for item in member.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"]}
        edit_planning = _event(member, organization_id, planning, "Budget")
        read_board = member.get(f"{base}/{board['id']}/events?window_start=2026-01-01")
        edit_board = _event(member, organization_id, board, "Not allowed")
        delete_board = member.delete(f"{base}/{board['id']}/events/{board_event['id']}?expected_version={board_event['version']}")
        grant_self = member.put(f"{base}/{board['id']}/access", json={"user_account_id": member_id, "role": "editor", "expected_version": 1})
        list_grants = member.get(f"{base}/{board['id']}/access")
        create_clock = member.post(base, json={"name": "Mine"})
    assert workspace == {planning["name"]: "editor", "Board": "viewer"}
    assert edit_planning.status_code == 201
    assert read_board.status_code == 200 and [item["title"] for item in read_board.json()] == ["Board meeting"]
    assert edit_board.status_code == 403
    assert delete_board.status_code == 403
    assert grant_self.status_code == 403
    assert list_grants.status_code == 403
    assert create_clock.status_code == 403

    with TestClient(admin_app) as admin:
        login(admin)
        admin_workspace = {item["name"]: item["access_role"] for item in admin.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"]}
        admin_edit = _event(admin, organization_id, board, "Admin agenda")
    assert admin_workspace == {planning["name"]: "editor", "Board": "editor"}
    assert admin_edit.status_code == 201

    with TestClient(idle_app) as idle:
        login(idle)
        idle_workspace = idle.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"]
        idle_read = idle.get(f"{base}/{planning['id']}/events")
        idle_detail = idle.get(f"{base}/{planning['id']}")
    assert idle_workspace == []
    assert idle_read.status_code == 403
    assert idle_detail.status_code == 404

    outsider_app = create_app(database_url=database_url, oidc_client=OIDC("matrix-outsider", "matrix-outsider@example.com"), clock=lambda: NOW)
    with TestClient(outsider_app) as outsider:
        login(outsider)
        assert outsider.get(f"/api/v1/organizations/{organization_id}").status_code == 404
        assert outsider.get(f"{base}/{planning['id']}/events").status_code == 404
        assert _event(outsider, organization_id, planning, "Intrusion").status_code == 404

    with TestClient(owner_app) as owner:
        login(owner)
        revoked = owner.delete(f"{base}/{planning['id']}/access/{member_id}?expected_version={editor_grant['version']}")
    assert revoked.status_code == 204
    with TestClient(member_app) as member:
        login(member)
        after = [item["name"] for item in member.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"]]
        assert _event(member, organization_id, planning, "After revocation").status_code == 403
    assert after == ["Board"]
    with owner_app.state.database_engine.connect() as connection:
        actions = connection.execute(text("SELECT action FROM audit_events WHERE organization_id = :id"), {"id": organization_id}).scalars().all()
    assert actions.count("yearclock.access_granted") == 3
    assert "yearclock.access_revoked" in actions
