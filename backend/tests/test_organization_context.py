from urllib.parse import parse_qs, urlparse
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth import OIDCIdentity
from app.billing import CheckoutRequest, CheckoutSession, StripeEvent
from app.database import RequestContext, transaction_session
from app.main import create_app
from app.models import (
    Lane,
    Organization,
    OrganizationMembership,
    Yearclock,
)


class FakeOIDCClient:
    def __init__(self, subject: str = "context-owner") -> None:
        self.subject = subject

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
            issuer="https://identity.example/application/o/yearclock/",
            subject=self.subject,
            email=f"{self.subject}@example.com",
            email_verified=True,
            display_name=self.subject.replace("-", " ").title(),
            expires_at=2_000_000_000,
        )

    def end_session_url(self, *, post_logout_redirect_uri: str, id_token_hint: str | None = None) -> str:
        return post_logout_redirect_uri


class FakeStripeBilling:
    def create_subscription_checkout(
        self,
        request: CheckoutRequest,
    ) -> CheckoutSession:
        return CheckoutSession(
            id=f"cs_test_{request.organization_id}",
            url=f"https://checkout.stripe.test/{request.organization_id}",
        )


class FakeStripeWebhookVerifier:
    event: StripeEvent | None = None

    def verify(self, payload: bytes, signature: str | None) -> StripeEvent:
        assert payload
        assert signature == "valid-test-signature"
        assert self.event is not None
        return self.event


def log_in(client: TestClient) -> None:
    login_response = client.get("/api/v1/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(login_response.headers["location"]).query)["state"][0]
    callback = client.get(
        "/api/v1/auth/callback",
        params={"code": "code", "state": state},
        follow_redirects=False,
    )
    assert callback.status_code == 303


def activate_organization(
    client: TestClient,
    verifier: FakeStripeWebhookVerifier,
    *,
    name: str,
) -> dict:
    signup = client.post(
        "/api/v1/organization-signups",
        json={
            "organization_name": name,
            "time_zone": "Europe/Helsinki",
            "default_locale": "en",
            "billing_name": name,
            "billing_email": "billing@example.com",
            "initial_seats": 1,
        },
    ).json()
    organization_id = signup["organization_id"]
    verifier.event = StripeEvent(
        id=f"evt_{organization_id}",
        type="checkout.session.completed",
        checkout_session_id=f"cs_test_{organization_id}",
        organization_id=organization_id,
        customer_id=f"cus_{organization_id}",
        subscription_id=f"sub_{organization_id}",
        payment_status="paid",
    )
    webhook = client.post(
        "/api/v1/billing/stripe/webhook",
        content=b'{"test": true}',
        headers={"Stripe-Signature": "valid-test-signature"},
    )
    assert webhook.json()["outcome"] == "activated"
    return client.get(
        f"/api/v1/organization-signups/{organization_id}"
    ).json()


def test_customer_lists_and_opens_only_their_organizations(
    database_url: str,
) -> None:
    verifier = FakeStripeWebhookVerifier()
    application = create_app(
        database_url=database_url,
        oidc_client=FakeOIDCClient(),
        stripe_billing=FakeStripeBilling(),
        stripe_webhook_verifier=verifier,
    )

    with TestClient(application) as owner:
        log_in(owner)
        northwind = activate_organization(owner, verifier, name="Northwind")
        contoso = activate_organization(owner, verifier, name="Contoso")

        organizations_response = owner.get("/api/v1/organizations")
        northwind_workspace = owner.get(
            f"/api/v1/organizations/{northwind['organization_id']}"
        )
        matching_yearclock = owner.get(
            "/api/v1/organizations/"
            f"{northwind['organization_id']}/yearclocks/"
            f"{northwind['initial_content']['yearclock_id']}"
        )
        mismatched_yearclock = owner.get(
            "/api/v1/organizations/"
            f"{northwind['organization_id']}/yearclocks/"
            f"{contoso['initial_content']['yearclock_id']}"
        )

    assert organizations_response.status_code == 200
    assert organizations_response.json() == {
        "organizations": [
            {
                "id": contoso["organization_id"],
                "name": "Contoso",
                "role": "owner",
                "status": "active",
                "purge_after": None,
            },
            {
                "id": northwind["organization_id"],
                "name": "Northwind",
                "role": "owner",
                "status": "active",
                "purge_after": None,
            },
        ]
    }
    assert northwind_workspace.status_code == 200
    assert northwind_workspace.json()["organization"]["name"] == "Northwind"
    assert northwind_workspace.json()["membership"]["role"] == "owner"
    # Compare the V1 fields; later versions add layout fields to the same summary.
    v1_summary = [
        {**{key: item[key] for key in ("id", "name", "version", "access_role")}, "lanes": [{key: lane[key] for key in ("id", "name", "display_order", "version")} for lane in item["lanes"]]}
        for item in northwind_workspace.json()["yearclocks"]
    ]
    assert v1_summary == [
        {
            "id": northwind["initial_content"]["yearclock_id"],
            "name": "Yearclock",
            "version": 1,
            "access_role": "editor",
            "lanes": [
                {
                    "id": northwind["initial_content"]["lane_id"],
                    "name": "General",
                    "display_order": 0,
                    "version": 1,
                }
            ],
        }
    ]
    assert matching_yearclock.status_code == 200
    assert matching_yearclock.json()["name"] == "Yearclock"
    assert mismatched_yearclock.status_code == 404


def test_guessed_routes_and_unscoped_queries_cannot_cross_organizations(
    database_url: str,
) -> None:
    verifier = FakeStripeWebhookVerifier()
    application = create_app(
        database_url=database_url,
        oidc_client=FakeOIDCClient(),
        stripe_billing=FakeStripeBilling(),
        stripe_webhook_verifier=verifier,
    )
    with TestClient(application) as owner:
        log_in(owner)
        northwind = activate_organization(owner, verifier, name="RLS Northwind")
        contoso = activate_organization(owner, verifier, name="RLS Contoso")
        pending = owner.post(
            "/api/v1/organization-signups",
            json={
                "organization_name": "RLS Pending",
                "time_zone": "Europe/Helsinki",
                "default_locale": "en",
                "billing_name": "RLS Pending",
                "billing_email": "billing@example.com",
                "initial_seats": 1,
            },
        ).json()
        owner_id = owner.get("/api/v1/auth/session").json()["user_account"]["id"]

    outsider_application = create_app(
        database_url=database_url,
        oidc_client=FakeOIDCClient(subject="context-outsider"),
        stripe_billing=FakeStripeBilling(),
        stripe_webhook_verifier=FakeStripeWebhookVerifier(),
    )
    with TestClient(outsider_application) as outsider:
        log_in(outsider)
        guessed = outsider.get(
            f"/api/v1/organizations/{northwind['organization_id']}"
        )

    with transaction_session(
        application.state.session_factory,
        RequestContext(
            user_account_id=UUID(owner_id),
            organization_id=UUID(northwind["organization_id"]),
        ),
    ) as session:
        unscoped_yearclocks = session.scalars(
            select(Yearclock).order_by(Yearclock.id)
        ).all()
        unscoped_organizations = session.scalars(
            select(Organization).order_by(Organization.id)
        ).all()
        unscoped_memberships = session.scalars(
            select(OrganizationMembership).order_by(
                OrganizationMembership.id
            )
        ).all()
        hidden_lane = session.get(
            Lane,
            UUID(contoso["initial_content"]["lane_id"]),
        )
        cross_tenant_update = session.execute(
            update(Yearclock)
            .where(
                Yearclock.id
                == UUID(contoso["initial_content"]["yearclock_id"])
            )
            .values(name="Cross-tenant breach")
        )
        pending_cross_tenant_update = session.execute(
            update(Organization)
            .where(Organization.id == UUID(pending["organization_id"]))
            .values(name="Pending cross-tenant breach")
        )

    assert guessed.status_code == 404
    assert [str(yearclock.id) for yearclock in unscoped_yearclocks] == [
        northwind["initial_content"]["yearclock_id"]
    ]
    assert [str(organization.id) for organization in unscoped_organizations] == [
        northwind["organization_id"]
    ]
    assert [
        str(membership.organization_id)
        for membership in unscoped_memberships
    ] == [northwind["organization_id"]]
    assert hidden_lane is None
    assert cross_tenant_update.rowcount == 0
    assert pending_cross_tenant_update.rowcount == 0
