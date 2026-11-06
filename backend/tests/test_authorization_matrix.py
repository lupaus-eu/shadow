"""Full authorization matrix across Organization, Shadow, and platform roles (ticket 23, ADR-0007).

Every actor calls every representative endpoint against Organization A. The
expected status encodes the role model: Owner ⊇ Admin ⊇ Member; per-Shadow
Editor and Viewer grants; Platform Users never reach customer routes; an
Owner of another Organization is a stranger to A. Mutations that succeed are
arranged so repeating them is harmless.
"""
from contextlib import ExitStack

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from datetime import timedelta

from app.billing import CancelResult, PortalSession, SeatIncreasePreview
from app.database import RequestContext, create_session_factory, transaction_session
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login
from test_platform_operations import _platform_app, platform_login

ACTORS = ("owner", "admin", "editor", "viewer", "member", "stranger", "platform_admin", "support_agent")
ALLOWED, DENIED = "allowed", "denied"


class MatrixStripe(Stripe):
    """Answers the billing calls only an Owner should ever reach."""

    def preview_seat_increase(self, request):
        return SeatIncreasePreview(id="preview", amount_due=3000, currency="eur", proration_date=NOW)

    def create_portal_session(self, *, customer_id, return_url):
        return PortalSession(url="https://billing.stripe.test/session")

    def update_customer(self, *, customer_id, name, email):
        return None

    def set_cancel_at_period_end(self, *, subscription_id, cancel, schedule_id=None):
        return CancelResult(cancel_at_period_end=cancel, current_period_end=NOW + timedelta(days=20))


@pytest.fixture(scope="module")
def world(database_url):
    with ExitStack() as stack:
        verifier = Verifier()
        owner_app = create_app(database_url=database_url, oidc_client=OIDC("matrix-owner", "matrix-owner@example.com"), stripe_billing=MatrixStripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
        owner = stack.enter_context(TestClient(owner_app))
        login(owner)
        organization_id = active_org(owner, verifier, seats=6)
        base = f"/api/v1/organizations/{organization_id}"
        clients = {"owner": owner}
        users = {}
        for actor, role in (("admin", "admin"), ("editor", "member"), ("viewer", "member"), ("member", "member")):
            application, user_id = join(owner_app, owner, organization_id, subject=f"matrix-{actor}", email=f"matrix-{actor}@example.com", role=role)
            clients[actor] = stack.enter_context(TestClient(application))
            login(clients[actor])
            users[actor] = user_id
        stranger_verifier = Verifier()
        stranger_app = create_app(database_url=database_url, oidc_client=OIDC("matrix-stranger", "matrix-stranger@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=stranger_verifier, clock=lambda: NOW)
        clients["stranger"] = stack.enter_context(TestClient(stranger_app))
        login(clients["stranger"])
        stranger_org = active_org(clients["stranger"], stranger_verifier)
        for actor in ("platform_admin", "support_agent"):
            clients[actor] = stack.enter_context(TestClient(_platform_app(database_url, f"matrix-{actor}", actor)))
            platform_login(clients[actor])
        memberships = {item["email"].split("@")[0].removeprefix("matrix-"): item for item in owner.get(f"{base}/memberships").json()}
        yield {"clients": clients, "base": base, "memberships": memberships, "organization_id": organization_id, "stranger_org": stranger_org, "engine": owner_app.state.database_engine}


# Each case: name, callable(world, client) -> response, set of actors allowed.
CASES = [
    ("open workspace", lambda w, c: c.get(w["base"]), {"owner", "admin", "editor", "viewer", "member"}),
    ("list people", lambda w, c: c.get(f"{w['base']}/memberships"), {"owner", "admin"}),
    ("preview bulk invitations", lambda w, c: c.post(f"{w['base']}/invitations/bulk", json={"emails": ["matrix-bulk@example.com"], "role": "member"}), {"owner", "admin"}),
    ("invite Member", lambda w, c: c.post(f"{w['base']}/invitations", json={"email": "matrix-invitee@example.com", "role": "member"}), {"owner", "admin"}),
    ("list own notifications", lambda w, c: c.get(f"{w['base']}/notifications"), {"owner", "admin", "editor", "viewer", "member"}),
    ("count unread notifications", lambda w, c: c.get(f"{w['base']}/notifications/unread-count"), {"owner", "admin", "editor", "viewer", "member"}),
    ("mark own notifications read", lambda w, c: c.post(f"{w['base']}/notifications/read-all"), {"owner", "admin", "editor", "viewer", "member"}),
    ("read notification settings", lambda w, c: c.get(f"{w['base']}/notification-settings"), {"owner", "admin", "editor", "viewer", "member"}),
    ("change notification settings", lambda w, c: c.put(f"{w['base']}/notification-settings", json={"settings": {"role_changed": {"in_app": True, "email": False}}}), {"owner", "admin", "editor", "viewer", "member"}),
    ("read activity", lambda w, c: c.get(f"{w['base']}/audit-events"), {"owner", "admin"}),
    ("list Support Access", lambda w, c: c.get(f"{w['base']}/support-access"), {"owner", "admin"}),
    ("read seats", lambda w, c: c.get(f"{w['base']}/billing/seats"), {"owner"}),
    ("preview seat increase", lambda w, c: c.post(f"{w['base']}/billing/seats/increase-preview", json={"target_seats": 7, "expected_version": 1}), {"owner"}),
    ("cancel the subscription", lambda w, c: c.post(f"{w['base']}/billing/cancel", json={"reason": "other"}), {"owner"}),
    ("undo the cancellation", lambda w, c: c.post(f"{w['base']}/billing/cancel/undo"), {"owner"}),
    ("subscribe again", lambda w, c: c.post(f"{w['base']}/billing/resubscribe", json={"seats": 3}), {"owner"}),
    ("transfer ownership", lambda w, c: c.post(f"{w['base']}/memberships/{w['memberships']['member']['id']}/transfer-ownership", json={"expected_version": 999, "keep_owner": False}), {"owner"}),
    ("read the billing contact", lambda w, c: c.get(f"{w['base']}/billing/contact"), {"owner"}),
    ("change the billing contact", lambda w, c: c.put(f"{w['base']}/billing/contact", json={"billing_name": "Northwind", "billing_email": "billing@example.com"}), {"owner"}),
    ("open billing portal", lambda w, c: c.post(f"{w['base']}/billing/portal"), {"owner"}),
    ("check deletion", lambda w, c: c.get(f"{w['base']}/deletion"), {"owner"}),
    ("platform health", lambda w, c: c.get("/api/v1/platform/health"), {"platform_admin", "support_agent"}),
    ("platform Organizations", lambda w, c: c.get("/api/v1/platform/organizations"), {"platform_admin"}),
    ("request Support Access", lambda w, c: c.post("/api/v1/platform/support-access", json={"organization_id": w["organization_id"], "case_reference": "MATRIX"}), {"support_agent"}),
]


@pytest.mark.parametrize(("name", "call", "allowed"), CASES, ids=[case[0] for case in CASES])
def test_authorization_matrix(world, name, call, allowed) -> None:
    outcomes = {}
    for actor in ACTORS:
        response = call(world, world["clients"][actor])
        outcomes[actor] = ALLOWED if response.status_code < 400 or response.status_code == 409 else DENIED
        if outcomes[actor] == DENIED:
            assert response.status_code in {401, 403, 404}, (name, actor, response.status_code, response.text)
    assert {actor for actor, outcome in outcomes.items() if outcome == ALLOWED} == allowed, (name, outcomes)


@pytest.mark.parametrize("actor", ["member", "editor", "viewer"])
def test_members_cannot_promote_themselves_or_others(world, actor) -> None:
    client = world["clients"][actor]
    own = world["memberships"][actor]
    for role in ("admin", "owner"):
        response = client.patch(f"{world['base']}/memberships/{own['id']}", json={"role": role, "expected_version": own["version"]})
        assert response.status_code == 403, (actor, role, response.text)
    other = world["memberships"]["member" if actor != "member" else "viewer"]
    assert client.patch(f"{world['base']}/memberships/{other['id']}", json={"role": "admin", "expected_version": other["version"]}).status_code == 403
    assert world["memberships"][actor]["role"] == "member"
    fresh = world["clients"]["owner"].get(f"{world['base']}/memberships").json()
    assert next(item for item in fresh if item["id"] == own["id"])["role"] == "member"


def test_admins_cannot_promote_themselves_or_anyone_to_owner(world) -> None:
    client = world["clients"]["admin"]
    own = world["memberships"]["admin"]
    assert client.patch(f"{world['base']}/memberships/{own['id']}", json={"role": "owner", "expected_version": own["version"]}).status_code == 403
    member = world["memberships"]["member"]
    assert client.patch(f"{world['base']}/memberships/{member['id']}", json={"role": "owner", "expected_version": member["version"]}).status_code == 403
    owner = world["memberships"]["owner"]
    assert client.patch(f"{world['base']}/memberships/{owner['id']}", json={"role": "member", "expected_version": owner["version"]}).status_code == 403


def test_a_stranger_cannot_reach_another_organizations_routes(world) -> None:
    stranger_base = f"/api/v1/organizations/{world['stranger_org']}"
    assert world["clients"]["owner"].get(stranger_base).status_code == 404
    assert world["clients"]["owner"].get(f"{stranger_base}/memberships").status_code in {403, 404}
    assert world["clients"]["stranger"].get(world["base"]).status_code in {403, 404}


def test_rls_hides_every_tenant_table_across_organizations(world) -> None:
    session_factory = create_session_factory(world["engine"])
    tables = ("organization_memberships", "organization_invitations", "audit_events", "support_access_requests",)
    with transaction_session(session_factory, RequestContext(organization_id=world["stranger_org"])) as session:
        foreign = {table: session.execute(text(f"SELECT count(*) FROM {table} WHERE organization_id = :id"), {"id": world["organization_id"]}).scalar_one() for table in tables}
    with transaction_session(session_factory, RequestContext()) as session:
        anonymous = {table: session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() for table in tables if table not in {"organization_memberships", "organization_invitations"}}
    assert set(foreign.values()) == {0}, foreign
    assert set(anonymous.values()) == {0}, anonymous
