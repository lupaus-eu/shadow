"""Operator console: Platform User sign-in, lifecycle views, and job replay (ticket 19)."""
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.main import create_app
from app.platform_admin import enroll
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, login


def platform_login(client: TestClient):
    response = client.get("/api/v1/auth/login?audience=platform", follow_redirects=False)
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    return client.get("/api/v1/auth/callback", params={"code": "test", "state": state}, follow_redirects=False)


def _enroll(engine, email: str, *roles: str) -> None:
    with Session(engine) as session, session.begin():
        enroll(session, email=email, roles=list(roles), now=datetime.now(UTC))


def _platform_app(database_url: str, subject: str, *roles: str):
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), clock=lambda: NOW)
    _enroll(application.state.database_engine, f"{subject}@example.com", *roles)
    return application


def test_enrolled_staff_sign_in_to_the_console_and_never_reach_customer_routes(database_url: str) -> None:
    application = _platform_app(database_url, "ops-admin", "platform_admin", "support_agent")
    with TestClient(application) as client:
        callback = platform_login(client)
        session = client.get("/api/v1/platform/session")
        customer_session = client.get("/api/v1/auth/session")
        customer_organizations = client.get("/api/v1/organizations")
        customer_login = client.get("/api/v1/auth/login", follow_redirects=False)
        state = parse_qs(urlparse(customer_login.headers["location"]).query)["state"][0]
        customer_callback = client.get("/api/v1/auth/callback", params={"code": "test", "state": state}, follow_redirects=False)
    assert callback.status_code == 303 and callback.headers["location"].endswith("/platform")
    assert session.status_code == 200 and session.json()["roles"] == ["platform_admin", "support_agent"]
    assert customer_session.status_code == 403
    assert customer_organizations.status_code == 403
    assert customer_callback.status_code == 403 and customer_callback.json()["detail"] == "customer account required"


def test_unenrolled_and_customer_identities_cannot_open_the_console(database_url: str) -> None:
    stranger = create_app(database_url=database_url, oidc_client=OIDC("ops-stranger", "ops-stranger@example.com"), clock=lambda: NOW)
    with TestClient(stranger) as client:
        denied = platform_login(client)
    verifier = Verifier()
    customer_app = create_app(database_url=database_url, oidc_client=OIDC("ops-customer", "ops-customer@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    _enroll(customer_app.state.database_engine, "ops-customer@example.com", "platform_admin")
    with TestClient(customer_app) as client:
        login(client)
        platform_api = [client.get(path).status_code for path in ("/api/v1/platform/session", "/api/v1/platform/organizations", "/api/v1/platform/health", "/api/v1/platform/jobs")]
        converted = platform_login(client)
    assert denied.status_code == 403 and denied.json()["detail"] == "platform enrollment required"
    assert platform_api == [403, 403, 403, 403]
    assert converted.status_code == 403 and converted.json()["detail"] == "platform account required"


def test_admins_see_lifecycle_and_health_without_content(database_url: str) -> None:
    verifier = Verifier()
    customer = create_app(database_url=database_url, oidc_client=OIDC("ops-tenant", "ops-tenant@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(customer) as client:
        login(client)
        organization_id = active_org(client, verifier)
        clock = client.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
        client.post(f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events", json={"title": "Confidential board plan", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-05-01"})
    admin = _platform_app(database_url, "ops-lifecycle", "platform_admin")
    agent = _platform_app(database_url, "ops-agent-only", "support_agent")
    with TestClient(admin) as client:
        platform_login(client)
        listed = client.get("/api/v1/platform/organizations").json()
        health = client.get("/api/v1/platform/health").json()
        content = client.get(f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events")
    with TestClient(agent) as client:
        platform_login(client)
        agent_organizations = client.get("/api/v1/platform/organizations").status_code
        agent_health = client.get("/api/v1/platform/health").status_code
    row = next(item for item in listed if item["id"] == organization_id)
    assert row["status"] == "active" and row["subscription"]["state"] == "active"
    assert row["members"] == 1 and row["yearclocks"] == 1 and row["purchased_seats"] == 2
    assert "Confidential board plan" not in repr(listed) and "Confidential board plan" not in repr(health)
    assert health["database"] == "ready" and health["organizations"]["active"] >= 1
    assert content.status_code == 403
    assert agent_organizations == 403 and agent_health == 200


def test_failed_jobs_are_inspectable_and_replay_is_idempotent_and_audited(database_url: str) -> None:
    verifier = Verifier()
    customer = create_app(database_url=database_url, oidc_client=OIDC("ops-jobs-owner", "ops-jobs-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(customer) as client:
        login(client)
        organization_id = active_org(client, verifier)
    job_id, email_id = uuid4(), uuid4()
    with customer.state.database_engine.begin() as connection:
        connection.execute(text("INSERT INTO background_jobs (id, organization_id, job_type, payload, idempotency_key, status, attempts, last_error) VALUES (:id, :org, 'content.purge', '{}', :key, 'failed', 5, 'RuntimeError: storage unavailable')"), {"id": job_id, "org": organization_id, "key": f"test:{job_id}"})
        connection.execute(text("INSERT INTO outbox_messages (id, organization_id, topic, payload, idempotency_key, status, attempts, last_error) VALUES (:id, :org, 'organization.invitation', CAST(:payload AS jsonb), :key, 'failed', 3, 'ConnectError: provider down')"), {"id": email_id, "org": organization_id, "payload": '{"to": "private@example.com", "text": "secret link"}', "key": f"test:{email_id}"})
    admin = _platform_app(database_url, "ops-replayer", "platform_admin")
    agent = _platform_app(database_url, "ops-viewer", "support_agent")
    with TestClient(agent) as client:
        platform_login(client)
        visible = {item["id"]: item for item in client.get("/api/v1/platform/jobs").json()}
        agent_replay = client.post(f"/api/v1/platform/jobs/job/{job_id}/replay").status_code
    with TestClient(admin) as client:
        platform_login(client)
        replayed = client.post(f"/api/v1/platform/jobs/job/{job_id}/replay").json()
        again = client.post(f"/api/v1/platform/jobs/job/{job_id}/replay").json()
        email = client.post(f"/api/v1/platform/jobs/email/{email_id}/replay").json()
        missing = client.post(f"/api/v1/platform/jobs/job/{uuid4()}/replay").status_code
        bad_status = client.get("/api/v1/platform/jobs?status=bogus").status_code
    failed_job, failed_email = visible[str(job_id)], visible[str(email_id)]
    assert (failed_job["type"], failed_job["attempts"], failed_job["last_error"]) == ("content.purge", 5, "RuntimeError: storage unavailable")
    assert failed_email["type"] == "organization.invitation" and "private@example.com" not in repr(visible) and "secret link" not in repr(visible)
    assert agent_replay == 403
    assert (replayed["status"], replayed["attempts"]) == ("pending", 0) and replayed["next_attempt_at"] is not None
    assert again["status"] == "pending"
    assert email["status"] == "pending"
    assert missing == 404 and bad_status == 422
    with customer.state.database_engine.connect() as connection:
        replays = connection.execute(text("SELECT target_id FROM audit_events WHERE organization_id = :org AND action = 'platform.job_replayed'"), {"org": organization_id}).scalars().all()
    assert sorted(map(str, replays)) == sorted([str(job_id), str(email_id)])
