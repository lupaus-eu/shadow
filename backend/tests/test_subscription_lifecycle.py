"""Renewal, cancellation, and payment-failure states (ticket 17)."""
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.billing import PortalSession, StripeEvent, StripeSignatureVerifier
from app.main import create_app
from test_invitations import NOW, OIDC, Stripe, Verifier, active_org, join, login


class PortalStripe(Stripe):
    def __init__(self) -> None:
        self.portal_requests: list[dict] = []

    def create_portal_session(self, *, customer_id: str, return_url: str) -> PortalSession:
        self.portal_requests.append({"customer_id": customer_id, "return_url": return_url})
        return PortalSession(url=f"https://billing.stripe.test/session/{customer_id}")


def _event(organization_id: str, event_type: str, event_id: str, created: datetime, **fields) -> StripeEvent:
    return StripeEvent(id=event_id, type=event_type, checkout_session_id=None, organization_id=organization_id, customer_id=f"cus_{organization_id}", subscription_id=f"sub_{organization_id}", payment_status=None, created_at=created, **fields)


def _post(client: TestClient, verifier: Verifier, event: StripeEvent) -> dict:
    verifier.event = event
    return client.post("/api/v1/billing/stripe/webhook", content=b"{}", headers={"Stripe-Signature": "test"}).json()


def test_grace_read_only_and_recovery_follow_verified_payment_events(database_url: str) -> None:
    verifier, stripe = Verifier(), PortalStripe()
    application = create_app(database_url=database_url, oidc_client=OIDC("billing-owner", "billing-owner@example.com"), stripe_billing=stripe, stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        orgs = f"/api/v1/organizations/{organization_id}"
        clock = client.get(orgs).json()["yearclocks"][0]
        events_path = f"{orgs}/yearclocks/{clock['id']}/events"
        body = {"title": "Plan", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-05-01"}
        now = datetime.now(UTC)

        failed = _post(client, verifier, _event(organization_id, "invoice.payment_failed", "evt_renewal_failed", now - timedelta(days=2), billing_reason="subscription_cycle"))
        grace = client.get(orgs).json()["subscription"]
        during_grace = client.post(events_path, json=body).status_code

        with application.state.database_engine.begin() as connection:
            connection.execute(text("UPDATE organizations SET grace_expires_at = now() - interval '1 minute' WHERE id = :id"), {"id": organization_id})
        expired = client.get(orgs).json()["subscription"]
        read_only_write = client.post(events_path, json=body).status_code
        read_only_read = client.get(events_path).status_code
        portal = client.post(f"{orgs}/billing/portal")

        stale_paid = _post(client, verifier, _event(organization_id, "invoice.paid", "evt_old_paid", now - timedelta(days=3)))
        paid = _post(client, verifier, _event(organization_id, "invoice.paid", "evt_renewal_paid", now - timedelta(days=1)))
        duplicate = _post(client, verifier, _event(organization_id, "invoice.paid", "evt_renewal_paid", now - timedelta(days=1)))
        recovered = client.get(orgs).json()["subscription"]
        after_recovery = client.post(events_path, json=body).status_code
    assert failed["outcome"] == "subscription_grace_started"
    assert grace["state"] == "grace" and grace["writable"] is True
    assert datetime.fromisoformat(grace["grace_expires_at"]) - (now - timedelta(days=2)) == timedelta(days=7)
    assert during_grace == 201
    assert expired["state"] == "read_only" and expired["writable"] is False
    assert read_only_write == 403 and read_only_read == 200
    assert portal.status_code == 200 and portal.json()["url"] == f"https://billing.stripe.test/session/cus_{organization_id}"
    assert stripe.portal_requests[0]["return_url"].endswith(f"/organizations/{organization_id}")
    assert stale_paid["outcome"] == "ignored_stale"
    assert paid["outcome"] == "subscription_recovered"
    assert duplicate["duplicate"] is True
    assert recovered["state"] == "active"
    assert after_recovery == 201
    with application.state.database_engine.connect() as connection:
        changes = connection.execute(text("SELECT change_summary->>'state' FROM audit_events WHERE organization_id = :id AND action = 'organization.subscription_changed' ORDER BY occurred_at"), {"id": organization_id}).scalars().all()
    assert changes == ["grace", "active"]


def test_cancellation_is_scheduled_reversible_and_never_deletes_content(database_url: str) -> None:
    verifier, stripe = Verifier(), PortalStripe()
    application = create_app(database_url=database_url, oidc_client=OIDC("cancel-owner", "cancel-owner@example.com"), stripe_billing=stripe, stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        orgs = f"/api/v1/organizations/{organization_id}"
        clock = client.get(orgs).json()["yearclocks"][0]
        events_path = f"{orgs}/yearclocks/{clock['id']}/events"
        client.post(events_path, json={"title": "Keep me", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-05-01"})
        now = datetime.now(UTC)
        period_end = now + timedelta(days=20)
        scheduled = _post(client, verifier, _event(organization_id, "customer.subscription.updated", "evt_cancel", now - timedelta(hours=3), cancel_at_period_end=True, current_period_end=period_end, subscription_status="active"))
        while_scheduled = client.get(orgs).json()["subscription"]
        write_while_scheduled = client.post(events_path, json={"title": "Still writable", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-05-02"}).status_code
        reversed_event = _post(client, verifier, _event(organization_id, "customer.subscription.updated", "evt_uncancel", now - timedelta(hours=2), cancel_at_period_end=False, current_period_end=period_end, subscription_status="active"))
        after_reversal = client.get(orgs).json()["subscription"]
        _post(client, verifier, _event(organization_id, "customer.subscription.updated", "evt_cancel_again", now - timedelta(hours=1), cancel_at_period_end=True, current_period_end=period_end, subscription_status="active"))
        ended = _post(client, verifier, _event(organization_id, "customer.subscription.deleted", "evt_ended", now, subscription_status="canceled"))
        late_update = _post(client, verifier, _event(organization_id, "customer.subscription.updated", "evt_late", now - timedelta(minutes=30), cancel_at_period_end=True, subscription_status="active"))
        after_end = client.get(orgs)
        titles = [item["title"] for item in client.get(f"{events_path}?window_start=2026-01-01").json()]
        write_after_end = client.post(events_path, json={"title": "Blocked", "lane_id": clock["lanes"][0]["id"], "starts_on": "2026-05-03"}).status_code
        portal_after_end = client.post(f"{orgs}/billing/portal").status_code
    assert scheduled["outcome"] == "subscription_updated"
    assert while_scheduled["cancel_at_period_end"] is True and while_scheduled["state"] == "active"
    assert datetime.fromisoformat(while_scheduled["current_period_end"]) == period_end
    assert write_while_scheduled == 201
    assert reversed_event["outcome"] == "subscription_updated" and after_reversal["cancel_at_period_end"] is False
    assert ended["outcome"] == "subscription_canceled"
    assert late_update["outcome"] == "ignored_stale"
    assert after_end.status_code == 200 and after_end.json()["subscription"]["state"] == "read_only"
    assert titles == ["Keep me", "Still writable"]
    assert write_after_end == 403
    assert portal_after_end == 200


def test_only_owners_open_the_customer_portal(database_url: str) -> None:
    verifier, stripe = Verifier(), PortalStripe()
    owner_app = create_app(database_url=database_url, oidc_client=OIDC("portal-owner", "portal-owner@example.com"), stripe_billing=stripe, stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(owner_app) as owner:
        login(owner)
        organization_id = active_org(owner, verifier)
        admin_app, _ = join(owner_app, owner, organization_id, subject="portal-admin", email="portal-admin@example.com", role="admin")
    with TestClient(admin_app) as admin:
        login(admin)
        assert admin.post(f"/api/v1/organizations/{organization_id}/billing/portal").status_code == 403
    assert stripe.portal_requests == []


def test_seat_invoices_do_not_change_renewal_state(database_url: str) -> None:
    verifier = Verifier()
    application = create_app(database_url=database_url, oidc_client=OIDC("seat-invoice", "seat-invoice@example.com"), stripe_billing=PortalStripe(), stripe_webhook_verifier=verifier, clock=lambda: NOW)
    with TestClient(application) as client:
        login(client)
        organization_id = active_org(client, verifier)
        outcome = _post(client, verifier, _event(organization_id, "invoice.payment_failed", "evt_seat_invoice", datetime.now(UTC), billing_reason="subscription_update"))
        state = client.get(f"/api/v1/organizations/{organization_id}").json()["subscription"]["state"]
    assert outcome["outcome"] == "ignored"
    assert state == "active"


def _signed(payload: dict, secret: str, now: int) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), f"{now}.".encode() + body, hashlib.sha256).hexdigest()
    return body, f"t={now},v1={signature}"


def test_the_verifier_reads_renewal_and_cancellation_fields() -> None:
    now = 1_790_000_000
    verifier = StripeSignatureVerifier("whsec_test", timestamp=lambda: now)
    invoice, invoice_signature = _signed({"id": "evt_1", "type": "invoice.payment_failed", "created": now, "data": {"object": {"id": "in_1", "customer": "cus_1", "billing_reason": "subscription_cycle", "parent": {"subscription_details": {"subscription": "sub_1", "metadata": {"organization_id": "org-1"}}}}}}, "whsec_test", now)
    subscription, subscription_signature = _signed({"id": "evt_2", "type": "customer.subscription.updated", "created": now, "data": {"object": {"id": "sub_1", "customer": "cus_1", "status": "active", "cancel_at_period_end": True, "metadata": {"organization_id": "org-1"}, "items": {"data": [{"quantity": 3, "current_period_end": now + 86_400}]}}}}, "whsec_test", now)
    parsed_invoice = verifier.verify(invoice, invoice_signature)
    parsed_subscription = verifier.verify(subscription, subscription_signature)
    assert (parsed_invoice.organization_id, parsed_invoice.subscription_id, parsed_invoice.billing_reason) == ("org-1", "sub_1", "subscription_cycle")
    assert parsed_subscription.cancel_at_period_end is True
    assert parsed_subscription.current_period_end == datetime.fromtimestamp(now + 86_400, tz=UTC)
    assert parsed_subscription.subscription_status == "active"
