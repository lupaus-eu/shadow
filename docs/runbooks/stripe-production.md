# Stripe in production

Status: written, not yet executed. The steps marked **human** need the Stripe
account, the legal entity, DNS, or secrets. Record the date, the person, and the
evidence next to each item when it is done. This runbook expands section 3 of
[`production-readiness.md`](production-readiness.md) and applies to the invited
beta ([`beta-launch.md`](beta-launch.md)) and to general availability.

Stripe renames menus and moves settings often, and it now calls the test
environment a **sandbox**. Dashboard paths below name the area to look for, not a
guaranteed click path; check the linked Stripe documentation when a path differs.
Billing design is in [`docs/architecture/billing.md`](../architecture/billing.md)
and ADR-0009 and ADR-0032.

## What Yearclock uses

| Stripe feature | Used for | Where |
| --- | --- | --- |
| Checkout (subscription mode) | First purchase, and subscribing again after a subscription ended | `app/billing.py` |
| Subscriptions and one monthly per-seat Price | The recurring charge | ADR-0009 |
| Subscription schedules | A seat decrease at renewal | `app/billing.py`, `seat_capacity.py` |
| Invoices (preview) | The prorated charge shown before a seat increase | `seat_capacity.py` |
| Customer Portal | Payment methods, invoice history, tax IDs and address | `billing_routes.py` |
| Customers | One per Organization; name and email edited in Yearclock | `subscription_routes.py` |
| Stripe Tax (`automatic_tax`, tax ID collection) | VAT on every invoice | Checkout session |
| Webhooks | The only source of payment state | `organization_routes.py` |

## 1. Account and business details

- [ ] **human** Create the live account for the legal entity that sells
  Yearclock (the entity on the invoices) and complete business verification.
  The product name, domain, and entity are still placeholders
  ([`launch-checklist.md`](launch-checklist.md)); Stripe needs them first.
- [ ] **human** Public details: legal business name, support email, support
  address, **privacy policy URL**, terms URL, and the statement descriptor.
  Stripe prints the legal name, support address, support email, and privacy
  policy URL on every receipt, so the policy page must exist. Use
  `https://<app domain>/legal/privacy` for the privacy policy URL and
  `https://<app domain>/legal/terms` for the terms URL (the same two links go into the
  Customer Portal business links in section 5); the pages must show published, not draft, text first.
- [ ] **human** Branding: logo (square, at least 128 px), icon, brand and accent
  colours. They apply to Checkout, the Customer Portal, invoices, and receipts.
- [ ] **human** Add the company's VAT ID as an account tax ID so it prints on
  invoices, set the invoice footer (company registration number, address, bank
  details if wanted), and choose the invoice number prefix. Stripe invoices are
  the bookkeeping documents (see section 3).
- [ ] **human** Add the payout bank account, turn on two-factor sign-in for every
  Stripe user, and give each person their own user instead of sharing one login.

## 2. Live-mode objects

Sandbox and live mode hold separate objects, so everything below is created
again in live mode and the live identifiers go into `.env.production`.

- [ ] **human** Product "Yearclock seat" with the **SaaS, business use** product
  tax code, and a recurring EUR 30 per month Price with per-unit pricing. Set the
  Price's tax behaviour on purpose: exclusive (EUR 30 plus VAT) matches
  `docs/architecture/billing.md`, which says the base price and tax are shown
  separately. Set `STRIPE_MONTHLY_SEAT_PRICE_ID`.
- [ ] **human** Stripe Tax: confirm the head office address, add the Finnish VAT
  registration, and add the EU One-Stop-Shop or other registrations only when
  they apply to you. Without a registration in the customer's location Stripe
  calculates zero tax, so check the tax monitoring view after the first sales.
  Customers with an EU VAT ID are handled by the tax ID collection the Checkout
  session already enables (reverse charge where it applies); confirm with the
  accountant what the invoice must show.
- [ ] **human** Sell to businesses only (see the beta terms): consumer sales bring
  withdrawal rights and consumer-VAT rules that the product does not support.
- [ ] **human** Create a **restricted** secret key for the backend instead of the
  unrestricted one, restrict it to the host's IP address if it is stable, store it
  as `STRIPE_SECRET_KEY` in the host's secrets, and rotate it on a schedule.
  Grant write access to Checkout Sessions, Customers, Subscriptions, Subscription
  Schedules, Invoices (the seat preview and the next-charge preview, and reading the
  invoice list shown to Owners), and Billing Portal Sessions, and read
  access to Prices. Stripe's permission errors name the missing permission, so
  run the live smoke test (section 8) with this key and add what it reports.
  Never commit or paste the key (see Stripe's best practices for secret keys).

## 3. Receipts and invoices

Stripe provides both, and they are different documents.

- **Receipt**: proof of a successful payment or refund. Turn on **Successful
  payments** and **Refunds** under *Settings, Business, Customer emails*. A
  receipt is not sent for a failed payment.
- **Invoice**: for a subscription Stripe creates an invoice automatically at
  every renewal, with the seller and buyer details, the VAT lines, the seller and
  buyer tax IDs, and a hosted page and a PDF. **This is the document the
  accountant needs.** Enable the customer emails that send the paid invoice, and
  keep invoice history on in the Customer Portal so an Owner can download any
  past invoice or receipt there (Yearclock does not show invoices itself).
- Corrections and goodwill go through **credit notes** and refunds in the
  Dashboard, never by editing a finalized invoice.
- **Language**: Stripe picks the language from the customer's preferred locales,
  then the account's default language, then the browser. Yearclock does not set
  `preferred_locales` on the customer yet, so set the account default language and
  see ticket 07 of [`.scratch/tech-beta-launch/`](../../.scratch/tech-beta-launch/technical-design.md).
- [ ] **human** Turn on the receipt and invoice emails, send a test receipt from
  the Dashboard (a sandbox payment can only be sent manually), and open the PDF
  with the accountant to confirm it has what Finnish bookkeeping needs.
- [ ] **human** Decide how invoices reach the accounting system: a monthly CSV of
  invoices and payouts from Stripe's reports is enough for the beta. Stripe does
  not issue Finvoice or Peppol e-invoices; ask customers who need them and treat
  it as a later question.

## 4. Webhook endpoint

- [ ] **human** Add `https://<app domain>/api/v1/billing/stripe/webhook` in live
  mode with the events `checkout.session.completed`,
  `customer.subscription.updated`, `customer.subscription.deleted`,
  `customer.subscription.pending_update_applied`,
  `customer.subscription.pending_update_expired`, `invoice.paid`, and
  `invoice.payment_failed`, and set `STRIPE_WEBHOOK_SECRET` to the endpoint's
  signing secret (the sandbox endpoint has its own).
- [ ] **human** Turn on Stripe's email alert for failing webhook deliveries. A
  failed webhook is rolled back and Stripe redelivers it for up to three days;
  Yearclock does not store rejected calls (`docs/operations/monitoring.md`).
- [ ] **human** Roll the secret as described in `production-readiness.md`
  section 3 and rehearse it once before launch.

## 5. Customer Portal (live configuration)

The portal has its own configuration per mode.

- [ ] **human** On: update payment methods, invoice history, customer
  information (email, address, tax IDs), and cancellation at the end of the
  period (Yearclock also cancels in the product, ADR-0032).
- [ ] **human** Off: **update quantities** (the product validates seats first),
  plan switching, and promotion codes. Set the business links (terms, privacy)
  and the default return address to the Organization page.

## 6. Failed payments, retries, and the grace period

Yearclock keeps an Organization fully writable for seven days after the first
failed renewal and then makes it read-only (`docs/architecture/billing.md`).
Stripe's retry settings must tell the same story.

- [ ] **human** *Billing, Revenue recovery, Retries*: use Smart Retries with a
  window of **one week**, and set the action when retries run out to **cancel the
  subscription**. Then Stripe stops retrying when the grace period ends, the
  `customer.subscription.deleted` event makes the Organization read-only for good,
  and an Owner can subscribe again. (Stripe recommends eight attempts over two
  weeks, which also works: the Organization is read-only after seven days, a
  later successful retry brings it back through `invoice.paid`, and a final
  failure ends the subscription. A shorter window is simpler to explain.)
- [ ] **human** Turn on Stripe's emails for failed payments with the portal link,
  and for upcoming renewals. Yearclock also notifies Owners and Admins in the
  product and by email (ADR-0031), so a customer may get both; that is fine.
- [ ] **human** Radar stays on with its defaults, 3D Secure is left to Stripe, and
  a person is named to answer disputes in the Dashboard within Stripe's deadline.

## 7. Payment methods

- [ ] **human** Cards and wallets only for the beta. Do **not** enable SEPA Direct
  Debit, bank transfers, or any other **delayed** payment method yet: Yearclock
  activates an Organization when `checkout.session.completed` arrives with
  `payment_status=paid` and does not handle `checkout.session.async_payment_succeeded`
  or the delayed-failure events. SEPA debit is attractive for European business
  customers, and enabling it is a ticket, not a Dashboard switch.

## 8. Rehearsals before the first real customer

- [ ] **human** In a sandbox with production-like settings, use **test clocks**
  (Stripe's subscription simulations) to run a whole cycle: activation, a renewal,
  a failed renewal and the retries, recovery, a cancellation and its undo, the end
  of a subscription and subscribing again, and a seat increase and decrease.
  Check each state in the product and the Audit Log. This is the only way to see a
  renewal without waiting a month.
- [ ] **human** Live smoke test with the founder's own card and a coupon-free
  EUR 30 seat: sign up, check the invoice PDF, the receipt, the VAT line, the
  portal, then cancel and refund the payment and confirm the Organization state.
  This also proves that the restricted key has every permission it needs.
- [ ] **human** Send a signed webhook with a wrong signature and confirm `400`.

## 9. The beta price

- [ ] **human** Create the coupon in live mode: a percentage coupon with a
  duration (for example 100 % for three months, or 50 % for six months) and no
  public promotion code. The beta invitation names the coupon and the backend
  applies it to the Checkout session (ticket 02 of the beta design), so customers
  cannot stack their own codes. Collect the card even when the first invoices are
  EUR 0, so the subscription continues when the discount ends.
- ADR-0009 says there is no free trial. A time-limited discount for invited
  customers is not a trial period, but record the exception in the beta ADR.

## 10. Running it

- Monthly: reconcile payouts with the bank, export invoices and payouts for the
  accountant, review failed payments and disputes, and review the webhook
  delivery log.
- Quarterly: rotate the restricted key and the webhook secret, review who has
  access to the Stripe account, and review the tax monitoring view.
- When a key leaks: roll it in the Dashboard at once (Stripe also notifies and may
  expire a key it finds exposed), update the host secret, restart `backend`, and
  record it as an incident.

## Features worth knowing about

| Feature | Use | When |
| --- | --- | --- |
| Test clocks (simulations) | Test renewals and failures | Before launch and before billing changes |
| Smart Retries and customer emails | Recover failed renewals with less work | Launch |
| Stripe Tax and its filing partner | VAT calculation and, if wanted, filing | Launch (calculation); filing when the volume justifies it |
| Customer Portal | Self-service for payment methods and invoices | Launch |
| Reports and Billing analytics | Revenue and churn numbers for the beta | Launch |
| Coupons | Beta pricing | Beta |
| SEPA Direct Debit | Cheaper, business-friendly payments | After the async events are handled |
| Revenue recognition, Sigma | Accounting and analysis | Later |
