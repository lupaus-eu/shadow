from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx

from app.billing import (
    CheckoutRequest,
    SeatChangeRequest,
    SeatIncreasePreviewRequest,
    StripeBillingClient,
    StripeSettings,
)


def test_subscription_checkout_uses_the_configured_monthly_seat_price() -> None:
    captured: dict[str, object] = {}

    def stripe_api(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["form"] = parse_qs(request.content.decode())
        return httpx.Response(
            200,
            json={
                "id": "cs_test_contract",
                "url": "https://checkout.stripe.test/cs_test_contract",
            },
        )

    http_client = httpx.Client(
        base_url="https://api.stripe.com",
        transport=httpx.MockTransport(stripe_api),
    )
    billing = StripeBillingClient(
        StripeSettings(
            secret_key="sk_test_contract",
            webhook_secret="whsec_contract",
            monthly_seat_price_id="price_eur_30_monthly",
            frontend_url="https://yearclock.example",
        ),
        client=http_client,
    )

    checkout = billing.create_subscription_checkout(
        CheckoutRequest(
            organization_id="3ea19a50-62af-446f-a608-c2c3c99cbb92",
            organization_name="Northwind Oy",
            billing_email="billing@northwind.example",
            seats=3,
            locale="fi",
            expires_at=datetime(2026, 7, 30, 9, 0, tzinfo=UTC),
        )
    )

    form = captured["form"]
    headers = captured["headers"]
    assert isinstance(form, dict)
    assert isinstance(headers, httpx.Headers)
    assert checkout.id == "cs_test_contract"
    assert form["mode"] == ["subscription"]
    assert form["line_items[0][price]"] == ["price_eur_30_monthly"]
    assert form["line_items[0][quantity]"] == ["3"]
    assert form["billing_address_collection"] == ["required"]
    assert form["automatic_tax[enabled]"] == ["true"]
    assert form["tax_id_collection[enabled]"] == ["true"]
    assert form["metadata[organization_id]"] == [
        "3ea19a50-62af-446f-a608-c2c3c99cbb92"
    ]
    assert headers["Idempotency-Key"] == (
        "organization-signup:3ea19a50-62af-446f-a608-c2c3c99cbb92"
    )


def test_seat_increase_uses_matching_preview_and_payment_gated_update() -> None:
    requests: list[tuple[str, str, dict[str, list[str]]]] = []

    def stripe_api(request: httpx.Request) -> httpx.Response:
        form = parse_qs(request.content.decode())
        requests.append((request.method, request.url.path, form))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "id": "sub_contract",
                    "items": {
                        "data": [
                            {
                                "id": "si_seats",
                                "quantity": 3,
                                "current_period_start": 1785315600,
                                "current_period_end": 1787994000,
                                "price": {"id": "price_eur_30_monthly"},
                            }
                        ]
                    },
                },
            )
        if request.url.path == "/v1/invoices/create_preview":
            return httpx.Response(
                200,
                json={
                    "id": "upcoming_in_preview",
                    "amount_due": 1200,
                    "currency": "eur",
                },
            )
        return httpx.Response(200, json={"id": "sub_contract"})

    billing = StripeBillingClient(
        StripeSettings(
            secret_key="sk_test_contract",
            webhook_secret="whsec_contract",
            monthly_seat_price_id="price_eur_30_monthly",
            frontend_url="https://yearclock.example",
        ),
        client=httpx.Client(
            base_url="https://api.stripe.com",
            transport=httpx.MockTransport(stripe_api),
        ),
    )
    proration_date = datetime(2026, 7, 29, 9, 0, tzinfo=UTC)

    preview = billing.preview_seat_increase(
        SeatIncreasePreviewRequest(
            organization_id="3ea19a50-62af-446f-a608-c2c3c99cbb92",
            subscription_id="sub_contract",
            current_seats=3,
            target_seats=5,
            proration_date=proration_date,
        )
    )
    result = billing.request_seat_increase(
        SeatChangeRequest(
            change_id="a3a70b4d-512a-43d7-a81d-534743a83d69",
            organization_id="3ea19a50-62af-446f-a608-c2c3c99cbb92",
            subscription_id="sub_contract",
            current_seats=3,
            target_seats=5,
            proration_date=proration_date,
        )
    )

    assert preview.id == "upcoming_in_preview"
    assert preview.amount_due == 1200
    assert result.reference == "sub_contract"
    preview_form = requests[1][2]
    update_form = requests[3][2]
    assert preview_form["subscription_details[items][0][quantity]"] == ["5"]
    assert preview_form["subscription_details[proration_date]"] == [
        str(int(proration_date.timestamp()))
    ]
    assert update_form["payment_behavior"] == ["pending_if_incomplete"]
    assert update_form["proration_behavior"] == ["always_invoice"]
    assert update_form["items[0][quantity]"] == ["5"]
    assert update_form["metadata[seat_change_id]"] == [
        "a3a70b4d-512a-43d7-a81d-534743a83d69"
    ]


def test_seat_decrease_uses_a_non_prorated_renewal_schedule() -> None:
    requests: list[tuple[str, dict[str, list[str]]]] = []

    def stripe_api(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, parse_qs(request.content.decode())))
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "current_period_start": 1785315600,
                    "current_period_end": 1787994000,
                    "items": {
                        "data": [
                            {
                                "id": "si_seats",
                                "quantity": 3,
                                "price": {"id": "price_eur_30_monthly"},
                            }
                        ]
                    }
                },
            )
        if request.url.path == "/v1/subscription_schedules":
            return httpx.Response(200, json={"id": "sub_sched_contract"})
        return httpx.Response(200, json={"id": "sub_sched_contract"})

    billing = StripeBillingClient(
        StripeSettings(
            secret_key="sk_test_contract",
            webhook_secret="whsec_contract",
            monthly_seat_price_id="price_eur_30_monthly",
            frontend_url="https://yearclock.example",
        ),
        client=httpx.Client(
            base_url="https://api.stripe.com",
            transport=httpx.MockTransport(stripe_api),
        ),
    )
    result = billing.schedule_seat_decrease(
        SeatChangeRequest(
            change_id="a3a70b4d-512a-43d7-a81d-534743a83d69",
            organization_id="3ea19a50-62af-446f-a608-c2c3c99cbb92",
            subscription_id="sub_contract",
            current_seats=3,
            target_seats=1,
        )
    )

    schedule_form = requests[2][1]
    assert result.reference == "sub_sched_contract"
    assert result.effective_at == datetime.fromtimestamp(1787994000, tz=UTC)
    assert schedule_form["proration_behavior"] == ["none"]
    assert schedule_form["phases[0][items][0][quantity]"] == ["3"]
    assert schedule_form["phases[1][items][0][quantity]"] == ["1"]
    assert schedule_form["phases[1][start_date]"] == ["1787994000"]
    assert schedule_form["phases[1][metadata][seat_change_id]"] == [
        "a3a70b4d-512a-43d7-a81d-534743a83d69"
    ]
