import hashlib
import hmac
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException


@dataclass(frozen=True)
class CheckoutRequest:
    organization_id: str
    organization_name: str
    billing_email: str
    seats: int
    locale: str
    expires_at: datetime


@dataclass(frozen=True)
class CheckoutSession:
    id: str
    url: str


@dataclass(frozen=True)
class SeatIncreasePreviewRequest:
    organization_id: str
    subscription_id: str
    current_seats: int
    target_seats: int
    proration_date: datetime


@dataclass(frozen=True)
class SeatIncreasePreview:
    id: str
    amount_due: int
    currency: str
    proration_date: datetime


@dataclass(frozen=True)
class SeatChangeRequest:
    change_id: str
    organization_id: str
    subscription_id: str
    current_seats: int
    target_seats: int
    proration_date: datetime | None = None


@dataclass(frozen=True)
class SeatChangeResult:
    reference: str
    effective_at: datetime | None


@dataclass(frozen=True)
class StripeEvent:
    id: str
    type: str
    checkout_session_id: str | None
    organization_id: str | None
    customer_id: str | None
    subscription_id: str | None
    payment_status: str | None
    seat_change_id: str | None = None
    quantity: int | None = None
    created_at: datetime | None = None
    subscription_status: str | None = None
    cancel_at_period_end: bool | None = None
    current_period_end: datetime | None = None
    billing_reason: str | None = None
    purpose: str | None = None


@dataclass(frozen=True)
class ResubscribeRequest:
    organization_id: str
    customer_id: str
    seats: int
    locale: str
    expires_at: datetime
    request_id: str


@dataclass(frozen=True)
class PortalSession:
    url: str


@dataclass(frozen=True)
class UpcomingCharge:
    """The next regular invoice of a subscription as Stripe previews it."""

    charge_date: datetime | None
    amount: int
    currency: str
    seats: int | None


@dataclass(frozen=True)
class InvoiceSummary:
    id: str
    created: datetime
    amount: int
    currency: str
    state: str
    reason: str
    hosted_invoice_url: str | None


@dataclass(frozen=True)
class CancelResult:
    cancel_at_period_end: bool
    current_period_end: datetime | None


class StripeBilling(Protocol):
    def create_subscription_checkout(
        self,
        request: CheckoutRequest,
    ) -> CheckoutSession: ...

    def preview_seat_increase(
        self,
        request: SeatIncreasePreviewRequest,
    ) -> SeatIncreasePreview: ...

    def request_seat_increase(
        self,
        request: SeatChangeRequest,
    ) -> SeatChangeResult: ...

    def schedule_seat_decrease(
        self,
        request: SeatChangeRequest,
    ) -> SeatChangeResult: ...

    def create_portal_session(self, *, customer_id: str, return_url: str) -> PortalSession: ...

    def set_cancel_at_period_end(self, *, subscription_id: str, cancel: bool, schedule_id: str | None = None) -> CancelResult: ...

    def create_resubscribe_checkout(self, request: ResubscribeRequest) -> CheckoutSession: ...

    def upcoming_charge(self, *, subscription_id: str) -> UpcomingCharge: ...

    def list_invoices(self, *, customer_id: str, limit: int = 12) -> list[InvoiceSummary]: ...

    def update_customer(self, *, customer_id: str, name: str, email: str) -> None: ...


class StripeWebhookVerifier(Protocol):
    def verify(self, payload: bytes, signature: str | None) -> StripeEvent: ...


@dataclass(frozen=True)
class StripeSettings:
    secret_key: str
    webhook_secret: str
    monthly_seat_price_id: str
    frontend_url: str

    @classmethod
    def from_environment(cls) -> "StripeSettings":
        return cls(
            secret_key=os.getenv("STRIPE_SECRET_KEY", ""),
            webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", ""),
            monthly_seat_price_id=os.getenv("STRIPE_MONTHLY_SEAT_PRICE_ID", ""),
            frontend_url=os.getenv("FRONTEND_URL", "http://localhost:8173"),
        )


class StripeBillingClient:
    def __init__(
        self,
        settings: StripeSettings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.Client(
            base_url="https://api.stripe.com",
            timeout=15,
        )

    def create_subscription_checkout(
        self,
        request: CheckoutRequest,
    ) -> CheckoutSession:
        if not self._settings.secret_key or not self._settings.monthly_seat_price_id:
            raise HTTPException(status_code=503, detail="billing is not configured")

        return_path = f"/organization-signups/{request.organization_id}"
        form = [
            ("mode", "subscription"),
            ("client_reference_id", request.organization_id),
            ("customer_email", request.billing_email),
            ("locale", request.locale),
            ("billing_address_collection", "required"),
            ("automatic_tax[enabled]", "true"),
            ("tax_id_collection[enabled]", "true"),
            ("line_items[0][price]", self._settings.monthly_seat_price_id),
            ("line_items[0][quantity]", str(request.seats)),
            ("metadata[organization_id]", request.organization_id),
            (
                "subscription_data[metadata][organization_id]",
                request.organization_id,
            ),
            (
                "success_url",
                f"{self._settings.frontend_url.rstrip('/')}{return_path}?checkout=returned",
            ),
            (
                "cancel_url",
                f"{self._settings.frontend_url.rstrip('/')}{return_path}?checkout=cancelled",
            ),
            ("expires_at", str(int(request.expires_at.timestamp()))),
        ]
        response = self._client.post(
            "/v1/checkout/sessions",
            content=urlencode(form),
            headers={
                "Authorization": f"Bearer {self._settings.secret_key}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Idempotency-Key": f"organization-signup:{request.organization_id}",
            },
        )
        try:
            response.raise_for_status()
            data = response.json()
            return CheckoutSession(id=data["id"], url=data["url"])
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise HTTPException(
                status_code=502,
                detail="unable to start checkout",
            ) from error

    def preview_seat_increase(
        self,
        request: SeatIncreasePreviewRequest,
    ) -> SeatIncreasePreview:
        item = self._subscription_item(
            self._subscription(request.subscription_id)
        )
        timestamp = int(request.proration_date.timestamp())
        data = self._post(
            "/v1/invoices/create_preview",
            [
                ("subscription", request.subscription_id),
                ("subscription_details[items][0][id]", item["id"]),
                (
                    "subscription_details[items][0][quantity]",
                    str(request.target_seats),
                ),
                ("subscription_details[proration_behavior]", "always_invoice"),
                ("subscription_details[proration_date]", str(timestamp)),
            ],
            idempotency_key=None,
            error_detail="unable to preview seat increase",
        )
        try:
            return SeatIncreasePreview(
                id=str(data["id"]),
                amount_due=int(data["amount_due"]),
                currency=str(data["currency"]),
                proration_date=request.proration_date,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=502,
                detail="invalid Stripe preview response",
            ) from error

    def request_seat_increase(
        self,
        request: SeatChangeRequest,
    ) -> SeatChangeResult:
        if request.proration_date is None:
            raise HTTPException(
                status_code=422,
                detail="seat increase requires a proration date",
            )
        item = self._subscription_item(
            self._subscription(request.subscription_id)
        )
        data = self._post(
            f"/v1/subscriptions/{request.subscription_id}",
            [
                ("payment_behavior", "pending_if_incomplete"),
                ("proration_behavior", "always_invoice"),
                ("proration_date", str(int(request.proration_date.timestamp()))),
                ("items[0][id]", item["id"]),
                ("items[0][quantity]", str(request.target_seats)),
                ("metadata[organization_id]", request.organization_id),
                ("metadata[seat_change_id]", request.change_id),
            ],
            idempotency_key=f"seat-increase:{request.change_id}",
            error_detail="unable to request seat increase",
        )
        return SeatChangeResult(reference=str(data["id"]), effective_at=None)

    def schedule_seat_decrease(
        self,
        request: SeatChangeRequest,
    ) -> SeatChangeResult:
        subscription = self._subscription(request.subscription_id)
        item = self._subscription_item(subscription)
        schedule = self._post(
            "/v1/subscription_schedules",
            [
                ("from_subscription", request.subscription_id),
                ("metadata[organization_id]", request.organization_id),
                ("metadata[seat_change_id]", request.change_id),
            ],
            idempotency_key=f"seat-decrease-schedule:{request.change_id}",
            error_detail="unable to create seat decrease schedule",
        )
        try:
            current_period_start = int(subscription["current_period_start"])
            effective_timestamp = int(subscription["current_period_end"])
            price_id = str(item["price"]["id"])
            schedule_id = str(schedule["id"])
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=502,
                detail="invalid Stripe subscription response",
            ) from error
        self._post(
            f"/v1/subscription_schedules/{schedule_id}",
            [
                ("end_behavior", "release"),
                ("proration_behavior", "none"),
                ("phases[0][start_date]", str(current_period_start)),
                ("phases[0][end_date]", str(effective_timestamp)),
                ("phases[0][items][0][price]", price_id),
                (
                    "phases[0][items][0][quantity]",
                    str(request.current_seats),
                ),
                ("phases[0][proration_behavior]", "none"),
                ("phases[1][start_date]", str(effective_timestamp)),
                ("phases[1][items][0][price]", price_id),
                (
                    "phases[1][items][0][quantity]",
                    str(request.target_seats),
                ),
                ("phases[1][iterations]", "1"),
                ("phases[1][proration_behavior]", "none"),
                ("phases[1][metadata][organization_id]", request.organization_id),
                ("phases[1][metadata][seat_change_id]", request.change_id),
            ],
            idempotency_key=f"seat-decrease-apply:{request.change_id}",
            error_detail="unable to schedule seat decrease",
        )
        return SeatChangeResult(
            reference=schedule_id,
            effective_at=datetime.fromtimestamp(effective_timestamp, tz=UTC),
        )

    def create_portal_session(self, *, customer_id: str, return_url: str) -> PortalSession:
        """Open Stripe's hosted Customer Portal for payment methods, invoices, and cancellation."""
        data = self._post(
            "/v1/billing_portal/sessions",
            [("customer", customer_id), ("return_url", return_url)],
            idempotency_key=None,
            error_detail="unable to open the billing portal",
        )
        try:
            return PortalSession(url=str(data["url"]))
        except KeyError as error:
            raise HTTPException(status_code=502, detail="invalid Stripe portal response") from error

    def update_customer(self, *, customer_id: str, name: str, email: str) -> None:
        """Keep Stripe's customer in step with the billing contact; address, tax ID, and payment method stay in the portal."""
        self._post(f"/v1/customers/{customer_id}", [("name", name), ("email", email)], idempotency_key=None, error_detail="unable to update the billing contact")

    def create_resubscribe_checkout(self, request: ResubscribeRequest) -> CheckoutSession:
        """A new subscription for the Organization's existing Stripe customer; the metadata marks it as a resubscription."""
        if not self._settings.secret_key or not self._settings.monthly_seat_price_id:
            raise HTTPException(status_code=503, detail="billing is not configured")
        base = f"{self._settings.frontend_url.rstrip('/')}/organizations/{request.organization_id}/admin/billing"
        data = self._post(
            "/v1/checkout/sessions",
            [
                ("mode", "subscription"),
                ("customer", request.customer_id),
                ("client_reference_id", request.organization_id),
                ("locale", request.locale),
                ("billing_address_collection", "required"),
                ("customer_update[address]", "auto"),
                ("customer_update[name]", "auto"),
                ("automatic_tax[enabled]", "true"),
                ("tax_id_collection[enabled]", "true"),
                ("line_items[0][price]", self._settings.monthly_seat_price_id),
                ("line_items[0][quantity]", str(request.seats)),
                ("metadata[organization_id]", request.organization_id),
                ("metadata[purpose]", "resubscribe"),
                ("metadata[seats]", str(request.seats)),
                ("subscription_data[metadata][organization_id]", request.organization_id),
                ("success_url", f"{base}?checkout=returned"),
                ("cancel_url", f"{base}?checkout=cancelled"),
                ("expires_at", str(int(request.expires_at.timestamp()))),
            ],
            idempotency_key=f"organization-resubscribe:{request.request_id}",
            error_detail="unable to start checkout",
        )
        try:
            return CheckoutSession(id=data["id"], url=data["url"])
        except KeyError as error:
            raise HTTPException(status_code=502, detail="unable to start checkout") from error

    def set_cancel_at_period_end(self, *, subscription_id: str, cancel: bool, schedule_id: str | None = None) -> CancelResult:
        """Schedule or undo the end of the subscription at the end of the paid period.

        A subscription held by a schedule (a scheduled seat decrease) cannot be changed directly, so the schedule is released first.
        """
        if schedule_id:
            self._post(f"/v1/subscription_schedules/{schedule_id}/release", [], idempotency_key=None, error_detail="unable to release the seat decrease schedule")
        data = self._post(f"/v1/subscriptions/{subscription_id}", [("cancel_at_period_end", "true" if cancel else "false")], idempotency_key=None, error_detail="unable to change the subscription")
        try:
            item = self._subscription_item(data)
            end = data.get("current_period_end") or item.get("current_period_end")
            return CancelResult(cancel_at_period_end=bool(data["cancel_at_period_end"]), current_period_end=datetime.fromtimestamp(int(end), tz=UTC) if end else None)
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=502, detail="invalid Stripe subscription response") from error

    def upcoming_charge(self, *, subscription_id: str) -> UpcomingCharge:
        """The next regular invoice, previewed by Stripe (tax, proration and schedules included)."""
        data = self._post(
            "/v1/invoices/create_preview",
            [("subscription", subscription_id)],
            idempotency_key=None,
            error_detail="unable to preview the next charge",
        )
        try:
            lines = (data.get("lines") or {}).get("data") or []
            line = lines[0] if lines else {}
            moment = data.get("next_payment_attempt") or (line.get("period") or {}).get("start")
            quantity = line.get("quantity")
            return UpcomingCharge(
                charge_date=datetime.fromtimestamp(int(moment), tz=UTC) if moment else None,
                amount=int(data["total"]),
                currency=str(data["currency"]),
                seats=int(quantity) if quantity is not None else None,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=502, detail="invalid Stripe preview response") from error

    def list_invoices(self, *, customer_id: str, limit: int = 12) -> list[InvoiceSummary]:
        """The customer's newest invoices (all subscriptions), without drafts."""
        data = self._get(
            "/v1/invoices",
            {"customer": customer_id, "limit": str(limit)},
            error_detail="unable to list invoices",
        )
        reasons = {"subscription_cycle": "renewal", "subscription_update": "seat_increase", "subscription_create": "signup"}
        try:
            invoices = []
            for item in data["data"]:
                if item.get("status") == "draft":
                    continue
                status = str(item["status"])
                state = "failed" if status == "open" and int(item.get("attempt_count") or 0) > 0 else status
                url = item.get("hosted_invoice_url")
                invoices.append(
                    InvoiceSummary(
                        id=str(item["id"]),
                        created=datetime.fromtimestamp(int(item["created"]), tz=UTC),
                        amount=int(item["total"]),
                        currency=str(item["currency"]),
                        state=state,
                        reason=reasons.get(str(item.get("billing_reason")), "other"),
                        hosted_invoice_url=url if isinstance(url, str) and url.startswith("https://") else None,
                    )
                )
            return invoices[:limit]
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(status_code=502, detail="invalid Stripe invoice response") from error

    def _get(self, path: str, params: dict[str, str], *, error_detail: str) -> dict[str, Any]:
        if not self._settings.secret_key:
            raise HTTPException(status_code=503, detail="billing is not configured")
        response = self._client.get(path, params=params, headers={"Authorization": f"Bearer {self._settings.secret_key}"})
        try:
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(status_code=502, detail=error_detail) from error

    def _subscription(self, subscription_id: str) -> dict[str, Any]:
        if not self._settings.secret_key:
            raise HTTPException(status_code=503, detail="billing is not configured")
        response = self._client.get(
            f"/v1/subscriptions/{subscription_id}",
            headers={"Authorization": f"Bearer {self._settings.secret_key}"},
        )
        try:
            response.raise_for_status()
            subscription = response.json()
            items = subscription["items"]["data"]
            if not isinstance(subscription, dict) or len(items) != 1:
                raise ValueError
            return subscription
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=502,
                detail="unable to load Stripe subscription",
            ) from error

    @staticmethod
    def _subscription_item(subscription: dict[str, Any]) -> dict[str, Any]:
        try:
            item = subscription["items"]["data"][0]
            if not isinstance(item, dict):
                raise ValueError
            return item
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise HTTPException(
                status_code=502,
                detail="invalid Stripe subscription response",
            ) from error

    def _post(
        self,
        path: str,
        form: list[tuple[str, str]],
        *,
        idempotency_key: str | None,
        error_detail: str,
    ) -> dict[str, Any]:
        if not self._settings.secret_key:
            raise HTTPException(status_code=503, detail="billing is not configured")
        headers = {
            "Authorization": f"Bearer {self._settings.secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        response = self._client.post(
            path,
            content=urlencode(form),
            headers=headers,
        )
        try:
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
            return data
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(status_code=502, detail=error_detail) from error


class StripeSignatureVerifier:
    def __init__(
        self,
        webhook_secret: str,
        *,
        tolerance_seconds: int = 300,
        timestamp: Callable[[], float] = time.time,
    ) -> None:
        self._webhook_secret = webhook_secret
        self._tolerance_seconds = tolerance_seconds
        self._timestamp = timestamp

    def verify(self, payload: bytes, signature: str | None) -> StripeEvent:
        if not self._webhook_secret:
            raise HTTPException(status_code=503, detail="billing is not configured")
        timestamp, signatures = self._parse_signature(signature)
        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac.new(
            self._webhook_secret.encode(),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()
        if (
            not any(hmac.compare_digest(expected, value) for value in signatures)
            or abs(self._timestamp() - timestamp) > self._tolerance_seconds
        ):
            raise HTTPException(status_code=400, detail="invalid Stripe signature")

        try:
            event = json.loads(payload)
            checkout = event["data"]["object"]
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            raise HTTPException(status_code=400, detail="invalid Stripe event") from error

        subscription_details = (
            (checkout.get("parent") or {}).get("subscription_details") or {}
        )
        metadata: dict[str, Any] = (
            checkout.get("metadata")
            or subscription_details.get("metadata")
            or {}
        )
        quantity = checkout.get("quantity")
        if quantity is None and metadata.get("purpose") == "resubscribe":
            quantity = metadata.get("seats")
        items = (checkout.get("items") or {}).get("data") or []
        if quantity is None and items:
            quantity = items[0].get("quantity")
        period_end = checkout.get("current_period_end")
        if period_end is None and items:
            period_end = items[0].get("current_period_end")
        is_subscription = str(event.get("type", "")).startswith("customer.subscription.")
        return StripeEvent(
            id=str(event.get("id", "")),
            type=str(event.get("type", "")),
            checkout_session_id=checkout.get("id"),
            organization_id=metadata.get("organization_id")
            or checkout.get("client_reference_id"),
            customer_id=checkout.get("customer"),
            subscription_id=(
                checkout.get("subscription")
                or subscription_details.get("subscription")
                or (
                    checkout.get("id")
                    if str(event.get("type", "")).startswith(
                        "customer.subscription."
                    )
                    else None
                )
            ),
            payment_status=(
                checkout.get("payment_status")
                or (
                    "paid"
                    if str(event.get("type", "")) in {
                        "customer.subscription.updated",
                        "customer.subscription.pending_update_applied",
                    }
                    and checkout.get("pending_update") is None
                    and checkout.get("status") in {"active", "trialing"}
                    else None
                )
            ),
            seat_change_id=metadata.get("seat_change_id"),
            quantity=int(quantity) if quantity is not None else None,
            created_at=(
                datetime.fromtimestamp(event["created"], tz=UTC)
                if event.get("created") is not None
                else None
            ),
            subscription_status=checkout.get("status") if is_subscription else None,
            cancel_at_period_end=checkout.get("cancel_at_period_end") if is_subscription else None,
            current_period_end=(
                datetime.fromtimestamp(int(period_end), tz=UTC)
                if is_subscription and period_end is not None
                else None
            ),
            billing_reason=checkout.get("billing_reason"),
            purpose=metadata.get("purpose"),
        )

    @staticmethod
    def _parse_signature(signature: str | None) -> tuple[int, list[str]]:
        try:
            components = [
                component.split("=", 1)
                for component in (signature or "").split(",")
            ]
            timestamp = int(
                next(value for key, value in components if key == "t")
            )
            signatures = [
                value for key, value in components if key == "v1"
            ]
            if not signatures:
                raise ValueError
            return timestamp, signatures
        except (StopIteration, TypeError, ValueError) as error:
            raise HTTPException(
                status_code=400,
                detail="invalid Stripe signature",
            ) from error
