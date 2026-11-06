"""Organization audit activity (ticket 18, ADR-0014)."""
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.audit import AuditEventDraft, record_audit_event
from app.database import RequestContext, transaction_session
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, invitation_token, join, login


def test_owners_and_admins_browse_scoped_paginated_activity(database_url: str) -> None:
    verifier = Verifier()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("activity-owner", "activity-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier, seats=3)
        admin_app, _ = join(owner_app, owner, organization_id, subject="activity-admin", email="activity-admin@example.com", role="admin")
        member_app, _ = join(owner_app, owner, organization_id, subject="activity-member", email="activity-member@example.com")
        orgs = f"/api/v1/organizations/{organization_id}"
        clock = owner.get(orgs).json()["yearclocks"][0]
        for index in range(3):
            owner.post(f"{orgs}/yearclocks/{clock['id']}/events", json={"title": f"Event {index}", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-05-01"})
        first_page = owner.get(f"{orgs}/audit-events?limit=2").json()
        second_page = owner.get(f"{orgs}/audit-events?limit=2&offset={first_page['next_offset']}").json()
        events_only = owner.get(f"{orgs}/audit-events?prefix=event").json()["items"]
        exact = owner.get(f"{orgs}/audit-events?action=organization.invitation_accepted").json()["items"]
        bad_prefix = owner.get(f"{orgs}/audit-events?prefix=event%25").status_code
        viewing = owner.get(f"{orgs}/yearclocks/{clock['id']}/events")
        after_viewing = owner.get(f"{orgs}/audit-events?limit=100").json()["items"]
    with TestClient(admin_app) as admin:
        login(admin)
        admin_view = admin.get(f"{orgs}/audit-events").status_code
    with TestClient(member_app) as member:
        login(member)
        member_view = member.get(f"{orgs}/audit-events").status_code
    other_app = create_app(database_url=database_url, oidc_client=OIDC("activity-other", "activity-other@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(other_app) as other:
        login(other)
        other_org = active_org(other, verifier)
        cross = other.get(f"{orgs}/audit-events").status_code
        own_only = {item["target_id"] for item in other.get(f"/api/v1/organizations/{other_org}/audit-events?limit=100").json()["items"]}

    assert len(first_page["items"]) == 2 and first_page["next_offset"] == 2
    assert first_page["items"][0]["occurred_at"] >= first_page["items"][1]["occurred_at"]
    assert {item["id"] for item in first_page["items"]}.isdisjoint({item["id"] for item in second_page["items"]})
    assert [item["action"] for item in events_only] == ["event.created"] * 3
    assert events_only[0]["actor"] == "activity-owner@example.com"
    assert {item["actor"] for item in exact} == {"activity-admin@example.com", "activity-member@example.com"}
    assert bad_prefix == 422
    assert viewing.status_code == 200
    assert not any(item["action"].startswith(("event.read", "yearclock.viewed")) for item in after_viewing)
    assert admin_view == 200 and member_view == 403 and cross == 404
    assert organization_id not in own_only and clock["id"] not in own_only


def test_audit_summaries_hold_no_secrets_and_no_update_route_exists(database_url: str) -> None:
    verifier = Verifier()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("secrets-owner", "secrets-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        session_token = owner.cookies.get("yearclock_session")
        invitation = owner.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "secret-invitee@example.com"}).json()
        token = invitation_token(owner_app.state.database_engine, invitation["id"])
        items = owner.get(f"/api/v1/organizations/{organization_id}/audit-events?limit=100").json()["items"]
        mutation_attempts = [owner.request(method, f"/api/v1/organizations/{organization_id}/audit-events/{items[0]['id']}").status_code for method in ("PATCH", "PUT", "DELETE")]
    serialized = repr([item["change_summary"] for item in items])
    assert token not in serialized and session_token not in serialized
    assert "cs_" not in serialized and "whsec" not in serialized
    assert all(status in {404, 405} for status in mutation_attempts)


def test_audit_is_written_only_with_a_committed_change(database_url: str) -> None:
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC("atomic-owner", "atomic-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    engine, factory = application.state.database_engine, application.state.session_factory

    def count(organization_id: str) -> int:
        with engine.connect() as connection:
            return connection.execute(text("SELECT count(*) FROM audit_events WHERE organization_id = :id"), {"id": organization_id}).scalar_one()

    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        orgs = f"/api/v1/organizations/{organization_id}"
        clock = client.get(orgs).json()["yearclocks"][0]
        before = count(organization_id)
        stale = client.patch(f"{orgs}/yearclocks/{clock['id']}", json={"name": "Stale", "expected_version": 99})
        after_stale = count(organization_id)
        renamed = client.patch(f"{orgs}/yearclocks/{clock['id']}", json={"name": "Renamed", "expected_version": clock["version"]})
        after_rename = count(organization_id)
    assert stale.status_code == 409 and after_stale == before
    assert renamed.status_code == 200 and after_rename == before + 1

    with pytest.raises(RuntimeError), transaction_session(factory, RequestContext(user_account_id=uuid4(), organization_id=UUID(organization_id))) as session:
        record_audit_event(session, AuditEventDraft(action="rolled.back", target_type="system", target_id=uuid4(), request_id="rollback"))
        raise RuntimeError("mutation failed after auditing")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM audit_events WHERE action = 'rolled.back'")).scalar_one() == 0
