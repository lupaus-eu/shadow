"""Acceptance coverage for PRD stories that were only partly demonstrated (v1-acceptance-trace.md)."""
import re
from contextlib import ExitStack
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.billing import StripeEvent
from app.database import RequestContext, create_session_factory, transaction_session
from app.invitations import create_invitation
from app.jobs import RECURRENCE_JOB, run_one_background_job
from app.main import create_app
from app.models import Organization, OutboxMessage
from app.work_queue import BackgroundJobDraft, enqueue_background_job
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, invitation_token, join, login
from test_platform_operations import _platform_app, platform_login

# Routes reachable without a customer or platform session, each with its own guard.
PUBLIC_ROUTES = {
    ("GET", "/health"),
    ("GET", "/api/v1/auth/login"),
    ("GET", "/api/v1/auth/callback"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/billing/stripe/webhook"),  # Stripe signature
    ("GET", "/api/v1/monitoring/health"),  # monitoring token
    ("GET", "/api/v1/legal/documents"),  # the repository's public texts
    ("GET", "/api/v1/legal/documents/{key}"),
}


@pytest.fixture
def stack():
    with ExitStack() as clients:
        yield clients


def _owner(stack, database_url, subject, *, seats=2, locale="en"):
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC(subject, f"{subject}@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    client = stack.enter_context(TestClient(application))
    login(client)
    organization_id = active_org(client, verifier, seats=seats)
    if locale != "en":
        with application.state.database_engine.begin() as connection:
            connection.execute(text("UPDATE organizations SET default_locale = :locale WHERE id = :id"), {"locale": locale, "id": organization_id})
    return application, client, verifier, organization_id


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda _: str(uuid4()), path)


def test_every_route_requires_a_session_except_the_guarded_public_ones(database_url) -> None:
    """Story 6: every customer and platform view requires authentication."""
    application = create_app(database_url=database_url)
    checked = []
    declared = {(method, route.path) for route in application.routes if isinstance(route, APIRoute) for method in route.methods}
    assert PUBLIC_ROUTES <= declared, PUBLIC_ROUTES - declared
    with TestClient(application, raise_server_exceptions=False) as client:
        for route in application.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in route.methods - {"HEAD", "OPTIONS"}:
                if (method, route.path) in PUBLIC_ROUTES:
                    continue
                response = client.request(method, _concrete(route.path), json={})
                checked.append((method, route.path, response.status_code))
    unprotected = [item for item in checked if item[2] != 401]
    assert len(checked) >= 70
    assert unprotected == []


def test_billing_state_of_one_organization_never_touches_another(database_url, stack) -> None:
    """Story 19: each Organization is billed independently."""
    _, client, verifier, first = _owner(stack, database_url, "billing-two-orgs")
    second = active_org(client, verifier)
    verifier.event = StripeEvent(id=f"evt_fail_{first}", type="invoice.payment_failed", checkout_session_id=None, organization_id=first, customer_id=f"cus_{first}", subscription_id=f"sub_{first}", payment_status=None, created_at=datetime.now(UTC), billing_reason="subscription_cycle")
    assert client.post("/api/v1/billing/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "test"}).status_code == 200
    first_state = client.get(f"/api/v1/organizations/{first}").json()["subscription"]["state"]
    second_state = client.get(f"/api/v1/organizations/{second}").json()["subscription"]["state"]
    first_seats = client.get(f"/api/v1/organizations/{first}/billing/seats").json()
    second_seats = client.get(f"/api/v1/organizations/{second}/billing/seats").json()
    assert first_state == "grace" and second_state == "active"
    assert first_seats["purchased"] == second_seats["purchased"] == 2 and second_seats["occupied"] == 1


def test_a_resent_invitation_invalidates_the_old_link(database_url, stack) -> None:
    """Story 42: resending invalidates the prior token."""
    application, owner, _, organization_id = _owner(stack, database_url, "resend-owner")
    invitation = owner.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "resend-invitee@example.com"}).json()
    old_token = invitation_token(application.state.database_engine, invitation["id"])
    resent = owner.post(f"/api/v1/organizations/{organization_id}/invitations/{invitation['id']}/resend?expected_version={invitation['version']}").json()
    new_token = invitation_token(application.state.database_engine, resent["id"])
    invitee = stack.enter_context(TestClient(create_app(database_url=database_url, oidc_client=OIDC("resend-invitee", "resend-invitee@example.com"), clock=lambda: NOW)))
    login(invitee)
    stale = invitee.post("/api/v1/invitations/accept", json={"token": old_token})
    fresh = invitee.post("/api/v1/invitations/accept", json={"token": new_token})
    assert stale.status_code in {404, 409, 410} and fresh.status_code == 200


def test_admins_cannot_invite_beyond_free_seats(database_url, stack) -> None:
    """Story 45: an Admin cannot invite when no seat is free."""
    application, owner, _, organization_id = _owner(stack, database_url, "seat-owner", seats=2)
    admin_app, _ = join(application, owner, organization_id, subject="seat-admin", email="seat-admin@example.com", role="admin")
    with TestClient(admin_app) as admin:
        login(admin)
        refused = admin.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "no-room@example.com"})
    assert refused.status_code == 409 and refused.json()["detail"] == "no Organization Seat is available"


def test_editors_edit_delete_and_restore_events(database_url, stack) -> None:
    """Story 48: an Editor creates, edits, restores, and removes Events."""
    application, owner, _, organization_id = _owner(stack, database_url, "editor-owner", seats=3)
    clock = owner.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
    editor_app, editor_id = join(application, owner, organization_id, subject="editor-user", email="editor-user@example.com")
    owner.put(f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/access", json={"user_account_id": editor_id, "role": "editor"})
    events = f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}/events"
    lane = clock["lanes"][0]["id"]
    with TestClient(editor_app) as editor:
        login(editor)
        created = editor.post(events, json={"title": "Draft", "lane_id": lane, "starts_on": "2026-10-01"}).json()
        edited = editor.patch(f"{events}/{created['id']}", json={"title": "Final", "lane_id": lane, "starts_on": "2026-10-02", "expected_version": 1})
        deleted = editor.delete(f"{events}/{created['id']}?expected_version=2")
        restored = editor.post(f"{events}/{created['id']}/restore?expected_version=3")
    assert edited.status_code == 200 and edited.json()["title"] == "Final"
    assert deleted.status_code == 204
    assert restored.status_code == 200 and restored.json()["deleted_at"] is None and restored.json()["version"] == 4


def test_removal_keeps_the_account_session_and_other_memberships(database_url, stack) -> None:
    """Story 50: removing a membership keeps the User Account and its other memberships."""
    application, owner, verifier, first = _owner(stack, database_url, "two-org-owner", seats=3)
    second = active_org(owner, verifier, seats=3)
    shared_app, _ = join(application, owner, first, subject="shared-user", email="shared-user@example.com")
    join(application, owner, second, subject="shared-user", email="shared-user@example.com")
    membership = next(item for item in owner.get(f"/api/v1/organizations/{first}/memberships").json() if item["email"] == "shared-user@example.com")
    with TestClient(shared_app) as shared:
        login(shared)
        assert owner.delete(f"/api/v1/organizations/{first}/memberships/{membership['id']}?expected_version={membership['version']}").status_code == 204
        session = shared.get("/api/v1/auth/session")
        remaining = [item["id"] for item in shared.get("/api/v1/organizations").json()["organizations"]]
        removed_workspace = shared.get(f"/api/v1/organizations/{first}").status_code
    assert session.status_code == 200 and remaining == [second] and removed_workspace == 404


def test_a_distant_planning_window_is_complete_without_the_worker(database_url, stack) -> None:
    """Story 88: a window beyond the materialization horizon still returns every Occurrence."""
    _, owner, _, organization_id = _owner(stack, database_url, "distant-owner")
    clock = owner.get(f"/api/v1/organizations/{organization_id}").json()["yearclocks"][0]
    base = f"/api/v1/organizations/{organization_id}/yearclocks/{clock['id']}"
    created = owner.post(f"{base}/series", json={"title": "Weekly sync", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-01-05", "frequency": "weekly", "interval": 1})
    assert created.status_code == 201, created.text
    listed = owner.get(f"{base}/events", params={"window_start": "2031-01-01"}).json()
    mondays = [date(2031, 1, 6) + timedelta(weeks=index) for index in range(53) if date(2031, 1, 6) + timedelta(weeks=index) <= date(2031, 12, 31)]
    assert sorted(item["starts_on"] for item in listed) == [day.isoformat() for day in mondays]
    again = owner.get(f"{base}/events", params={"window_start": "2031-01-01"}).json()
    assert len(again) == len(listed)


def test_a_failed_recurrence_job_can_be_replayed(database_url, stack) -> None:
    """Story 121: failed recurrence work is inspectable and replayable."""
    application, owner, _, organization_id = _owner(stack, database_url, "replay-owner")
    session_factory = create_session_factory(application.state.database_engine)
    with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
        job_id = enqueue_background_job(session, BackgroundJobDraft(job_type=RECURRENCE_JOB, payload={}, idempotency_key=f"replay:{uuid4()}"))
    with application.state.database_engine.begin() as connection:
        connection.execute(text("UPDATE background_jobs SET status = 'failed', attempts = 5, last_error = 'RuntimeError: boom' WHERE id = :id"), {"id": job_id})
    admin = stack.enter_context(TestClient(_platform_app(database_url, "replay-admin", "platform_admin")))
    platform_login(admin)
    listed = {item["id"] for item in admin.get("/api/v1/platform/jobs").json()}
    replayed = admin.post(f"/api/v1/platform/jobs/job/{job_id}/replay")
    ran = run_one_background_job(session_factory, organization_id=organization_id)
    with application.state.database_engine.connect() as connection:
        status = connection.execute(text("SELECT status FROM background_jobs WHERE id = :id"), {"id": job_id}).scalar_one()
    assert str(job_id) in listed and replayed.status_code == 200 and ran and status == "completed"


def test_a_job_for_one_organization_cannot_see_another(database_url, stack) -> None:
    """T7: background work runs inside its own Organization's RLS context."""
    application, owner, verifier, first = _owner(stack, database_url, "worker-isolation")
    second = active_org(owner, verifier)
    session_factory = create_session_factory(application.state.database_engine)
    seen = {}

    def spy(session, job, now):
        seen["yearclocks"] = session.execute(text("SELECT DISTINCT organization_id::text FROM yearclocks")).scalars().all()
        seen["organizations"] = session.execute(text("SELECT id::text FROM organizations")).scalars().all()
        seen["updated"] = session.execute(text("UPDATE yearclocks SET name = 'hijacked' WHERE organization_id = :other"), {"other": second}).rowcount

    with transaction_session(session_factory, RequestContext(organization_id=first)) as session:
        enqueue_background_job(session, BackgroundJobDraft(job_type="test.spy", payload={}, idempotency_key=f"spy:{uuid4()}"))
    assert run_one_background_job(session_factory, organization_id=first, handlers={"test.spy": spy})
    assert seen == {"yearclocks": [first], "organizations": [first], "updated": 0}
    assert owner.get(f"/api/v1/organizations/{second}").json()["yearclocks"][0]["name"] != "hijacked"


def test_invitation_and_email_commit_together_and_carry_no_secrets(database_url, stack, monkeypatch) -> None:
    """T9: the outbox row shares the Invitation's transaction; payloads hold no credentials."""
    monkeypatch.setenv("OIDC_CLIENT_SECRET", "oidc-secret-value")
    application, owner, _, organization_id = _owner(stack, database_url, "outbox-owner", seats=4, locale="fi")
    session_factory = create_session_factory(application.state.database_engine)
    with pytest.raises(RuntimeError):
        with transaction_session(session_factory, RequestContext(organization_id=organization_id)) as session:
            organization = session.get(Organization, organization_id)
            created = create_invitation(session, organization=organization, invited_by=organization.created_by_user_account_id, email="rolled-back@example.com", role="member", now=datetime.now(UTC), frontend_url="https://app.example", request_id="t9")
            assert session.scalar(select(OutboxMessage.id).where(OutboxMessage.idempotency_key == f"invitation:{created.invitation.id}:email"))
            raise RuntimeError("abort after enqueue")
    with application.state.database_engine.connect() as connection:
        leftovers = connection.execute(text("SELECT count(*) FROM outbox_messages WHERE payload->>'to' = 'rolled-back@example.com'")).scalar_one()
        invitations = connection.execute(text("SELECT count(*) FROM organization_invitations WHERE email = 'rolled-back@example.com'")).scalar_one()
    assert leftovers == 0 and invitations == 0

    owner.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "kept@example.com"})
    with application.state.database_engine.connect() as connection:
        payload = connection.execute(text("SELECT payload FROM outbox_messages WHERE payload->>'to' = 'kept@example.com'")).scalar_one()
    assert set(payload) == {"to", "subject", "text", "accept_url"}
    assert payload["subject"].startswith("Kutsu organisaatioon") and "Hyväksy kutsu" in payload["text"]
    serialized = repr(payload)
    for secret in ("oidc-secret-value", "sk_", "whsec_", "yearclock_session", owner.cookies.get("yearclock_session") or "no-cookie-value"):
        assert secret not in serialized


def test_removing_a_member_through_the_api_frees_a_seat(database_url, stack) -> None:
    """T10: seat release after a membership removal."""
    application, owner, _, organization_id = _owner(stack, database_url, "seat-release-owner", seats=2)
    join(application, owner, organization_id, subject="seat-release-member", email="seat-release-member@example.com")
    before = owner.get(f"/api/v1/organizations/{organization_id}/billing/seats").json()
    membership = next(item for item in owner.get(f"/api/v1/organizations/{organization_id}/memberships").json() if item["role"] == "member")
    assert owner.delete(f"/api/v1/organizations/{organization_id}/memberships/{membership['id']}?expected_version={membership['version']}").status_code == 204
    after = owner.get(f"/api/v1/organizations/{organization_id}/billing/seats").json()
    invited = owner.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": "next-member@example.com"})
    assert before["occupied"] == 2 and before["available"] == 0
    assert after["occupied"] == 1 and after["available"] == 1
    assert invited.status_code == 201


def test_a_failed_webhook_leaves_no_trace_so_stripe_redelivery_succeeds(database_url, stack, monkeypatch) -> None:
    """Story 121 (decision 2026-09-23): failed webhooks rely on Stripe redelivery."""
    import app.organization_routes as organization_routes

    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC("redelivery-owner", "redelivery-owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    client = stack.enter_context(TestClient(application, raise_server_exceptions=False))
    login(client)
    signup = client.post("/api/v1/organization-signups", json={"organization_name": "Redelivery", "time_zone": "Europe/Helsinki", "default_locale": "en", "billing_name": "Redelivery", "billing_email": "billing@example.com", "initial_seats": 2}).json()
    organization_id = signup["organization_id"]
    verifier.event = StripeEvent(f"evt_{organization_id}", "checkout.session.completed", f"cs_{organization_id}", organization_id, f"cus_{organization_id}", f"sub_{organization_id}", "paid")
    real = organization_routes.process_checkout_event

    def failing(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("database went away mid-webhook")

    monkeypatch.setattr(organization_routes, "process_checkout_event", failing)
    first = client.post("/api/v1/billing/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "test"})
    with application.state.database_engine.connect() as connection:
        recorded = connection.execute(text("SELECT count(*) FROM stripe_webhook_events WHERE event_id = :id"), {"id": f"evt_{organization_id}"}).scalar_one()
        status = connection.execute(text("SELECT status FROM organizations WHERE id = :id"), {"id": organization_id}).scalar_one()
    monkeypatch.setattr(organization_routes, "process_checkout_event", real)
    redelivered = client.post("/api/v1/billing/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "test"})
    assert first.status_code == 500 and recorded == 0 and status == "pending_activation"
    assert redelivered.status_code == 200 and redelivered.json()["outcome"] == "activated"
