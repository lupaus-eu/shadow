---
status: accepted
---

# Use Stripe for Organization billing

Stripe Billing is the subscription and payment system of record. Each Organization maps to its own Stripe Customer and monthly prepaid Subscription, using Stripe Checkout for initial purchase and the hosted Customer Portal for Owner self-service. Yearclock mirrors subscription status through verified, idempotently processed webhooks but remains authoritative for Organization ownership, roles, and product entitlements.

Failed webhook processing relies on Stripe's redelivery (product decision,
2026-09-23). A webhook is processed in one transaction together with its
idempotency record, so a failure leaves no trace and returns an error; Stripe
retries the delivery for up to three days and shows failed deliveries in its
dashboard. Yearclock therefore stores no failed-webhook record and offers no
webhook replay in the operator console.
