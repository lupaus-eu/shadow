# Alpha launch

Status: plan, not executed. The alpha is the first release: an internal pilot for
people in the same corporate group, on the production stack with Stripe in its
sandbox. Its purpose is to try and improve features and to show the software to
people outside the development team. It comes before the invited beta in
[`beta-launch.md`](beta-launch.md); read that runbook for the phases and for what
the beta adds. Record the date, the person, and the evidence next to each item
when it is done.

## Name

Call this phase the **alpha** (in Finnish, *alfa* or *konsernipilotti*). "Pre-beta"
works but is not a common term; the usual meaning of the words fits better:

| Phase | Who | Payments | Promise |
| --- | --- | --- | --- |
| **Alpha** (this runbook) | Colleagues in the same group, a few dozen people | Stripe sandbox, no money | Features may change or break; data may be removed |
| **Beta** | Invited external organizations | Stripe live, a beta price | A named support contact, hourly restore-tested backups, notice of changes |
| **General availability** | Anyone | Stripe live | The published terms and prices |

## Scope

- **Who:** employees of the group's companies. The people are known, and one
  company (the one running the alpha) is the controller of their account data.
- **What:** trying features, finding what is wrong or missing, and demonstrations
  to colleagues who are not developers. Planning content may be real or invented.
- **Payments:** Stripe's sandbox only. Checkout shows that it is a test, and a test
  card (`4242 4242 4242 4242`) completes it. No invoice or receipt from the alpha
  is a real one, and nothing needs the accountant.
- **What the alpha promises:** nothing about uptime or data. Say so in the notice
  below.

## What the alpha changes in the beta plan

| Beta gate | In the alpha |
| --- | --- |
| Invitation gate on Organization creation (ADR-0034, ticket 01) | **Not built.** Enrollment needs an Authentik invitation, sent by the operator (below) |
| Beta price and coupon (ticket 02) | Not needed |
| Stripe live account, tax, receipts, restricted key | **Sandbox only** (`stripe-production.md` sections 2 to 5, 8 and 9 wait for the beta) |
| Hourly encrypted off-host backups with a restore to a new host | **Daily** encrypted off-host backups and one restore rehearsal; the rest waits for the beta |
| Public beta terms, privacy policy, DPA template | A short alpha notice and an intra-group data arrangement (below) |
| Rate limiting, dependency audit | Should, not must |
| Managed PostgreSQL | Not needed; the database stays in its container |
| External penetration test | Not needed |

## Access without new code

The alpha does not need the Beta Invitation. The operator chooses who may use it,
from any company or domain, and two measures keep it to them:

1. **Enrollment only by an Authentik invitation.** Authentik's own Invitation stage
   in the enrollment flow admits only people who hold an invitation link. The
   operator creates the invitations (Authentik administration, Directory,
   Invitations: one per person or a reusable one, with an expiry and optionally
   single use) and sends the links. Without the link the enrollment page refuses
   to continue ("continue flow without invitation" off). Put the stage in the
   repository's blueprint (`authentik/blueprints/yearclock-identity-flows.yaml`),
   because the blueprint is re-applied on every start and would remove a change
   made only in the Authentik interface (ticket 09 of
   `.scratch/tech-beta-launch/`). Invitations have no domain limit, so any address
   works. Existing accounts sign in as usual.
2. **Do not announce the address.** Use a domain that is easy to set up and share it
   with the invitees only. The final product name and domain are not needed yet;
   changing the address later means the OIDC redirect URIs, the cookie domain,
   `FRONTEND_URL`, and the Stripe webhook address, which are all configuration.

There is no network restriction: the address is reachable from anywhere, and the
invitation is the gate. Joining an Organization by an Yearclock Invitation works as
before, but the invitee must first hold an Authentik invitation to create an
account. Anyone with an invitation link can also create an Organization of their
own, which is fine for an alpha with sandbox payments.

## Gates for the alpha

### Must be done first

- [ ] **human** Production host, secrets, DNS, TLS, and the Authentik
  administrator with MFA (`production-readiness.md` sections 1, 2, and 5).
- [ ] **human** Scaleway sending domain verified and one Invitation and one
  Authentik email delivered (`production-readiness.md` section 4). Authentik's
  enrollment and recovery emails depend on it.
- [ ] **human** Stripe **sandbox** keys and a sandbox webhook endpoint for the
  alpha address (`production-readiness.md` section 3 with the sandbox, the same
  events, and the portal configured as in `stripe-production.md` section 5). Make
  sure no live key is on the host: `STRIPE_SECRET_KEY` starts with `sk_test_` or
  `rk_test_`.
- [ ] **human** The Authentik invitation requirement is in place (ticket 09,
  implemented; production default `AUTHENTIK_ENROLLMENT_OPEN=false`). Check that
  the enrollment page refuses a visitor without an invitation link, and create the
  first invitations as in [`authentik-invitations.md`](authentik-invitations.md).
- [ ] **human** Daily backups of both databases, encrypted, copied off the host, with
  a failure alert, and one restore rehearsed with `scripts/ops/restore-drill.sh`
  (ticket 03, implemented; set up as in [`backup.md`](backup.md) at the daily
  frequency). Keep `.env.production` in the password manager.
- [ ] **human** Container log rotation and an uptime check that reaches a person
  (ticket 04, implemented: rotation is in `docker-compose.prod.yml`; the disk check
  is in [`backup.md`](backup.md) and `docs/operations/monitoring.md`).
- [ ] **human** The alpha notice and the intra-group arrangement (below).
- [ ] **human** A named person who answers questions and decides about fixes.

### Should be done soon

- A weekly dependency audit run (ticket 06) and a note on rate limiting (ticket 05).
- A short getting-started note per language, taken from the end-user tutorial.
- Sample content for demonstrations: a Yearclock with Lanes, Categories, Labels,
  a Series, and a Linked Lane made by hand in a demonstration Organization.

## The alpha notice and personal data

Colleagues' names, emails, and planning content are personal data even in an alpha,
and the group's companies are separate legal entities.

- [ ] **human** A one-page notice, in Finnish and English, linked from the
  invitation message: what the alpha is for, that payments are test payments, that
  data may be changed or removed (see the end of the alpha), who to ask, and who the
  controller is. It can be a page in the group's intranet; legal wording is for
  your lawyer.
- [ ] **human** A short written arrangement between the group company that runs
  Yearclock and any other company whose employees use it, stating the roles
  (controller and processor) and the purposes. Use the group's own template if it
  has one.
- [ ] **human** The processing records in `docs/gdpr/README.md` already list what
  Yearclock holds; add the alpha to the group's own records of processing.

## Running the alpha

- **Trying features:** the "needs a human" items in
  [`docs/end-user-tutorial/yearclock-v2-testing.md`](../end-user-tutorial/yearclock-v2-testing.md)
  and each `acceptance-trace.md` under `.scratch/` are ready-made test scripts for
  colleagues: print, export and import, the calendar file, notifications, the
  subscription flows with test cards, ownership transfer, and the richer Event
  content. Give each tester two or three chapters and ask for notes.
- **Demonstrations:** use the demonstration Organization, switch the interface
  language to match the audience, and try the print layout and the calendar file;
  they show well to non-developers.
- **Feedback:** one place (a shared channel or a document) and a short call after
  the first week. Sort what comes in into fix now, roadmap, and not planned.
- **Changes:** deploy as often as needed, but take a backup first (migrations run
  automatically), check `/health` afterwards, and tell the testers when something
  noticeable changes.
- **Watching:** failed jobs and emails in `/platform/jobs`, the uptime check, and
  disk use, daily at first.

## The end of the alpha

Alpha data cannot move to the beta. Organizations activated through the sandbox
carry sandbox Stripe customer and subscription identifiers that do not exist in
live mode, and the product has no tool to move an Organization to another Stripe
customer. Plan for that:

- Say in the notice that the alpha data is removed when the beta starts, and that a
  tester can keep an Event list through **Export to Excel** and bring it back with
  **Import**.
- At the start of the beta use a **fresh Yearclock database** with the live keys and
  keep the final alpha backup for a while. The Authentik database can stay: people
  keep their accounts and sign in again, and the product creates a new account
  record for each.
- Move to the beta when the open decisions in `beta-launch.md` are made, the beta
  gates are done, and the alpha has run long enough to trust the billing and backup
  paths: for example four weeks without a lost or unrecovered incident and the
  subscription flows tried end to end with test clocks.

## Decisions

1. Decided: any address may enroll with an invitation; the operator chooses the
   people. No domain list.
2. Decided: the address is any suitable domain, with no network restriction.
3. Decided: the operator collects feedback and asks the testers separately.
4. Decided: Scaleway Object Storage, with the operator holding the key (see the
   backup section of `beta-launch.md`); an open choice remains of the region.
5. Decided: the operator builds the demonstration Organization by hand.
