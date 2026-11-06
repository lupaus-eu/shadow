"""Customer-approved Support Access: request, decide, use, expire, revoke (ticket 20)."""
from contextlib import ExitStack
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.database import RequestContext, create_session_factory, transaction_session
from app.main import create_app
from app.support_access_routes import expire_support_access
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login
from test_platform_operations import _platform_app, platform_login


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _customer(stack: ExitStack, database_url: str, subject: str):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    client = stack.enter_context(TestClient(application))
    login(client)
    organization_id = active_org(client, verifier, seats=3)
    clock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
    created = client.post(f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events", json={"title": "Budget review", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-01"})
    assert created.status_code == 201, created.text
    return application, client, organization_id, clock


def _agent(stack: ExitStack, database_url: str, subject: str):
    client = stack.enter_context(TestClient(_platform_app(database_url, subject, "support_agent")))
    platform_login(client)
    return client


def _actions(client: TestClient, organization_id: str) -> list[dict]:
    return client.get(f"/api/v1/organizations/{organization_id}/audit-events", params={"limit": 100}).json()["items"]


def test_read_grant_lets_the_agent_read_and_nothing_more(database_url: str, stack: ExitStack) -> None:
    _, owner, organization_id, clock = _customer(stack, database_url, "support-owner")
    agent = _agent(stack, database_url, "support-agent-read")
    requested = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-1", "hours": 4})
    assert requested.status_code == 201, requested.text
    grant = requested.json()
    assert grant["status"] == "pending" and grant["scope"] == "read" and grant["requested_hours"] == 4

    before = agent.get(f"/api/v1/platform/support-access/{grant['id']}/yearclocks")
    listed = owner.get(f"/api/v1/organizations/{organization_id}/support-access").json()
    too_long = owner.post(f"/api/v1/organizations/{organization_id}/support-access/{grant['id']}/approve", json={"hours": 5})
    approved = owner.post(f"/api/v1/organizations/{organization_id}/support-access/{grant['id']}/approve", json={"hours": 2})
    assert before.status_code == 403
    assert [item["case_reference"] for item in listed] == ["CASE-1"]
    assert too_long.status_code == 422
    assert approved.status_code == 200 and approved.json()["status"] == "approved"

    clocks = agent.get(f"/api/v1/platform/support-access/{grant['id']}/yearclocks")
    events = agent.get(f"/api/v1/platform/support-access/{grant['id']}/yearclocks/{clock['id']}/events", params={"window_start": "2026-09-01"})
    write = agent.post(f"/api/v1/platform/support-access/{grant['id']}/yearclocks/{clock['id']}/events", json={"title": "Injected", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-02"})
    customer_route = agent.get(f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events")
    assert clocks.status_code == 200 and clocks.json()[0]["id"] == clock["id"]
    assert [item["title"] for item in events.json()] == ["Budget review"]
    assert write.status_code == 403 and write.json()["detail"] == "Support Access is read-only"
    assert customer_route.status_code == 403

    actions = [(item["action"], item["support_access_id"]) for item in _actions(owner, organization_id)]
    assert ("support_access.requested", None) in actions and ("support_access.approved", None) in actions
    assert actions.count(("support_access.content_read", grant["id"])) == 2
    assert next(item for item in _actions(owner, organization_id) if item["action"] == "support_access.content_read")["actor"].startswith("Platform support")


def test_write_grant_edits_events_and_revocation_fails_closed(database_url: str, stack: ExitStack) -> None:
    _, owner, organization_id, clock = _customer(stack, database_url, "support-writer-owner")
    agent = _agent(stack, database_url, "support-agent-write")
    grant = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-2", "scope": "write", "hours": 1}).json()
    owner.post(f"/api/v1/organizations/{organization_id}/support-access/{grant['id']}/approve")
    created = agent.post(f"/api/v1/platform/support-access/{grant['id']}/yearclocks/{clock['id']}/events", json={"title": "Fixed by support", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-03"})
    assert created.status_code == 201, created.text
    updated = agent.patch(f"/api/v1/platform/support-access/{grant['id']}/yearclocks/{clock['id']}/events/{created.json()['id']}", json={"title": "Fixed again", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-10-03", "expected_version": 1})
    assert updated.status_code == 200 and updated.json()["version"] == 2

    revoked = owner.post(f"/api/v1/organizations/{organization_id}/support-access/{grant['id']}/revoke")
    after = agent.get(f"/api/v1/platform/support-access/{grant['id']}/yearclocks")
    again = owner.post(f"/api/v1/organizations/{organization_id}/support-access/{grant['id']}/revoke")
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    assert after.status_code == 403 and again.status_code == 409

    audit = _actions(owner, organization_id)
    mutations = [item for item in audit if item["action"] in {"event.created", "event.updated"} and item["support_access_id"] == grant["id"]]
    assert len(mutations) == 2 and all(item["actor"].startswith("Platform support") for item in mutations)
    assert any(item["action"] == "support_access.revoked" for item in audit)


def test_expired_grants_fail_closed_and_are_audited_once(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, _ = _customer(stack, database_url, "support-expiry-owner")
    agent = _agent(stack, database_url, "support-agent-expiry")
    grant = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-3"}).json()
    owner.post(f"/api/v1/organizations/{organization_id}/support-access/{grant['id']}/approve")
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE support_access_requests SET expires_at = now() - interval '1 minute' WHERE id = :id"), {"id": grant["id"]})
    session_factory = create_session_factory(application.state.database_engine)
    assert expire_support_access(session_factory) >= 1
    assert expire_support_access(session_factory) == 0
    denied = agent.get(f"/api/v1/platform/support-access/{grant['id']}/yearclocks")
    mine = {item["id"]: item for item in agent.get("/api/v1/platform/support-access").json()}
    assert denied.status_code == 403 and mine[grant["id"]]["status"] == "expired"
    assert [item["action"] for item in _actions(owner, organization_id)].count("support_access.expired") == 1


def test_only_owners_and_admins_decide_and_agents_cannot_self_approve(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, _ = _customer(stack, database_url, "support-roles-owner")
    member_app, _ = join(application, owner, organization_id, subject="support-member", email="support-member@example.com")
    admin_app, _ = join(application, owner, organization_id, subject="support-admin", email="support-admin@example.com", role="admin")
    agent = _agent(stack, database_url, "support-agent-roles")
    first = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-4"}).json()
    second = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-5"}).json()
    self_approve = agent.post(f"/api/v1/organizations/{organization_id}/support-access/{first['id']}/approve")
    with TestClient(member_app) as member:
        login(member)
        member_list = member.get(f"/api/v1/organizations/{organization_id}/support-access").status_code
        member_approve = member.post(f"/api/v1/organizations/{organization_id}/support-access/{first['id']}/approve").status_code
    with TestClient(admin_app) as admin:
        login(admin)
        admin_reject = admin.post(f"/api/v1/organizations/{organization_id}/support-access/{first['id']}/reject")
    owner_approve_rejected = owner.post(f"/api/v1/organizations/{organization_id}/support-access/{first['id']}/approve").status_code
    owner_approve = owner.post(f"/api/v1/organizations/{organization_id}/support-access/{second['id']}/approve").status_code
    assert self_approve.status_code == 403
    assert member_list == 403 and member_approve == 403
    assert admin_reject.status_code == 200 and admin_reject.json()["status"] == "rejected"
    assert owner_approve_rejected == 409 and owner_approve == 200


def test_requests_need_a_support_agent_and_an_active_organization(database_url: str, stack: ExitStack) -> None:
    _, owner, organization_id, _ = _customer(stack, database_url, "support-scope-owner")
    admin = TestClient(_platform_app(database_url, "support-platform-admin", "platform_admin"))
    with admin:
        platform_login(admin)
        admin_request = admin.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-6"}).status_code
    agent = _agent(stack, database_url, "support-agent-scope")
    unknown = agent.post("/api/v1/platform/support-access", json={"organization_id": str(uuid4()), "case_reference": "CASE-7"}).status_code
    too_long = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-8", "hours": 25}).status_code
    customer = owner.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-9"}).status_code
    other = _agent(stack, database_url, "support-agent-other")
    grant = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-10"}).json()
    owner.post(f"/api/v1/organizations/{organization_id}/support-access/{grant['id']}/approve")
    borrowed = other.get(f"/api/v1/platform/support-access/{grant['id']}/yearclocks").status_code
    assert admin_request == 403 and unknown == 404 and too_long == 422 and customer == 403 and borrowed == 404


def test_postgres_refuses_content_under_an_inactive_or_read_only_grant(database_url: str, stack: ExitStack) -> None:
    application, owner, organization_id, clock = _customer(stack, database_url, "support-rls-owner")
    agent = _agent(stack, database_url, "support-agent-rls")
    grant = agent.post("/api/v1/platform/support-access", json={"organization_id": organization_id, "case_reference": "CASE-11"}).json()
    session_factory = create_session_factory(application.state.database_engine)
    context = RequestContext(organization_id=organization_id, support_access_id=grant["id"])
    with transaction_session(session_factory, context) as session:
        pending_rows = session.execute(text("SELECT count(*) FROM events")).scalar_one()
    owner.post(f"/api/v1/organizations/{organization_id}/support-access/{grant['id']}/approve")
    with transaction_session(session_factory, context) as session:
        approved_rows = session.execute(text("SELECT count(*) FROM events")).scalar_one()
    with pytest.raises(ProgrammingError):
        with transaction_session(session_factory, context) as session:
            session.execute(text("UPDATE events SET title = 'tampered' WHERE yearclock_id = :id"), {"id": clock["id"]})
            session.execute(text("INSERT INTO lanes (id, organization_id, yearclock_id, name) VALUES (:id, :org, :clock, 'x')"), {"id": uuid4(), "org": organization_id, "clock": clock["id"]})
    other_org = RequestContext(organization_id=uuid4(), support_access_id=grant["id"])
    with transaction_session(session_factory, other_org) as session:
        foreign_rows = session.execute(text("SELECT count(*) FROM yearclocks")).scalar_one()
    with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
        titles = session.execute(text("SELECT title FROM events WHERE yearclock_id = :id"), {"id": clock["id"]}).scalars().all()
    assert pending_rows == 0 and approved_rows >= 1 and foreign_rows == 0
    assert "tampered" not in titles
