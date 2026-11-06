"""The next charge and the payments an Owner sees (Yearclock V2 billing overview)."""
from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
from fastapi import HTTPException

from app.billing import InvoiceSummary, StripeBillingClient, StripeSettings, UpcomingCharge
from test_notifications import World, stack  # noqa: F401 - the fixture
from test_invitations import Stripe
from test_subscription_management import ManageStripe

CHARGE_DATE = datetime(2026, 12, 4, tzinfo=UTC)


class OverviewStripe(ManageStripe):
    def __init__(self) -> None:
        super().__init__()
        self.fail_overview = False
        self.invoices: list[InvoiceSummary] = []
        self.preview_calls: list[str] = []
        self.list_calls: list[dict] = []

    def upcoming_charge(self, *, subscription_id):
        self.preview_calls.append(subscription_id)
        if self.fail_overview:
            raise HTTPException(status_code=502, detail="unable to preview the next charge")
        return UpcomingCharge(charge_date=CHARGE_DATE, amount=18000, currency="eur", seats=6)

    def list_invoices(self, *, customer_id, limit=12):
        self.list_calls.append({"customer_id": customer_id, "limit": limit})
        if self.fail_overview:
            raise HTTPException(status_code=502, detail="unable to list invoices")
        return self.invoices


def invoice(number: int, **extra) -> InvoiceSummary:
    values = {"id": f"in_{number}", "created": datetime(2026, 11, 1, tzinfo=UTC), "amount": 18000, "currency": "eur", "state": "paid", "reason": "renewal", "hosted_invoice_url": f"https://invoice.stripe.test/{number}"}
    return InvoiceSummary(**{**values, **extra})


def test_an_owner_sees_the_next_charge_from_stripe(database_url, stack) -> None:
    stripe = OverviewStripe()
    world = World(stack, database_url, "ovw-next", stripe=stripe)
    response = world.owner.get(f"{world.org}/billing/next-charge")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "scheduled", "charge_date": "2026-12-04T00:00:00Z", "amount": 18000, "currency": "eur", "seats": 6}
    assert stripe.preview_calls == [f"sub_{world.organization_id}"]


def test_no_charge_is_previewed_when_the_cancellation_is_scheduled_and_stripe_is_not_asked(database_url, stack) -> None:
    stripe = OverviewStripe()
    world = World(stack, database_url, "ovw-cancel", stripe=stripe)
    assert world.owner.post(f"{world.org}/billing/cancel").status_code == 200
    assert world.owner.get(f"{world.org}/billing/next-charge").json() == {"status": "none_cancelled", "charge_date": None, "amount": None, "currency": None, "seats": None}
    assert stripe.preview_calls == []


def test_a_stripe_failure_degrades_both_views_without_an_error(database_url, stack) -> None:
    stripe = OverviewStripe()
    stripe.fail_overview = True
    world = World(stack, database_url, "ovw-down", stripe=stripe)
    assert world.owner.get(f"{world.org}/billing/next-charge").json()["status"] == "unavailable"
    response = world.owner.get(f"{world.org}/billing/invoices")
    assert response.status_code == 200 and response.json() == {"status": "unavailable", "invoices": []}


def test_the_invoice_list_is_capped_and_asks_stripe_for_the_organizations_customer(database_url, stack) -> None:
    stripe = OverviewStripe()
    stripe.invoices = [invoice(number) for number in range(15)]
    world = World(stack, database_url, "ovw-list", stripe=stripe)
    body = world.owner.get(f"{world.org}/billing/invoices").json()
    assert body["status"] == "ok" and len(body["invoices"]) == 12
    assert body["invoices"][0] == {"id": "in_0", "date": "2026-11-01T00:00:00Z", "amount": 18000, "currency": "eur", "state": "paid", "reason": "renewal", "hosted_invoice_url": "https://invoice.stripe.test/0"}
    assert stripe.list_calls == [{"customer_id": f"cus_{world.organization_id}", "limit": 12}]


def test_only_owners_can_read_the_overview(database_url, stack) -> None:
    stripe = OverviewStripe()
    world = World(stack, database_url, "ovw-roles", stripe=stripe)
    admin, _, _ = world.person("admin", role="admin")
    member, _, _ = world.person("member")
    for client in (admin, member):
        assert client.get(f"{world.org}/billing/next-charge").status_code == 403
        assert client.get(f"{world.org}/billing/invoices").status_code == 403
    other = World(stack, database_url, "ovw-other", stripe=OverviewStripe())
    assert other.owner.get(f"{world.org}/billing/next-charge").status_code == 404
    assert other.owner.get(f"{world.org}/billing/invoices").status_code == 404
    assert stripe.preview_calls == [] and stripe.list_calls == []


def _client(handler) -> StripeBillingClient:
    return StripeBillingClient(
        StripeSettings(secret_key="sk_test", webhook_secret="whsec", monthly_seat_price_id="price_1", frontend_url="https://yearclock.example"),
        client=httpx.Client(base_url="https://api.stripe.com", transport=httpx.MockTransport(handler)),
    )


def test_the_client_previews_the_next_invoice_of_the_subscription_only() -> None:
    seen: dict = {}

    def api(request: httpx.Request) -> httpx.Response:
        seen["path"], seen["form"] = request.url.path, parse_qs(request.content.decode())
        return httpx.Response(200, json={"total": 18000, "currency": "eur", "next_payment_attempt": 1796342400, "lines": {"data": [{"quantity": 6, "period": {"start": 1796342400}}]}})

    charge = _client(api).upcoming_charge(subscription_id="sub_1")
    assert seen == {"path": "/v1/invoices/create_preview", "form": {"subscription": ["sub_1"]}}
    assert (charge.amount, charge.currency, charge.seats, charge.charge_date) == (18000, "eur", 6, datetime(2026, 12, 4, tzinfo=UTC))


def test_the_client_maps_invoices_and_drops_drafts_and_foreign_links() -> None:
    seen: dict = {}

    def api(request: httpx.Request) -> httpx.Response:
        seen["path"], seen["query"] = request.url.path, dict(request.url.params)
        base = {"currency": "eur", "total": 3000, "created": 1793664000, "hosted_invoice_url": "https://invoice.stripe.com/i/1"}
        return httpx.Response(200, json={"data": [
            {**base, "id": "in_a", "status": "paid", "billing_reason": "subscription_update"},
            {**base, "id": "in_b", "status": "open", "attempt_count": 2, "billing_reason": "subscription_cycle"},
            {**base, "id": "in_c", "status": "draft", "billing_reason": "subscription_cycle"},
            {**base, "id": "in_d", "status": "paid", "billing_reason": "manual", "hosted_invoice_url": "http://insecure.test/i"},
            {**base, "id": "in_e", "status": "paid", "billing_reason": "subscription_create"},
        ]})

    found = _client(api).list_invoices(customer_id="cus_1")
    assert seen == {"path": "/v1/invoices", "query": {"customer": "cus_1", "limit": "12"}}
    assert [(item.id, item.state, item.reason, item.hosted_invoice_url is not None) for item in found] == [
        ("in_a", "paid", "seat_increase", True),
        ("in_b", "failed", "renewal", True),
        ("in_d", "paid", "other", False),
        ("in_e", "paid", "signup", True),
    ]
