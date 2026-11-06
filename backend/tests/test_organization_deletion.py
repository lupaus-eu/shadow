"""Organization deletion: Pending Deletion, the recovery window, restore, and purge (ticket 21)."""
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.database import RequestContext, create_session_factory, transaction_session
from app.jobs import ORGANIZATION_PURGE_JOB, run_one_background_job, schedule_organization_purge_jobs
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login
from test_platform_operations import _platform_app, platform_login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _organization(stack: ExitStack, database_url: str, subject: str):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    owner = stack.enter_context(TestClient(application))
    login(owner)
    organization_id = active_org(owner, verifier, seats=4)
    clock = owner.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
    created = owner.post(f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events", json={"title": "Secret merger", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01"})
    assert created.status_code == 201
    return application, owner, organization_id, clock


def _age_request(application, organization_id: str, days: int) -> None:
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET deletion_requested_at = now() - make_interval(days => :days) WHERE id = :id"), {"days": days, "id": organization_id})


def _count(application, table: str, organization_id: str) -> int:
    with application.state.database_engine.connect() as connection:
        return connection.execute(text(f"SELECT count(*) FROM {table} WHERE organization_id = :id"), {"id": organization_id}).scalar_one()


def test_only_owners_request_deletion_and_pending_deletion_closes_the_organization(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, clock = _organization(stack, database_url, "delete-owner")
    admin_app, _ = join(application, owner, organization_id, subject="delete-admin", email="delete-admin@example.com", role="admin")
    member_app, _ = join(application, owner, organization_id, subject="delete-member", email="delete-member@example.com")
    with TestClient(admin_app) as admin:
        login(admin)
        admin_request = admin.post(f"/api/v1/organizations/{organization_id}/deletion", json={"confirm": True}).status_code
    unconfirmed = owner.post(f"/api/v1/organizations/{organization_id}/deletion", json={"confirm": False}).status_code
    requested = owner.post(f"/api/v1/organizations/{organization_id}/deletion", json={"confirm": True})
    assert admin_request == 403 and unconfirmed == 422
    assert requested.status_code == 200 and requested.json()["status"] == "pending_deletion"
    purge_after = datetime.fromisoformat(requested.json()["purge_after"])
    assert timedelta(days=29, hours=23) < purge_after - datetime.now(UTC) <= timedelta(days=30)

    workspace = owner.get(f"/api/v1/organizations/{organization_id}").status_code
    events = owner.get(f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events").status_code
    create = owner.post(f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events", json={"title": "x", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-02"}).status_code
    listed = owner.get("/api/v1/organizations").json()["organizations"]
    again = owner.post(f"/api/v1/organizations/{organization_id}/deletion", json={"confirm": True}).status_code
    with TestClient(member_app) as member:
        login(member)
        member_listed = member.get("/api/v1/organizations").json()["organizations"]
        member_events = member.get(f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events").status_code
    assert workspace == 404 and events in {403, 404} and create in {403, 404, 409} and again == 409
    assert [(item["id"], item["status"]) for item in listed if item["id"] == organization_id] == [(organization_id, "pending_deletion")]
    assert all(item["id"] != organization_id for item in member_listed) and member_events in {403, 404}

    session_factory = create_session_factory(application.state.database_engine)
    with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
        visible = [session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in ("yearclocks", "events", "lanes", "organization_memberships")]
    assert visible == [0, 0, 0, 0]


def test_restore_inside_the_window_keeps_the_billing_state(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, clock = _organization(stack, database_url, "restore-owner")
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET subscription_access_state = 'canceled' WHERE id = :id"), {"id": organization_id})
    owner.post(f"/api/v1/organizations/{organization_id}/deletion", json={"confirm": True})
    restored = owner.post(f"/api/v1/organizations/{organization_id}/deletion/restore")
    workspace = owner.get(f"/api/v1/organizations/{organization_id}").json()
    events = owner.get(f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events", params={"window_start": "2026-09-01"}).json()
    actions = [item["action"] for item in owner.get(f"/api/v1/organizations/{organization_id}/audit-events").json()["items"]]
    assert restored.status_code == 200 and restored.json()["status"] == "active" and restored.json()["purge_after"] is None
    assert workspace["subscription"]["state"] == "read_only" and workspace["subscription"]["writable"] is False
    assert [item["title"] for item in events] == ["Secret merger"]
    assert "organization.deletion_requested" in actions and "organization.deletion_restored" in actions
    assert owner.post(f"/api/v1/organizations/{organization_id}/deletion/restore").status_code == 409

    # A read-only (unpaid) Organization can still be deleted.
    assert owner.post(f"/api/v1/organizations/{organization_id}/deletion", json={"confirm": True}).status_code == 200
    _age_request(application, organization_id, 31)
    late = owner.post(f"/api/v1/organizations/{organization_id}/deletion/restore")
    assert late.status_code == 409 and late.json()["detail"] == "The recovery window has ended"


def test_purge_removes_customer_content_and_keeps_minimal_evidence(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, _ = _organization(stack, database_url, "purge-owner")
    join(application, owner, organization_id, subject="purge-member", email="purge-member@example.com")
    owner.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "pending-invitee@example.com", "role": "member"})
    assert owner.put(f"/api/v1/organizations/{organization_id}/notification-settings", json={"summary": {"frequency": "daily"}}).status_code == 200
    assert _count(application, "notifications", organization_id) >= 1 and _count(application, "notification_preferences", organization_id) == 1
    agent = stack.enter_context(TestClient(_platform_app(database_url, "purge-agent", "support_agent")))
    platform_login(agent)
    assert agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-P"}).status_code == 201
    owner.post(f"/api/v1/organizations/{organization_id}/deletion", json={"confirm": True})
    session_factory = create_session_factory(application.state.database_engine)

    _age_request(application, organization_id, 29)
    schedule_organization_purge_jobs(session_factory, now=datetime.now(UTC))
    assert _count(application, "background_jobs", organization_id) == _count_jobs(application, organization_id, ORGANIZATION_PURGE_JOB) + _count_other_jobs(application, organization_id)
    assert _count_jobs(application, organization_id, ORGANIZATION_PURGE_JOB) == 0

    _age_request(application, organization_id, 31)
    assert schedule_organization_purge_jobs(session_factory, now=datetime.now(UTC)) >= 1
    schedule_organization_purge_jobs(session_factory, now=datetime.now(UTC))
    assert _count_jobs(application, organization_id, ORGANIZATION_PURGE_JOB) == 1
    while run_one_background_job(session_factory, organization_id=organization_id):
        pass
    with application.state.database_engine.connect() as connection:
        job = connection.execute(text("SELECT status, last_error FROM background_jobs WHERE organization_id = :id AND job_type = :type"), {"id": organization_id, "type": ORGANIZATION_PURGE_JOB}).one()
    assert job.status == "completed", job.last_error

    for table in ("yearclocks", "lanes", "categories", "events", "organization_memberships", "organization_invitations", "support_access_requests", "yearclock_access_grants", "notifications", "notification_preferences"):
        assert _count(application, table, organization_id) == 0, table
    with application.state.database_engine.connect() as connection:
        organization = connection.execute(text("SELECT status, purged_at, billing_email, stripe_customer_id FROM organizations WHERE id = :id"), {"id": organization_id}).one()
        summaries = connection.execute(text("SELECT action, change_summary FROM audit_events WHERE organization_id = :id"), {"id": organization_id}).all()
        payloads = connection.execute(text("SELECT payload FROM outbox_messages WHERE organization_id = :id"), {"id": organization_id}).scalars().all()
    assert organization.status == "purged" and organization.purged_at is not None
    assert organization.billing_email == "billing@example.com" and organization.stripe_customer_id
    actions = {row.action for row in summaries}
    assert {"organization.deletion_requested", "event.created", "organization.purged"} <= actions
    assert all(row.change_summary == {} for row in summaries) and "Secret merger" not in repr(summaries)
    assert payloads and all(payload == {} for payload in payloads)
    assert owner.get("/api/v1/organizations").json()["organizations"] == []
    assert owner.post(f"/api/v1/organizations/{organization_id}/deletion/restore").status_code == 403


def test_a_restored_organization_is_not_purged_by_a_stale_job(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, _ = _organization(stack, database_url, "stale-purge-owner")
    owner.post(f"/api/v1/organizations/{organization_id}/deletion", json={"confirm": True})
    _age_request(application, organization_id, 31)
    session_factory = create_session_factory(application.state.database_engine)
    schedule_organization_purge_jobs(session_factory, now=datetime.now(UTC))
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE organizations SET status = 'active', deletion_requested_at = NULL WHERE id = :id"), {"id": organization_id})
    while run_one_background_job(session_factory, organization_id=organization_id):
        pass
    assert _count(application, "yearclocks", organization_id) == 1
    assert _count(application, "events", organization_id) == 1


def test_audit_summaries_can_only_be_emptied_by_the_purge_scope(database_url: str, stack: ExitStack) -> None:
    application, _, organization_id, _ = _organization(stack, database_url, "audit-guard-owner")
    session_factory = create_session_factory(application.state.database_engine)
    with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
        assert session.execute(text("UPDATE audit_events SET change_summary = '{}'::jsonb")).rowcount == 0
    with pytest.raises(DBAPIError):
        with transaction_session(session_factory, RequestContext(organization_id=organization_id, worker_scope="purge")) as session:
            session.execute(text("UPDATE audit_events SET change_summary = '{\"x\": 1}'::jsonb"))
    with pytest.raises(DBAPIError):
        with transaction_session(session_factory, RequestContext(organization_id=organization_id, worker_scope="purge")) as session:
            session.execute(text("UPDATE audit_events SET action = 'forged'"))


def _count_jobs(application, organization_id: str, job_type: str) -> int:
    with application.state.database_engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM background_jobs WHERE organization_id = :id AND job_type = :type"), {"id": organization_id, "type": job_type}).scalar_one()


def _count_other_jobs(application, organization_id: str) -> int:
    with application.state.database_engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM background_jobs WHERE organization_id = :id AND job_type <> :type"), {"id": organization_id, "type": ORGANIZATION_PURGE_JOB}).scalar_one()
