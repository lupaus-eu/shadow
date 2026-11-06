from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import OIDCIdentity
from app.billing import CheckoutRequest, CheckoutSession, StripeEvent
from app.main import create_app

NOW = datetime(2026, 7, 30, 9, 0, tzinfo=UTC)


class OIDC:
    def __init__(self, subject: str, email: str) -> None:
        self.subject, self.email = subject, email

    def authorization_url(self, **kwargs) -> str:
        return f"https://identity.example/authorize?state={kwargs['state']}"

    def exchange_code(self, **kwargs) -> OIDCIdentity:
        return OIDCIdentity("https://identity.example/application/o/yearclock/", self.subject, self.email, True, self.subject, 2_000_000_000)

    def end_session_url(self, **kwargs) -> str:
        return kwargs["post_logout_redirect_uri"]


class Stripe:
    def create_subscription_checkout(self, request: CheckoutRequest) -> CheckoutSession:
        return CheckoutSession(f"cs_{request.organization_id}", "https://checkout.test")


class Verifier:
    event: StripeEvent | None = None
    def verify(self, payload: bytes, signature: str | None) -> StripeEvent:
        assert self.event is not None
        return self.event


def login(client: TestClient) -> None:
    response = client.get("/api/v1/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    assert client.get("/api/v1/auth/callback", params={"code": "test", "state": state}, follow_redirects=False).status_code == 303


def active_org(client: TestClient, verifier: Verifier, *, seats: int = 2) -> str:
    signup = client.post("/api/v1/organization-signups", json={"organization_name": "Northwind", "time_zone": "Europe/Helsinki", "default_locale": "en", "billing_name": "Northwind", "billing_email": "billing@example.com", "initial_seats": seats}).json()
    org_id = signup["organization_id"]
    verifier.event = StripeEvent(f"evt_{org_id}", "checkout.session.completed", f"cs_{org_id}", org_id, f"cus_{org_id}", f"sub_{org_id}", "paid")
    assert client.post("/api/v1/billing/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "test"}).json()["outcome"] == "activated"
    return org_id


def invitation_token(engine, invitation_id: str) -> str:
    with engine.connect() as connection:
        body = connection.execute(text("SELECT payload->>'accept_url' FROM outbox_messages WHERE idempotency_key = :key"), {"key": f"invitation:{invitation_id}:email"}).scalar_one()
    return body.rsplit("/", 1)[1]


def test_invitation_reserves_capacity_and_authenticated_acceptance_converts_it(database_url: str) -> None:
    verifier = Verifier()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("owner", "owner@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        org_id = active_org(owner, verifier)
        invitation = owner.post(f"/api/v1/organizations/{org_id}/invitations", json={"email": "invitee@example.com"})
        seats = owner.get(f"/api/v1/organizations/{org_id}/billing/seats")
        unavailable = owner.post(f"/api/v1/organizations/{org_id}/invitations", json={"email": "second@example.com"})
    assert invitation.status_code == 201
    assert seats.json()["reserved"] == 1
    assert seats.json()["available"] == 0
    assert unavailable.status_code == 409
    token = invitation_token(owner_app.state.database_engine, invitation.json()["id"])
    wrong_app = create_app(database_url=database_url, oidc_client=OIDC("wrong", "wrong@example.com"), clock=lambda: NOW)
    with TestClient(wrong_app) as wrong:
        login(wrong)
        assert wrong.post("/api/v1/invitations/accept", json={"token": token}).status_code == 404
    invitee_app = create_app(database_url=database_url, oidc_client=OIDC("invitee", "invitee@example.com"), clock=lambda: NOW)
    with TestClient(invitee_app) as invitee:
        login(invitee)
        accepted = invitee.post("/api/v1/invitations/accept", json={"token": token})
        duplicate = invitee.post("/api/v1/invitations/accept", json={"token": token})
        organizations = invitee.get("/api/v1/organizations")
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"
    assert duplicate.status_code == 409
    assert organizations.json()["organizations"] == [{"id": org_id, "name": "Northwind", "role": "member", "status": "active", "purge_after": None}]


def test_resend_revocation_and_expiry_release_reserved_capacity(database_url: str) -> None:
    now = [NOW]
    verifier = Verifier()
    app = create_app(database_url=database_url, oidc_client=OIDC("owner-two", "owner-two@example.com"), stripe_billing=Stripe(), stripe_webhook_verifier=verifier, clock=lambda: now[0])
    with TestClient(app) as owner:
        login(owner)
        org_id = active_org(owner, verifier)
        first = owner.post(f"/api/v1/organizations/{org_id}/invitations", json={"email": "first@example.com"}).json()
        old_token = invitation_token(app.state.database_engine, first["id"])
        resent = owner.post(f"/api/v1/organizations/{org_id}/invitations/{first['id']}/resend?expected_version={first['version']}").json()
        revoked = owner.delete(f"/api/v1/organizations/{org_id}/invitations/{resent['id']}?expected_version={resent['version']}")
        after_revoke = owner.get(f"/api/v1/organizations/{org_id}/billing/seats")
        expiring = owner.post(f"/api/v1/organizations/{org_id}/invitations", json={"email": "expired@example.com"}).json()
        now[0] += timedelta(days=7)
        login(owner)
        expired = owner.get(f"/api/v1/organizations/{org_id}/invitations")
        after_expiry = owner.get(f"/api/v1/organizations/{org_id}/billing/seats")
    assert old_token != invitation_token(app.state.database_engine, resent["id"])
    assert revoked.status_code == 204
    assert after_revoke.json()["reserved"] == 0
    assert expired.status_code == 200
    assert next(item for item in expired.json() if item["id"] == expiring["id"])["status"] == "expired"
    assert after_expiry.json()["reserved"] == 0


def join(owner_app, owner: TestClient, organization_id: str, *, subject: str, email: str, role: str = "member"):
    """Invite, accept, and return (application, user_account_id) for a new member."""
    invitation = owner.post(f"/api/v1/organizations/{organization_id}/invitations", json={"email": email, "role": role})
    assert invitation.status_code == 201, invitation.text
    token = invitation_token(owner_app.state.database_engine, invitation.json()["id"])
    member_app = create_app(database_url=str(owner_app.state.database_engine.url.render_as_string(hide_password=False)), oidc_client=OIDC(subject, email), clock=lambda: NOW)
    with TestClient(member_app) as member:
        login(member)
        assert member.post("/api/v1/invitations/accept", json={"token": token}).status_code == 200
        user_id = member.get("/api/v1/auth/session").json()["user_account"]["id"]
    return member_app, user_id
