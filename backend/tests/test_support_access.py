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
    return application, client, organization_id, None


def _agent(stack: ExitStack, database_url: str, subject: str):
    client = stack.enter_context(TestClient(_platform_app(database_url, subject, "support_agent")))
    platform_login(client)
    return client


def _actions(client: TestClient, organization_id: str) -> list[dict]:
    return client.get(f"/api/v1/organizations/{organization_id}/audit-events", params={"limit": 100}).json()["items"]


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
    borrowed = other.get(f"/api/v1/platform/support-access/{grant['id']}/shadows").status_code
    assert admin_request == 403 and unknown == 404 and too_long == 422 and customer == 403 and borrowed == 404


