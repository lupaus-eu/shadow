---
status: accepted
---

# Manage the subscription and ownership in the application

## Context

V1 left cancellation, the undoing of a cancellation, and payment details to
Stripe's Customer Portal (ADR-0009). Owners still need to cancel and undo from
the product, subscribe again after a subscription has ended (today the
Organization stays read-only for good), pass ownership on, and keep the billing
contact current. The V1 PRD said that ownership transfer is adding another
accepted Owner before removing the former one.

## Decision

- **Cancel and undo** in the application, at the end of the paid period only,
  by Owners. Stripe is called first; the local projection is updated from its
  answer in the same request; later webhooks are idempotent. The portal stays
  for payment methods, invoices, and its own cancellation. A scheduled seat
  decrease is released by a cancellation.
- **Resubscribe** an Organization whose subscription has ended with a new
  Checkout for the same Stripe customer, marked `purpose=resubscribe`. Payment
  confirmation attaches the new subscription and reactivates the Organization
  with its content. Content of an ended subscription is not deleted
  automatically.
- **Ownership Transfer** is an atomic action to an existing active member, with
  no acceptance step, and optional step-down. The last Owner leaving must name a
  successor. Many Owners remain allowed.
- **Billing contact** (name and email) is edited in the application and in the
  Stripe customer; address, VAT ID, and payment method stay in the portal. The
  old email address gets a notice with the new one masked.
- Owners and Admins are notified of billing events through P8 notifications.

## Consequences

- The Stripe client gains customer update, cancel-at-period-end, subscription
  schedule release, and a resubscribe Checkout; the webhook gains a
  resubscribe path.
- Refines ADR-0009 (more Owner self-service in the product), ADR-0031 (new
  notification types under the `billing` key), and the V1 PRD statement on
  ownership transfer: an existing member can be promoted and the transferor can
  step down in one action; inviting a new Owner still needs acceptance.
- No free trial, tier, or refund logic is introduced.
