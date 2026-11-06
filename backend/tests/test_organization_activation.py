import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import AuthSettings, OIDCIdentity
from app.billing import (
    CheckoutRequest,
    CheckoutSession,
    StripeEvent,
    StripeSignatureVerifier,
)
from app.main import create_app

NOW = datetime(2026, 7, 29, 9, 0, tzinfo=UTC)


class FakeOIDCClient:
    def authorization_url(
        self,
        *,
        state: str,
        nonce: str,
        code_challenge: str,
        redirect_uri: str,
    ) -> str:
        return f"https://identity.example/authorize?state={state}"

    def exchange_code(
        self,
        *,
        code: str,
        code_verifier: str,
        nonce: str,
        redirect_uri: str,
    ) -> OIDCIdentity:
        return OIDCIdentity(
            issuer="https://identity.example/application/o/shadow/",
            subject="organization-owner",
            email="owner@example.com",
            email_verified=True,
            display_name="Organization Owner",
            expires_at=2_000_000_000,
        )

    def end_session_url(self, *, post_logout_redirect_uri: str, id_token_hint: str | None = None) -> str:
        return post_logout_redirect_uri


class FakeStripeBilling:
    def __init__(self) -> None:
        self.checkout_requests: list[CheckoutRequest] = []

    def create_subscription_checkout(
        self,
        request: CheckoutRequest,
    ) -> CheckoutSession:
        self.checkout_requests.append(request)
        return CheckoutSession(
            id=f"cs_test_{request.organization_id}",
            url=f"https://checkout.stripe.test/{request.organization_id}",
        )


class FakeStripeWebhookVerifier:
    def __init__(self) -> None:
        self.event: StripeEvent | None = None

    def verify(self, payload: bytes, signature: str | None) -> StripeEvent:
        assert payload
        assert signature == "valid-test-signature"
        assert self.event is not None
        return self.event


class MutableClock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def log_in(client: TestClient) -> None:
    login_response = client.get("/api/v1/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
    response = client.get(
        "/api/v1/auth/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert response.status_code == 303


def signup(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/organization-signups",
        headers={"X-Request-ID": "organization-signup-test"},
        json={
            "organization_name": "Northwind Oy",
            "time_zone": "Europe/Helsinki",
            "default_locale": "fi",
            "billing_name": "Northwind Oy",
            "billing_email": "billing@northwind.example",
            "initial_seats": 3,
        },
    )
    assert response.status_code == 201
    return response.json()


def paid_event(signup_response: dict, *, event_id: str) -> StripeEvent:
    organization_id = signup_response["organization_id"]
    return StripeEvent(
        id=event_id,
        type="checkout.session.completed",
        checkout_session_id=f"cs_test_{organization_id}",
        organization_id=organization_id,
        customer_id=f"cus_{organization_id}",
        subscription_id=f"sub_{organization_id}",
        payment_status="paid",
    )


def test_authenticated_customer_starts_a_pending_subscription_checkout(
    database_url: str,
) -> None:
    stripe = FakeStripeBilling()
    verifier = FakeStripeWebhookVerifier()
    application = create_app(
        database_url=database_url,
        oidc_client=FakeOIDCClient(),
        stripe_billing=stripe,
        stripe_webhook_verifier=verifier,
        clock=lambda: NOW,
    )

    with TestClient(application) as client:
        anonymous_response = client.post(
            "/api/v1/organization-signups",
            json={
                "organization_name": "Northwind Oy",
                "time_zone": "Europe/Helsinki",
                "default_locale": "fi",
                "billing_name": "Northwind Oy",
                "billing_email": "billing@northwind.example",
                "initial_seats": 3,
            },
        )
        log_in(client)
        response_data = signup(client)
        status_response = client.get(
            f"/api/v1/organization-signups/{response_data['organization_id']}"
        )

    assert anonymous_response.status_code == 401
    assert response_data["status"] == "pending_activation"
    assert response_data["checkout_url"].startswith(
        "https://checkout.stripe.test/"
    )
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "pending_activation"
    assert status_response.json()["initial_content"] is None
    assert stripe.checkout_requests == [
        CheckoutRequest(
            organization_id=response_data["organization_id"],
            organization_name="Northwind Oy",
            billing_email="billing@northwind.example",
            seats=3,
            locale="fi",
            expires_at=datetime(2026, 7, 30, 9, 0, tzinfo=UTC),
        )
    ]
    with application.state.database_engine.connect() as connection:
        audit_event = connection.execute(
            text(
                """
                SELECT actor_user_account_id, organization_id, action, request_id
                FROM audit_events
                WHERE target_id = :organization_id
                  AND action = 'organization.signup_started'
                """
            ),
            {"organization_id": response_data["organization_id"]},
        ).one()
    assert str(audit_event.actor_user_account_id)
    assert str(audit_event.organization_id) == response_data["organization_id"]
    assert audit_event.action == "organization.signup_started"
    assert audit_event.request_id == "organization-signup-test"


def test_verified_paid_event_activates_once_and_creates_localized_content(
    database_url: str,
) -> None:
    stripe = FakeStripeBilling()
    verifier = FakeStripeWebhookVerifier()
    application = create_app(
        database_url=database_url,
        oidc_client=FakeOIDCClient(),
        stripe_billing=stripe,
        stripe_webhook_verifier=verifier,
        clock=lambda: NOW,
    )

    with TestClient(application) as client:
        log_in(client)
        signup_response = signup(client)
        verifier.event = paid_event(signup_response, event_id="evt_paid_once")

        activation = client.post(
            "/api/v1/billing/stripe/webhook",
            content=b'{"test": true}',
            headers={"Stripe-Signature": "valid-test-signature"},
        )
        duplicate = client.post(
            "/api/v1/billing/stripe/webhook",
            content=b'{"test": true}',
            headers={"Stripe-Signature": "valid-test-signature"},
        )
        status_response = client.get(
            f"/api/v1/organization-signups/{signup_response['organization_id']}"
        )
        with application.state.database_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM organization_memberships
                    WHERE organization_id = :organization_id
                    """
                ),
                {"organization_id": signup_response["organization_id"]},
            )
        after_membership_removal = client.get(
            f"/api/v1/organization-signups/{signup_response['organization_id']}"
        )

    assert activation.json() == {
        "received": True,
        "processed": True,
        "duplicate": False,
        "outcome": "activated",
    }
    assert duplicate.json() == {
        "received": True,
        "processed": True,
        "duplicate": True,
        "outcome": "activated",
    }
    active = status_response.json()
    assert active["status"] == "active"
    assert active["initial_seats"] == 3
    assert active["initial_content"]["owner_user_account_id"]
    assert after_membership_removal.status_code == 404


def test_unpaid_or_abandoned_checkout_never_grants_access(
    database_url: str,
) -> None:
    clock = MutableClock()
    verifier = FakeStripeWebhookVerifier()
    application = create_app(
        database_url=database_url,
        oidc_client=FakeOIDCClient(),
        stripe_billing=FakeStripeBilling(),
        stripe_webhook_verifier=verifier,
        clock=clock,
        auth_settings=AuthSettings(session_max_age=timedelta(hours=48)),
    )

    with TestClient(application) as client:
        log_in(client)
        unpaid_signup = signup(client)
        verifier.event = StripeEvent(
            **{
                **paid_event(unpaid_signup, event_id="evt_unpaid").__dict__,
                "payment_status": "unpaid",
            }
        )
        unpaid_webhook = client.post(
            "/api/v1/billing/stripe/webhook",
            content=b'{"test": true}',
            headers={"Stripe-Signature": "valid-test-signature"},
        )
        unpaid_status = client.get(
            f"/api/v1/organization-signups/{unpaid_signup['organization_id']}"
        )

        abandoned_signup = signup(client)
        clock.now += timedelta(hours=24)
        expired_status = client.get(
            f"/api/v1/organization-signups/{abandoned_signup['organization_id']}"
        )
        verifier.event = paid_event(abandoned_signup, event_id="evt_too_late")
        late_webhook = client.post(
            "/api/v1/billing/stripe/webhook",
            content=b'{"test": true}',
            headers={"Stripe-Signature": "valid-test-signature"},
        )
        after_late_event = client.get(
            f"/api/v1/organization-signups/{abandoned_signup['organization_id']}"
        )

    assert unpaid_webhook.json()["outcome"] == "ignored"
    assert unpaid_status.json()["status"] == "pending_activation"
    assert unpaid_status.json()["initial_content"] is None
    assert expired_status.json()["status"] == "expired"
    assert expired_status.json()["initial_content"] is None
    assert late_webhook.json()["outcome"] == "ignored"
    assert after_late_event.json()["status"] == "expired"
    assert after_late_event.json()["initial_content"] is None


def test_signup_validates_seat_count_and_iana_time_zone(database_url: str) -> None:
    stripe = FakeStripeBilling()
    application = create_app(
        database_url=database_url,
        oidc_client=FakeOIDCClient(),
        stripe_billing=stripe,
        stripe_webhook_verifier=FakeStripeWebhookVerifier(),
        clock=lambda: NOW,
    )
    with TestClient(application) as client:
        log_in(client)
        invalid = client.post(
            "/api/v1/organization-signups",
            json={
                "organization_name": "Northwind",
                "time_zone": "Helsinki-ish",
                "default_locale": "en",
                "billing_name": "Northwind",
                "billing_email": "billing@example.com",
                "initial_seats": 0,
            },
        )

    assert invalid.status_code == 422
    assert stripe.checkout_requests == []


def test_stripe_signature_verification_rejects_tampering() -> None:
    timestamp = 1_800_000_000
    payload = json.dumps(
        {
            "id": "evt_signature",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_signature",
                    "client_reference_id": "3ea19a50-62af-446f-a608-c2c3c99cbb92",
                    "metadata": {},
                    "customer": "cus_signature",
                    "subscription": "sub_signature",
                    "payment_status": "paid",
                }
            },
        },
        separators=(",", ":"),
    ).encode()
    digest = hmac.new(
        b"whsec_test",
        f"{timestamp}.".encode() + payload,
        hashlib.sha256,
    ).hexdigest()
    verifier = StripeSignatureVerifier(
        "whsec_test",
        timestamp=lambda: timestamp,
    )

    event = verifier.verify(payload, f"t={timestamp},v1={digest}")

    assert event.id == "evt_signature"
    assert event.organization_id == "3ea19a50-62af-446f-a608-c2c3c99cbb92"
    try:
        verifier.verify(payload + b" ", f"t={timestamp},v1={digest}")
    except Exception as error:
        assert getattr(error, "status_code", None) == 400
    else:
        raise AssertionError("tampered payload must be rejected")
