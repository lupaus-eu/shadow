"""Cancel, undo, subscribe again, and the billing contact (Shadow V2, P14)."""
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import text

from app.billing import CancelResult, CheckoutSession, ResubscribeRequest, SeatChangeRequest, SeatChangeResult, StripeEvent
from test_invitations import NOW
from test_notifications import World, stack  # noqa: F401 - the fixture
from test_invitations import Stripe
from test_subscription_lifecycle import _event, _post

PERIOD_END = datetime(2026, 11, 4, tzinfo=UTC)


class ManageStripe(Stripe):
    """Records the calls P14 makes and can be told to fail."""

    def __init__(self) -> None:
        self.cancel_calls: list[dict] = []
        self.fail_cancel = False
        self.schedules = 0
        self.checkouts: list[ResubscribeRequest] = []
        self.customer_updates: list[dict] = []
        self.fail_customer = False

    def set_cancel_at_period_end(self, *, subscription_id, cancel, schedule_id=None):
        self.cancel_calls.append({"subscription_id": subscription_id, "cancel": cancel, "schedule_id": schedule_id})
        if self.fail_cancel:
            raise HTTPException(status_code=502, detail="unable to change the subscription")
        return CancelResult(cancel_at_period_end=cancel, current_period_end=PERIOD_END)

    def update_customer(self, *, customer_id, name, email):
        if self.fail_customer:
            raise HTTPException(status_code=502, detail="unable to update the billing contact")
        self.customer_updates.append({"customer_id": customer_id, "name": name, "email": email})

    def create_resubscribe_checkout(self, request: ResubscribeRequest) -> CheckoutSession:
        self.checkouts.append(request)
        return CheckoutSession(id=f"cs_resub_{len(self.checkouts)}", url=f"https://checkout.test/resub/{len(self.checkouts)}")

    def schedule_seat_decrease(self, request: SeatChangeRequest) -> SeatChangeResult:
        self.schedules += 1
        return SeatChangeResult(reference=f"sched_{self.schedules}", effective_at=PERIOD_END)


def subscription(world):
    return world.owner.get(world.org).json()["subscription"]


def audit(world, prefix="organization"):
    return world.owner.get(f"{world.org}/audit-events", params={"prefix": prefix}).json()["items"]


def test_an_owner_cancels_at_the_end_of_the_period_and_the_others_are_told(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "sub-cancel", stripe=stripe)
    admin, _, _ = world.person("admin", role="admin")
    member, _, _ = world.person("member")
    response = world.owner.post(f"{world.org}/billing/cancel", json={"reason": "switching"})
    assert response.status_code == 200, response.text
    assert response.json()["cancel_at_period_end"] is True and response.json()["current_period_end"].startswith("2026-11-04")
    assert stripe.cancel_calls == [{"subscription_id": f"sub_{world.organization_id}", "cancel": True, "schedule_id": None}]
    assert subscription(world)["cancel_at_period_end"] is True and subscription(world)["current_period_end"].startswith("2026-11-04")
    entry = next(item for item in audit(world) if item["action"] == "organization.subscription_cancel_scheduled")
    assert entry["change_summary"] == {"reason": "switching", "current_period_end": PERIOD_END.isoformat(), "released_seat_decrease": False}
    assert [item["params"]["current_period_end"][:10] for item in world.notices(admin, "subscription_cancel_scheduled")] == ["2026-11-04"]
    assert world.notices(world.owner, "subscription_cancel_scheduled") == [] and world.notices(member, "subscription_cancel_scheduled") == []
    assert world.owner.post(f"{world.org}/billing/cancel").status_code == 409


def test_a_stripe_failure_changes_nothing(database_url, stack) -> None:
    stripe = ManageStripe()
    stripe.fail_cancel = True
    world = World(stack, database_url, "sub-fail", stripe=stripe)
    admin, _, _ = world.person("admin", role="admin")
    response = world.owner.post(f"{world.org}/billing/cancel", json={"reason": "other"})
    assert response.status_code == 502
    assert subscription(world)["cancel_at_period_end"] is False
    assert not any(item["action"].startswith("organization.subscription_cancel") for item in audit(world))
    assert world.notices(admin, "subscription_cancel_scheduled") == []


def test_undo_restores_the_subscription_and_needs_a_scheduled_cancellation(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "sub-undo", stripe=stripe)
    admin, _, _ = world.person("admin", role="admin")
    assert world.owner.post(f"{world.org}/billing/cancel/undo").status_code == 409
    assert world.owner.post(f"{world.org}/billing/cancel").status_code == 200
    undone = world.owner.post(f"{world.org}/billing/cancel/undo")
    assert undone.status_code == 200 and undone.json()["cancel_at_period_end"] is False
    assert stripe.cancel_calls[-1]["cancel"] is False
    assert subscription(world)["cancel_at_period_end"] is False
    assert any(item["action"] == "organization.subscription_cancel_undone" for item in audit(world))
    assert len(world.notices(admin, "subscription_cancel_undone")) == 1


def test_cancelling_is_allowed_during_the_grace_period(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "sub-grace", stripe=stripe)
    _post(world.owner, world.verifier, _event(world.organization_id, "invoice.payment_failed", "evt_sub_grace", datetime.now(UTC) - timedelta(days=1), billing_reason="subscription_cycle"))
    assert subscription(world)["state"] == "grace"
    assert world.owner.post(f"{world.org}/billing/cancel").status_code == 200
    assert subscription(world)["state"] == "grace" and subscription(world)["cancel_at_period_end"] is True


def test_cancelling_releases_a_scheduled_seat_decrease(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "sub-seats", stripe=stripe)
    seats = world.owner.get(f"{world.org}/billing/seats").json()
    decrease = world.owner.post(f"{world.org}/billing/seats", json={"target_seats": seats["purchased"] - 1, "expected_version": seats["version"], "confirmed": True})
    assert decrease.status_code == 202, decrease.text
    assert world.owner.get(f"{world.org}/billing/seats").json()["pending_change"]["kind"] == "decrease"
    response = world.owner.post(f"{world.org}/billing/cancel")
    assert response.status_code == 200 and response.json()["released_seat_decrease"] is True
    assert stripe.cancel_calls[-1]["schedule_id"] == "sched_1"
    assert world.owner.get(f"{world.org}/billing/seats").json()["pending_change"] is None
    entry = next(item for item in audit(world) if item["action"] == "organization.subscription_cancel_scheduled")
    assert entry["change_summary"]["released_seat_decrease"] is True


def test_the_webhook_after_a_cancellation_leaves_the_state_alone_and_stale_events_do_not_undo_it(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "sub-webhook", stripe=stripe)
    assert world.owner.post(f"{world.org}/billing/cancel").status_code == 200
    older = _event(world.organization_id, "customer.subscription.updated", "evt_sub_old", datetime.now(UTC) - timedelta(hours=1), cancel_at_period_end=False, current_period_end=PERIOD_END)
    assert _post(world.owner, world.verifier, older)["outcome"] == "ignored_stale"
    assert subscription(world)["cancel_at_period_end"] is True
    newer = _event(world.organization_id, "customer.subscription.updated", "evt_sub_new", datetime.now(UTC) + timedelta(minutes=5), cancel_at_period_end=True, current_period_end=PERIOD_END)
    _post(world.owner, world.verifier, newer)
    assert subscription(world)["cancel_at_period_end"] is True and subscription(world)["current_period_end"].startswith("2026-11-04")


def test_only_owners_cancel_and_not_after_the_subscription_has_ended(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "sub-roles", stripe=stripe)
    admin, _, _ = world.person("admin", role="admin")
    member, _, _ = world.person("member")
    for client in (admin, member):
        assert client.post(f"{world.org}/billing/cancel").status_code == 403
        assert client.post(f"{world.org}/billing/cancel/undo").status_code == 403
    assert stripe.cancel_calls == []
    _post(world.owner, world.verifier, _event(world.organization_id, "customer.subscription.deleted", "evt_sub_ended", datetime.now(UTC)))
    assert subscription(world)["state"] == "read_only"
    assert world.owner.post(f"{world.org}/billing/cancel").status_code == 409
    assert world.owner.post(f"{world.org}/billing/cancel/undo").status_code == 409


def test_the_stripe_client_releases_a_schedule_before_it_changes_the_subscription() -> None:
    import httpx

    from app.billing import StripeBillingClient, StripeSettings

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.content.decode()))
        if request.url.path.endswith("/release"):
            return httpx.Response(200, json={"id": "sched_1"})
        return httpx.Response(200, json={"id": "sub_1", "cancel_at_period_end": True, "items": {"data": [{"current_period_end": 1_793_000_000}]}})

    client = StripeBillingClient(StripeSettings("sk_test", "whsec", "price_1", "http://localhost"), client=httpx.Client(base_url="https://stripe.test", transport=httpx.MockTransport(handler)))
    result = client.set_cancel_at_period_end(subscription_id="sub_1", cancel=True, schedule_id="sched_1")
    assert [(method, path) for method, path, _ in seen] == [("POST", "/v1/subscription_schedules/sched_1/release"), ("POST", "/v1/subscriptions/sub_1")]
    assert seen[1][2] == "cancel_at_period_end=true"
    assert result.cancel_at_period_end is True and result.current_period_end == datetime.fromtimestamp(1_793_000_000, tz=UTC)
    seen.clear()
    assert client.set_cancel_at_period_end(subscription_id="sub_1", cancel=False).cancel_at_period_end is True  # echoes what the fake Stripe says
    assert [path for _, path, _ in seen] == ["/v1/subscriptions/sub_1"] and seen[0][2] == "cancel_at_period_end=false"


def ended(world):
    _post(world.owner, world.verifier, _event(world.organization_id, "customer.subscription.deleted", f"evt_end_{world.subject}", datetime.now(UTC)))
    assert subscription(world)["ended"] is True


def completed(world, session_id, *, quantity=5, subscription=None, event_id="evt_resub", customer=None, paid=True, created=None):
    world.verifier.event = StripeEvent(event_id, "checkout.session.completed", session_id, world.organization_id, customer or f"cus_{world.organization_id}", subscription or f"sub_new_{world.subject}", "paid" if paid else "unpaid", quantity=quantity, created_at=created or datetime.now(UTC), purpose="resubscribe")
    return world.owner.post("/api/v1/billing/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "test"}).json()["outcome"]


def test_subscribing_again_is_offered_only_after_the_subscription_has_ended(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "sub-resub-offer", stripe=stripe)
    assert subscription(world)["ended"] is False
    assert world.owner.post(f"{world.org}/billing/resubscribe", json={"seats": 4}).status_code == 409
    ended(world)
    response = world.owner.post(f"{world.org}/billing/resubscribe", json={"seats": 4})
    assert response.status_code == 200 and response.json()["url"] == "https://checkout.test/resub/1"
    [checkout] = stripe.checkouts
    assert checkout.customer_id == f"cus_{world.organization_id}" and checkout.seats == 4 and checkout.organization_id == world.organization_id
    assert any(item["action"] == "organization.resubscribe_started" and item["change_summary"] == {"seats": 4} for item in audit(world))


def test_the_seat_count_must_cover_the_current_members_and_only_owners_may_ask(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "sub-resub-seats", stripe=stripe)
    admin, _, _ = world.person("admin", role="admin")
    world.person("member")
    ended(world)
    refused = world.owner.post(f"{world.org}/billing/resubscribe", json={"seats": 2})
    assert refused.status_code == 422 and refused.json()["detail"] == {"reason": "too_few_seats", "minimum": 3}
    assert world.owner.post(f"{world.org}/billing/resubscribe", json={"seats": 3}).status_code == 200
    assert admin.post(f"{world.org}/billing/resubscribe", json={"seats": 5}).status_code == 403
    assert world.owner.post(f"{world.org}/billing/resubscribe", json={"seats": 0}).status_code == 422


def test_late_events_of_the_old_subscription_and_other_sessions_change_nothing(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "sub-resub-late", stripe=stripe)
    ended(world)
    assert world.owner.post(f"{world.org}/billing/resubscribe", json={"seats": 4}).status_code == 200
    assert completed(world, "cs_somebody_else", event_id="evt_wrong_session") == "ignored"
    assert completed(world, "cs_resub_1", paid=False, event_id="evt_unpaid") == "ignored"
    assert completed(world, "cs_resub_1", customer="cus_other", event_id="evt_other_customer") == "ignored"
    assert subscription(world)["ended"] is True
    assert world.owner.post(f"{world.org}/billing/resubscribe", json={"seats": 4}).status_code == 200  # a second attempt replaces the first
    assert completed(world, "cs_resub_1", event_id="evt_first_session") == "ignored"
    assert completed(world, "cs_resub_2", event_id="evt_second_session") == "subscription_resumed"
    old_deleted = _event(world.organization_id, "customer.subscription.deleted", "evt_old_deleted_late", datetime.now(UTC) + timedelta(minutes=1))
    assert _post(world.owner, world.verifier, old_deleted)["outcome"] == "ignored"
    assert subscription(world)["state"] == "active"


def test_an_abandoned_checkout_changes_nothing(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "sub-resub-abandon", stripe=stripe)
    ended(world)
    assert world.owner.post(f"{world.org}/billing/resubscribe", json={"seats": 3}).status_code == 200
    assert subscription(world)["ended"] is True and subscription(world)["state"] == "read_only"


def test_the_stripe_client_starts_a_checkout_for_the_existing_customer_and_the_verifier_reads_its_purpose() -> None:
    import hashlib
    import hmac
    import json
    from urllib.parse import parse_qs

    import httpx

    from app.billing import StripeBillingClient, StripeSettings, StripeSignatureVerifier

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, parse_qs(request.content.decode()), request.headers.get("Idempotency-Key")))
        return httpx.Response(200, json={"id": "cs_1", "url": "https://checkout.stripe.test/cs_1"})

    client = StripeBillingClient(StripeSettings("sk_test", "whsec", "price_1", "http://localhost:8173"), client=httpx.Client(base_url="https://stripe.test", transport=httpx.MockTransport(handler)))
    session = client.create_resubscribe_checkout(ResubscribeRequest("org-1", "cus_1", 4, "fi", datetime(2026, 10, 6, tzinfo=UTC), "org-1:abc"))
    path, form, key = seen[0]
    assert session.id == "cs_1" and path == "/v1/checkout/sessions" and key == "organization-resubscribe:org-1:abc"
    assert form["customer"] == ["cus_1"] and "customer_email" not in form and form["line_items[0][quantity]"] == ["4"]
    assert form["metadata[purpose]"] == ["resubscribe"] and form["metadata[seats]"] == ["4"] and form["locale"] == ["fi"]
    assert form["success_url"] == ["http://localhost:8173/organizations/org-1/admin/billing?checkout=returned"]

    now = 1_790_000_000
    payload = json.dumps({"id": "evt_1", "type": "checkout.session.completed", "created": now, "data": {"object": {"id": "cs_1", "customer": "cus_1", "subscription": "sub_2", "payment_status": "paid", "client_reference_id": "org-1", "metadata": {"organization_id": "org-1", "purpose": "resubscribe", "seats": "4"}}}}).encode()
    signature = f"t={now},v1={hmac.new(b'whsec_test', f'{now}.'.encode() + payload, hashlib.sha256).hexdigest()}"
    parsed = StripeSignatureVerifier("whsec_test", timestamp=lambda: now).verify(payload, signature)
    assert (parsed.purpose, parsed.quantity, parsed.subscription_id, parsed.organization_id) == ("resubscribe", 4, "sub_2", "org-1")


def contact(client, world, **body):
    return client.put(f"{world.org}/billing/contact", json={"billing_name": "Northwind", "billing_email": "billing@example.com", **body})


def notice_mails(world):
    with world.application.state.database_engine.begin() as connection:
        return [row.payload for row in connection.execute(text("SELECT payload FROM outbox_messages WHERE topic = 'billing.contact_changed' AND organization_id = :org ORDER BY created_at"), {"org": world.organization_id})]


def test_the_billing_email_changes_in_stripe_and_here_and_the_old_address_gets_a_masked_notice(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "bill-email", stripe=stripe)
    admin, _, _ = world.person("admin", role="admin")
    assert world.owner.get(f"{world.org}/billing/contact").json() == {"billing_name": "Northwind", "billing_email": "billing@example.com"}
    response = contact(world.owner, world, billing_email="  finance@newco.example.org ")
    assert response.status_code == 200 and response.json()["billing_email"] == "finance@newco.example.org"
    assert stripe.customer_updates == [{"customer_id": f"cus_{world.organization_id}", "name": "Northwind", "email": "finance@newco.example.org"}]
    assert world.owner.get(f"{world.org}/billing/contact").json()["billing_email"] == "finance@newco.example.org"
    [mail] = notice_mails(world)
    assert mail["to"] == "billing@example.com" and "f***@n***.org" in mail["text"] and "finance@newco" not in mail["text"] + mail["subject"]
    entry = next(item for item in audit(world) if item["action"] == "organization.billing_contact_changed")
    assert entry["change_summary"] == {"fields": ["email"]} and "finance" not in str(entry)
    [notice] = world.notices(admin, "billing_contact_changed")
    assert notice["params"] == {"fields": ["email"]} and world.notices(world.owner, "billing_contact_changed") == []


def test_a_name_only_change_sends_no_email_and_an_unchanged_contact_does_nothing(database_url, stack) -> None:
    stripe = ManageStripe()
    world = World(stack, database_url, "bill-name", stripe=stripe)
    assert contact(world.owner, world).status_code == 200 and stripe.customer_updates == []
    assert contact(world.owner, world, billing_name="  Northwind Oy ").json()["billing_name"] == "Northwind Oy"
    assert [entry["change_summary"]["fields"] for entry in audit(world) if entry["action"] == "organization.billing_contact_changed"] == [["name"]]
    assert notice_mails(world) == []
    assert len(stripe.customer_updates) == 1


def test_a_stripe_failure_and_bad_input_change_nothing(database_url, stack) -> None:
    stripe = ManageStripe()
    stripe.fail_customer = True
    world = World(stack, database_url, "bill-fail", stripe=stripe)
    assert contact(world.owner, world, billing_email="new@example.org").status_code == 502
    assert world.owner.get(f"{world.org}/billing/contact").json()["billing_email"] == "billing@example.com"
    assert notice_mails(world) == [] and not any(item["action"] == "organization.billing_contact_changed" for item in audit(world))
    for bad in ({"billing_email": "not-an-address"}, {"billing_email": "a@b"}, {"billing_name": "   "}, {"billing_name": "x" * 201}):
        assert contact(world.owner, world, **bad).status_code == 422, bad


def test_changes_per_day_are_limited_and_only_owners_edit(database_url, stack, monkeypatch) -> None:
    monkeypatch.setenv("LIMIT_BILLING_CONTACT_CHANGES_PER_DAY", "2")
    stripe = ManageStripe()
    world = World(stack, database_url, "bill-limit", stripe=stripe)
    admin, _, _ = world.person("admin", role="admin")
    assert admin.get(f"{world.org}/billing/contact").status_code == 403
    assert contact(admin, world, billing_name="Hacked").status_code == 403
    assert contact(world.owner, world, billing_name="One").status_code == 200
    assert contact(world.owner, world, billing_name="Two").status_code == 200
    refused = contact(world.owner, world, billing_name="Three")
    assert refused.status_code == 429 and refused.json()["detail"]["maximum"] == 2 and 1 <= refused.json()["detail"]["retry_after_seconds"] <= 86400
    assert refused.headers["retry-after"] == str(refused.json()["detail"]["retry_after_seconds"])
    assert contact(world.owner, world, billing_name="Two").status_code == 200  # unchanged: nothing to count
    assert len(stripe.customer_updates) == 2


def test_the_stripe_client_updates_name_and_email_on_the_customer() -> None:
    import httpx
    from urllib.parse import parse_qs

    from app.billing import StripeBillingClient, StripeSettings

    seen = []
    handler = lambda request: (seen.append((request.url.path, parse_qs(request.content.decode()))), httpx.Response(200, json={"id": "cus_1"}))[1]
    client = StripeBillingClient(StripeSettings("sk_test", "whsec", "price_1", "http://localhost"), client=httpx.Client(base_url="https://stripe.test", transport=httpx.MockTransport(handler)))
    client.update_customer(customer_id="cus_1", name="Northwind Oy", email="finance@example.org")
    assert seen == [("/v1/customers/cus_1", {"name": ["Northwind Oy"], "email": ["finance@example.org"]})]


def test_the_masked_address_shows_a_hint_only() -> None:
    from app.billing_contact import mask_email

    assert mask_email("billing@example.com") == "b***@e***.com" and mask_email("a@b.co.uk") == "a***@b***.uk" and mask_email("x@host") == "x***@h***"
