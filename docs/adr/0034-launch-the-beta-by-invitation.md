---
status: proposed
---

# Launch the beta by invitation

## Context

Anyone can create an Authentik account, and any signed-in account can start
Organization signup and pay in Stripe Checkout. The first release to prospective
customers should reach only invited organizations, run on the single production
host with its PostgreSQL container, and be cheap to open up later. The product
cannot gate sign-in itself: the people a customer invites must be able to enroll.

## Decision

- **Phases.** The first release is an internal **alpha** for the corporate group,
  with Stripe in its sandbox, the database in its container, daily off-host
  backups, and enrollment limited to people holding an Authentik invitation (Authentik's
  Invitation stage, sent by the operator) instead of the Beta Invitation (`docs/runbooks/alpha-launch.md`). The alpha's data is removed when
  the beta starts, because sandbox Stripe identifiers do not exist in live mode.
  The beta is the invited external phase described below; general availability
  follows it.

- **Gate Organization creation, not sign-in.** While the signup mode is `invite`,
  creating an Organization requires a **Beta Invitation**: an entry bound to a
  verified email address, with an expiry, used up by one Organization, and
  optionally carrying a seat limit, a note, and a Stripe coupon. Platform Admins
  create and revoke them in the operator console. Joining an Organization through
  an ordinary Invitation (ADR-0023) is unaffected. At general availability the
  mode is `open`.
- **No typed promo codes for access.** Shared codes leak and cannot carry a person
  or a price. Stripe promotion codes stay off; the beta price is a coupon the
  backend applies to the Checkout session from the invitation.
- **A discount is not a trial.** ADR-0009 excludes free trials; a time-limited
  coupon for invited customers, with the card collected at signup, is recorded here
  as the beta exception and does not change the commercial model.
- **Database for the beta.** PostgreSQL stays in its container on the production
  host, on the condition that both databases are backed up hourly, encrypted, and
  copied off the host, that a missed backup alerts a person, and that a restore to
  a new host has been rehearsed. Moving to a managed PostgreSQL is a gate for
  opening signups, pending a compatibility check (row-level security, the
  non-owner application role, two databases, connection limits).
- **Cards only.** Delayed payment methods (SEPA Direct Debit, bank transfers) stay
  off until the webhook handles `checkout.session.async_payment_succeeded`.

## Consequences

- One table, one platform route set, an operator console page, and a signup check
  are needed; the Stripe client gains a coupon on the Checkout session.
- The off-host backup copy introduces a place that holds all customer data and an
  encryption key to look after.
- The recovery point is one hour, not zero, and the single host remains a single
  point of failure; the beta terms say so.
- Refines ADR-0009 (the beta coupon), ADR-0011 (backups of the two databases), and
  ADR-0023 (a new email, the Beta Invitation).

Refined by ADR-0035 (the host, the image delivery, and the database stance for the test phase).
