# Billing

## Provider

Stripe Billing is the system of record for subscription and payment state.

## Commercial model

- One billable Organization seat costs EUR 30 per month.
- Seats are purchased per Organization and each billing month is charged in advance.
- The base price and any applicable tax are shown separately and clearly during Stripe Checkout.
- V1 has one plan and no free trial, usage metering, or customer-facing feature tiers.
- Every active Organization User, including Owners, Admins, Editors, and Viewers, occupies one seat.
- Pending Invitations, Platform Users, and time-limited Support Access do not occupy seats.
- The same User Account occupies one separate seat in every Organization where it has an active membership.

## Ownership boundary

- Each Organization maps to one Stripe Customer and one monthly prepaid per-seat Subscription.
- Billing belongs to the Organization, never to a User Account.
- Organization Owners start Checkout and access Stripe's hosted Customer Portal.
- Yearclock remains authoritative for Organization ownership, roles, and product entitlements.
- Yearclock remains authoritative for the active membership count and purchased seat capacity; Stripe remains authoritative for payment and subscription quantity.

## Seat capacity

- The first checkout purchases at least one seat for the initial Owner.
- Owners manage seat capacity through Yearclock's billing UI; direct quantity adjustment in the hosted Customer Portal is disabled so membership invariants can be checked first.
- The production Customer Portal configuration must keep **Update quantities**
  off. The portal may still expose payment-method, invoice, and end-of-period
  cancellation controls.
- Before an increase, Yearclock displays Stripe's proration preview. Confirmation uses an immediate prorated invoice and a pending update so capacity becomes usable only after successful payment is confirmed.
- A decrease is scheduled for the next renewal and cannot reduce capacity below active Organization Users plus reserved Invitations.
- Once a decrease is scheduled, available capacity is calculated against the
  lower renewal quantity. This prevents new Invitations or memberships from
  invalidating the scheduled quantity before it takes effect.
- An Invitation reserves an available seat until it is accepted, revoked, superseded, or expires.
- Organization Admins may manage memberships and Invitations only within already-purchased capacity.
- When no unreserved seat is available, an Owner must increase capacity before another Invitation can be issued.
- Removing an Organization User releases the seat for reuse immediately but does not create a credit for the current prepaid period.

## State synchronization

Implementation: `backend/app/subscription_access.py` projects these events for
an Organization's subscription (`stripe_subscription_id`):

| Stripe event | Effect |
| --- | --- |
| `invoice.payment_failed` (renewal, no seat change) | `active` → `grace` for seven days from the event time |
| `invoice.paid` / `invoice.payment_succeeded` (no seat change) | `grace` → `active` |
| `customer.subscription.updated` | Records `cancel_at_period_end` and `current_period_end` |
| `customer.subscription.deleted` | `canceled`: read-only; content and the Organization stay |
| `checkout.session.completed` with `metadata.purpose=resubscribe` (paid, for the Checkout session the Organization started) | Resubscription: new subscription id, `active`, bought seats, cancellation flag cleared (ADR-0032) |

The effective state is `active`, `grace` (still writable), or `read_only`
(expired grace or ended subscription). Events older than the last applied
subscription event are ignored (`ignored_stale`); duplicate event ids are
recorded once. Every state change writes an `organization.subscription_changed`
Audit Event.

- The backend stores Stripe identifiers and a local projection of subscription status.
- Verified Stripe webhooks update the local projection.
- Webhook processing must be idempotent because events may be delivered more than once.
- Seat-change events are correlated to one retained change record. A terminal
  change cannot be applied or failed again, so delayed and out-of-order events
  cannot overwrite newer capacity.
- Browser redirects from Checkout or the Customer Portal never establish entitlement by themselves.

## Signup and activation

- Organization signup creates a Pending Activation record before redirecting its prospective Owner to Stripe Checkout.
- Initial Checkout purchases one or more seats, including the initial Owner's seat.
- The Organization becomes Active only after a verified Stripe event confirms the first successful payment.
- An abandoned Pending Activation record expires after 24 hours and grants no Organization access.

## Renewal and cancellation

- An Owner may cancel at any time in Yearclock (**Billing and seats**, ADR-0032) or through the hosted Customer Portal; both give the same state.
- In Yearclock the cancellation is always at the end of the paid period, and an Owner can undo it until then. Stripe is called first (`StripeBilling.set_cancel_at_period_end`); when it fails nothing changes locally. On success the projection (`cancel_at_period_end`, `current_period_end`) is updated from Stripe's answer in the same request and `subscription_event_at` is advanced, so older events still in flight cannot undo it; the webhook that follows leaves the state unchanged.
- A subscription held by a subscription schedule (a scheduled seat decrease) cannot be changed directly, so the schedule is released first. The pending seat change is marked failed with the reason `subscription_cancel_scheduled`, and undoing the cancellation does not bring it back.
- Cancellation takes effect at the end of the already-paid billing period, with full access continuing until then.
- V1 does not prorate or refund unused time by default, except where required by law or handled manually by the Platform Operator.
- Cancellation never deletes the Organization or its content.
- An Owner may reverse a scheduled cancellation before the period ends.

## Next charge and payment history

- Owners see the next charge and the last 12 invoices in **Billing and seats**. Both are read from Stripe on each request (`StripeBilling.upcoming_charge` through `POST /v1/invoices/create_preview` with only the subscription, and `list_invoices` through `GET /v1/invoices?customer=`); Yearclock stores nothing and computes no amount. A Stripe failure shows as `unavailable` in the page and never fails it. The restricted key needs read access to invoices.

## Resubscription

- When the subscription has ended (`canceled`) an Owner can subscribe again in Yearclock (**Billing and seats**). `POST /billing/resubscribe` starts a Stripe Checkout in subscription mode for the Organization's existing Stripe customer (`StripeBilling.create_resubscribe_checkout`, metadata `purpose=resubscribe` and `seats`) with at least the current members plus reserved invitations as seats, stores the Checkout session id, and returns its address. A second attempt replaces the stored session.
- Only a verified, paid `checkout.session.completed` for that session and customer counts. `resume_subscription` then stores the old subscription id in `previous_subscription_ids`, sets the new `stripe_subscription_id`, state `active`, the bought seats (`seat_version` increases), clears the cancellation flag, grace, and period end, writes `organization.subscription_changed` with the outcome `subscription_resumed`, and notifies Owners and Admins. A browser return from Checkout never establishes anything by itself.
- Events of an earlier subscription no longer match `stripe_subscription_id` and are ignored. An abandoned Checkout changes nothing. Content is never touched.

## Failed renewal

- A failed renewal starts a seven-day grace period with normal access and a visible billing warning.
- During grace, Owners can update payment details through the Customer Portal.
- After grace expires without successful payment, customer content becomes read-only while Owners retain billing access.
- A later confirmed payment restores normal entitlement without recreating the Organization.

## Tax

Stripe collects the billing address and tax identifiers and calculates tax according to the production Stripe configuration. Exact tax registrations and treatment require review before production launch.
