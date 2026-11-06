from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import OIDCIdentity
from app.billing import (
    CheckoutRequest,
    CheckoutSession,
    SeatChangeRequest,
    SeatChangeResult,
    SeatIncreasePreview,
    SeatIncreasePreviewRequest,
    StripeEvent,
)
from app.main import create_app

NOW = datetime(2026, 7, 29, 9, 0, tzinfo=UTC)
RENEWAL = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


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
            subject="seat-owner",
            email="seat-owner@example.com",
            email_verified=True,
            display_name="Seat Owner",
            expires_at=2_000_000_000,
        )

    def end_session_url(self, *, post_logout_redirect_uri: str, id_token_hint: str | None = None) -> str:
        return post_logout_redirect_uri


class FakeStripeBilling:
    def __init__(self) -> None:
        self.preview_requests: list[SeatIncreasePreviewRequest] = []
        self.change_requests: list[SeatChangeRequest] = []

    def create_subscription_checkout(
        self,
        request: CheckoutRequest,
    ) -> CheckoutSession:
        return CheckoutSession(
            id=f"cs_test_{request.organization_id}",
            url=f"https://checkout.stripe.test/{request.organization_id}",
        )

    def preview_seat_increase(
        self,
        request: SeatIncreasePreviewRequest,
    ) -> SeatIncreasePreview:
        self.preview_requests.append(request)
        return SeatIncreasePreview(
            id="preview_3_to_5",
            amount_due=1200,
            currency="eur",
            proration_date=NOW,
        )

    def request_seat_increase(
        self,
        request: SeatChangeRequest,
    ) -> SeatChangeResult:
        self.change_requests.append(request)
        return SeatChangeResult(
            reference=f"sub_update_{request.change_id}",
            effective_at=None,
        )

    def schedule_seat_decrease(
        self,
        request: SeatChangeRequest,
    ) -> SeatChangeResult:
        self.change_requests.append(request)
        return SeatChangeResult(
            reference=f"sub_schedule_{request.change_id}",
            effective_at=RENEWAL,
        )


class FakeStripeWebhookVerifier:
    event: StripeEvent | None = None

    def verify(self, payload: bytes, signature: str | None) -> StripeEvent:
        assert payload
        assert signature == "valid-test-signature"
        assert self.event is not None
        return self.event


def log_in(client: TestClient) -> None:
    login = client.get("/api/v1/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]
    callback = client.get(
        "/api/v1/auth/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 303


def activate_organization(
    client: TestClient,
    verifier: FakeStripeWebhookVerifier,
) -> str:
    signup = client.post(
        "/api/v1/organization-signups",
        json={
            "organization_name": "Northwind",
            "time_zone": "Europe/Helsinki",
            "default_locale": "en",
            "billing_name": "Northwind",
            "billing_email": "billing@example.com",
            "initial_seats": 3,
        },
    ).json()
    organization_id = signup["organization_id"]
    verifier.event = StripeEvent(
        id=f"evt_activate_{organization_id}",
        type="checkout.session.completed",
        checkout_session_id=f"cs_test_{organization_id}",
        organization_id=organization_id,
        customer_id=f"cus_{organization_id}",
        subscription_id=f"sub_{organization_id}",
        payment_status="paid",
    )
    response = client.post(
        "/api/v1/billing/stripe/webhook",
        content=b'{"event": true}',
        headers={"Stripe-Signature": "valid-test-signature"},
    )
    assert response.json()["outcome"] == "activated"
    return organization_id


def post_event(
    client: TestClient,
    verifier: FakeStripeWebhookVerifier,
    event: StripeEvent,
) -> dict:
    verifier.event = event
    return client.post(
        "/api/v1/billing/stripe/webhook",
        content=b'{"event": true}',
        headers={"Stripe-Signature": "valid-test-signature"},
    ).json()


def test_owner_previews_and_confirms_payment_gated_seat_increase(
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
        organization_id = activate_organization(client, verifier)
        seat_url = f"/api/v1/organizations/{organization_id}/billing/seats"

        initial = client.get(seat_url)
        preview = client.post(
            f"{seat_url}/increase-preview",
            json={"target_seats": 5, "expected_version": 1},
        )
        preview_data = preview.json()
        missing_confirmation = client.post(
            seat_url,
            json={
                "target_seats": 5,
                "expected_version": 1,
                "preview_id": preview_data["preview_id"],
                "confirmed": False,
            },
        )
        mismatched_preview = client.post(
            seat_url,
            json={
                "target_seats": 6,
                "expected_version": 1,
                "preview_id": preview_data["preview_id"],
                "confirmed": True,
            },
        )
        requested = client.post(
            seat_url,
            json={
                "target_seats": 5,
                "expected_version": 1,
                "preview_id": preview_data["preview_id"],
                "confirmed": True,
            },
        )
        before_payment = client.get(seat_url)
        change_id = requested.json()["pending_change"]["id"]
        wrong_subscription = post_event(
            client,
            verifier,
            StripeEvent(
                id="evt_wrong_subscription",
                type="customer.subscription.pending_update_applied",
                checkout_session_id=None,
                organization_id=organization_id,
                customer_id=None,
                subscription_id="sub_another_organization",
                payment_status="paid",
                seat_change_id=change_id,
                quantity=5,
                created_at=NOW,
            ),
        )
        failed_attempt = post_event(
            client,
            verifier,
            StripeEvent(
                id="evt_payment_attempt_failed",
                type="invoice.payment_failed",
                checkout_session_id=None,
                organization_id=organization_id,
                customer_id=None,
                subscription_id=f"sub_{organization_id}",
                payment_status="unpaid",
                seat_change_id=change_id,
                quantity=None,
                created_at=NOW,
            ),
        )
        after_failed_attempt = client.get(seat_url)
        paid_event = StripeEvent(
            id="evt_seat_increase_paid",
            type="customer.subscription.pending_update_applied",
            checkout_session_id=None,
            organization_id=organization_id,
            customer_id=None,
            subscription_id=f"sub_{organization_id}",
            payment_status="paid",
            seat_change_id=change_id,
            quantity=5,
            created_at=NOW,
        )
        applied = post_event(client, verifier, paid_event)
        duplicate = post_event(client, verifier, paid_event)
        delayed_failure = post_event(
            client,
            verifier,
            StripeEvent(
                id="evt_delayed_failure",
                type="invoice.payment_failed",
                checkout_session_id=None,
                organization_id=organization_id,
                customer_id=None,
                subscription_id=f"sub_{organization_id}",
                payment_status="unpaid",
                seat_change_id=change_id,
                quantity=None,
                created_at=NOW,
            ),
        )
        after_payment = client.get(seat_url)

    assert initial.json() == {
        "purchased": 3,
        "occupied": 1,
        "reserved": 0,
        "available": 2,
        "version": 1,
        "pending_change": None,
    }
    assert preview_data["target_seats"] == 5
    assert preview_data["amount_due"] == 1200
    assert preview_data["currency"] == "eur"
    assert preview_data["proration_date"] == "2026-07-29T09:00:00Z"
    assert missing_confirmation.status_code == 422
    assert mismatched_preview.status_code == 409
    assert requested.status_code == 202
    assert requested.json()["purchased"] == 3
    assert requested.json()["version"] == 2
    assert requested.json()["pending_change"]["status"] == "pending_payment"
    assert before_payment.json()["purchased"] == 3
    assert wrong_subscription["outcome"] == "ignored"
    assert failed_attempt["outcome"] == "ignored"
    assert after_failed_attempt.json()["purchased"] == 3
    assert after_failed_attempt.json()["pending_change"]["status"] == (
        "pending_payment"
    )
    assert applied["outcome"] == "seat_change_applied"
    assert duplicate["duplicate"] is True
    assert delayed_failure["outcome"] == "ignored"
    assert after_payment.json()["purchased"] == 5
    assert after_payment.json()["available"] == 4
    assert after_payment.json()["version"] == 3
    assert after_payment.json()["pending_change"] is None


def test_decrease_is_scheduled_at_renewal_and_respects_used_capacity(
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
        organization_id = activate_organization(client, verifier)
        seat_url = f"/api/v1/organizations/{organization_id}/billing/seats"

        extra_user_id = uuid4()
        membership_id = uuid4()
        with application.state.database_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO user_accounts (
                        id, oidc_issuer, oidc_subject, account_class,
                        email, display_name, locale
                    ) VALUES (
                        :id, 'https://identity.example/', :subject, 'customer',
                        :email, 'Extra User', 'en'
                    )
                    """
                ),
                {
                    "id": extra_user_id,
                    "subject": f"extra-{extra_user_id}",
                    "email": f"{extra_user_id}@example.com",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO organization_memberships (
                        id, organization_id, user_account_id, role
                    ) VALUES (:id, :organization_id, :user_id, 'admin')
                    """
                ),
                {
                    "id": membership_id,
                    "organization_id": organization_id,
                    "user_id": extra_user_id,
                },
            )
            connection.execute(
                text(
                    """
                    UPDATE organizations
                    SET reserved_seats = 1
                    WHERE id = :organization_id
                    """
                ),
                {"organization_id": organization_id},
            )
        used_capacity = client.get(seat_url)
        below_occupied = client.post(
            seat_url,
            json={"target_seats": 2, "expected_version": 1, "confirmed": True},
        )
        with application.state.database_engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM organization_memberships
                    WHERE id = :membership_id
                    """
                ),
                {"membership_id": membership_id},
            )
            connection.execute(
                text(
                    """
                    UPDATE organizations
                    SET reserved_seats = 0
                    WHERE id = :organization_id
                    """
                ),
                {"organization_id": organization_id},
            )
        released_capacity = client.get(seat_url)
        scheduled = client.post(
            seat_url,
            json={"target_seats": 1, "expected_version": 1, "confirmed": True},
        )
        change_id = scheduled.json()["pending_change"]["id"]
        before_renewal = client.get(seat_url)
        applied = post_event(
            client,
            verifier,
            StripeEvent(
                id="evt_renewed_at_lower_quantity",
                type="customer.subscription.updated",
                checkout_session_id=None,
                organization_id=organization_id,
                customer_id=None,
                subscription_id=f"sub_{organization_id}",
                payment_status="paid",
                seat_change_id=change_id,
                quantity=1,
                created_at=RENEWAL,
            ),
        )
        after_renewal = client.get(seat_url)

    assert used_capacity.json()["occupied"] == 2
    assert used_capacity.json()["reserved"] == 1
    assert used_capacity.json()["available"] == 0
    assert below_occupied.status_code == 409
    assert below_occupied.json()["detail"] == (
        "seat capacity cannot be lower than occupied plus reserved seats"
    )
    assert released_capacity.json()["occupied"] == 1
    assert released_capacity.json()["available"] == 2
    assert scheduled.status_code == 202
    assert scheduled.json()["purchased"] == 3
    assert scheduled.json()["pending_change"]["status"] == "scheduled"
    assert scheduled.json()["pending_change"]["effective_at"] == (
        "2026-08-29T09:00:00Z"
    )
    assert before_renewal.json()["available"] == 0
    assert applied["outcome"] == "seat_change_applied"
    assert after_renewal.json()["purchased"] == 1
    assert after_renewal.json()["available"] == 0
    assert len(stripe.change_requests) == 1
