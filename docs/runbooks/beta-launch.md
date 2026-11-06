# Beta launch

Status: plan, not executed. This runbook defines what must be true before
Yearclock is shown to invited prospective customers (the phase after the alpha), how access is limited, and
what the database and backup stance is for that period. It builds on
[`production-readiness.md`](production-readiness.md),
[`launch-checklist.md`](launch-checklist.md), and
[`stripe-production.md`](stripe-production.md). The proposed decisions are in
ADR-0034 and the engineering work is in
[`.scratch/tech-beta-launch/`](../../.scratch/tech-beta-launch/technical-design.md).
Record the date, the person, and the evidence next to each item when it is done.

## Phases

The first release is an **alpha** for colleagues in the same corporate group, with
Stripe in its sandbox and the database still in its container
([`alpha-launch.md`](alpha-launch.md)). This runbook covers the **beta** that follows
for invited external organizations; the gates below that the alpha defers are the
invitation gate, the live Stripe account, the beta price, hourly backups with a
restore to a new host, the public terms and policies, and the rate-limit and audit
decisions.

## Scope

- **Who:** 10 to 25 invited organizations that sell nothing to the public through
  Yearclock: prospective customers, partners, and friendly users. Business
  customers only.
- **What:** real data and real accounts on the production stack, with a beta
  price. It is a product beta, not a test environment: the data is the
  customers' and is protected like production data.
- **What the beta promises:** no uptime guarantee, a named support contact, daily
  backups that are restore-tested, an export of everything on request, and notice
  before the price, the terms, or the end of the beta change. Say so in the beta
  terms.
- **What it does not promise:** high availability, a recovery point under one hour
  (see the database stance), e-invoicing, or SSO (P10b).

## Access: invitation only

Anyone can already create an Authentik account (verified-email enrollment with a
second factor), and any signed-in account can start Organization signup and pay in
Checkout. Limit the one step that costs money and support time:

- **Creating an Organization requires a Beta Invitation.** Signing in and joining
  an existing Organization through an ordinary Invitation (ADR-0023) stay open,
  because the people a customer invites must be able to enroll.
- A Beta Invitation is bound to an email address, expires, is used up by one
  Organization, and may carry a seat limit, a note, and a Stripe coupon (the beta
  price). A Platform Admin creates it; the invitee gets an email from the
  Scaleway sender and signs up with that address.
- A **typed promo code** is the weaker design for this purpose: a shared code
  leaks, cannot be tied to a person, and cannot carry a price. Stripe promotion
  codes belong to pricing, not to access. Keep `allow_promotion_codes` off.
- The gate is a mode (`invite` during the beta, `open` at general availability),
  so opening up later is one setting.
- Until the gate exists, do not publish the domain or send out any link, and treat
  every signup as a surprise; the gate is a **must** below.

## Pricing during the beta

Options, in order of preference for a beta that also tests willingness to pay:

1. **A founding-customer price**: for example 50 % off for six months through the
   invitation's coupon, card collected at signup. Real money validates the whole
   billing path, including the first renewal.
2. **A free period for friendly testers**: 100 % off for three months, card still
   collected, so the subscription converts without a second step.
3. **No card, free**: avoid. It skips the one thing the beta must prove (payment)
   and the subscription would fail at the first renewal.

Whatever is chosen, say it in the beta terms, and note the exception to ADR-0009
("no free trial") in ADR-0034.

## Readiness gates

### Must be done before the first invitation

| Gate | Why | Described in | Status |
| --- | --- | --- | --- |
| Product name, domain, and selling entity decided | Stripe, the email sender, the terms, and the invoices all name them | `launch-checklist.md` | Open |
| Production host, secrets, DNS, TLS, and Authentik administrator done and smoke-tested | Nothing else works without them | `production-readiness.md` sections 1, 2, and 5 | Open |
| **Invitation gate on Organization creation** | Otherwise anyone can create and pay for an Organization | ADR-0034, tech design ticket 01 | Open |
| **Automated, encrypted, off-host backups of both databases, with a freshness alert, and one restore to a new host rehearsed** | The beta holds customers' data on one host | database stance below, ticket 03 | Open |
| Container log rotation and an external uptime monitor with an alert that reaches a person | A full disk or a silent outage is the likeliest first incident | `docs/operations/monitoring.md`, ticket 04 | Open |
| Stripe live account configured and rehearsed (test clocks, live smoke test) | Real money | `stripe-production.md` | Open |
| Scaleway sending domain verified; an Invitation, a beta invitation, and an Authentik recovery email pass SPF, DKIM, and DMARC | Invitations are how people get in | `production-readiness.md` section 4 | Open |
| Beta terms, privacy policy, a processor agreement (DPA) template, and the sub-processor list published | Required by law and printed on Stripe receipts | legal section below | Open |
| A support address and a person who answers it | Beta users will need help in the first week | operating section below | Open |
| Rate limiting decided and in place at the edge | Listed as open in the security review | `docs/architecture/security-review.md`, ticket 05 | Open |
| Dependency audit (`pip-audit`, `npm audit`) clean or accepted | Listed as open in the security review | ticket 06 | Open |

### Should be done before or during the first week

- Finnish wording review of the interface and the emails by a native speaker
  (Finnish customers will see the product in Finnish, ADR-0016).
- A keyboard and screen-reader pass of the main journeys
  (`launch-checklist.md`, Accessibility).
- A production-like staging stack with Stripe in a sandbox, so billing changes are
  rehearsed away from customers.
- A deploy and rollback note: take a backup, deploy, check `/health`, and roll the
  images back if the check fails (`migrate` runs before `backend` and `worker`).
- Error tracking for the backend and the frontend, or at least a daily review of
  the failed jobs and the logs.
- A getting-started page per language (the end-user tutorial is the base) and an
  onboarding email for each invitee.
- Privacy-friendly analytics on the public site only; none in the application.

### Can wait until general availability

- Managed PostgreSQL, high availability, and point-in-time recovery.
- An external penetration test (needed before opening signups, not before an
  invited beta).
- SEPA Direct Debit and e-invoicing.
- The remaining roadmap packages (P6, P9, P10b, P12, P13).

## Database and backups

**Stance.** Keep PostgreSQL in its container on the single production host for the
invited beta, **provided the backups below exist and a restore has been
rehearsed**. Move to a managed PostgreSQL before opening signups or before the
beta customers carry business-critical plans, whichever comes first. A managed
database is not required to be responsible, but without backups the container is
not acceptable.

Why this is reasonable now: the data is small (a dump takes seconds), the user
count is limited, an export exists for customers, and the single host is already
the single point of failure for the whole stack, so a managed database alone would
not remove it.

What the container design must be made to do:

- **Backups.** `scripts/ops/backup-databases.sh` dumps the Yearclock and Authentik
  databases separately, but nothing schedules it or copies it off the host. Run it
  **hourly**, keep the last 24 hourly and 14 daily dumps on the host, and copy
  every dump, encrypted, to object storage in another region or provider
  (the operator chose Scaleway Object Storage; if the host is also at Scaleway, use a different region or a separate project so one account problem cannot remove both) with versioning or object
  lock so ransomware or a bad script cannot delete the history. Keep 30 daily and
  6 monthly copies off-host. Target: **recovery point of one hour, recovery time of
  half a day**; say so in the beta terms.
- **Encryption and the key.** Encrypt on the host before upload, so the storage
  never holds readable data and the key stays with the operator. Prefer one tool
  that does encryption, deduplication, retention, and an S3 backend together, such
  as restic (`restic forget --keep-hourly 24 --keep-daily 30 --keep-monthly 6`), or
  `age` with `rclone` if plain files are wanted. Use a bucket-scoped access key that
  can add objects but not remove them where the tool allows it, and enable object
  versioning or lock. Keep the encryption key and the repository password in the
  password manager and on paper elsewhere; without them the backups are useless.
- **Setup and rehearsal.** The scripts, timers, and step-by-step setup are in
  [`backup.md`](backup.md).
- **A dead-man's switch.** Failures are emailed through Scaleway Transactional Email
  and every success can be too, so a missing email is the alarm; for the hourly
  beta also use an external heartbeat service, whose missed ping pages a person. A silent backup failure is the
  failure that matters.
- **Authentik is part of it.** Losing its database means nobody can sign in, so
  its dump is as important as the application's. Also keep `.env.production`
  (especially `AUTHENTIK_SECRET_KEY`) in the password manager, outside the host.
- **Restore.** `scripts/ops/restore-drill.sh` restores each dump into a scratch
  database. Also rehearse the harder case once before launch and then quarterly:
  **a new empty host** (install Docker, restore the secrets, `docker compose up`
  the database, restore both dumps, start the stack, sign in, open a Yearclock, and
  check an invoice-affecting state). Time it and write the result next to this
  item.
- **Before every deploy** take a backup; migrations run automatically.
- **Hardening the container.** The database port is not published, volumes are
  named, the data volume is on a disk with provider snapshots enabled as a second
  layer, and disk use is watched (`MONITORING_DATABASE_MAX_BYTES`, plus a host disk
  alert). Write down the PostgreSQL major-version upgrade procedure before it is
  needed.
- **Later.** Continuous archiving (WAL shipping with a tool such as pgBackRest)
  gives point-in-time recovery if an hourly recovery point stops being enough.

Managed PostgreSQL needs a compatibility check first (ticket 08): Yearclock relies
on a non-owner application role without `BYPASSRLS`, forced row-level security,
`SET LOCAL ROLE`, two logical databases (Yearclock and Authentik) with separate
owners, and connection pools sized against `POSTGRES_MAX_CONNECTIONS`.

## Legal and privacy minimum

- [ ] **human** Draft texts for all of the following are in `backend/legal/` (status `draft`); counsel's checklist is `docs/legal/counsel-checklist.md`. Beta terms: business customers only; the beta promises above;
  data ownership and export; acceptable use; liability limits; the price and how
  it changes; the right to end the beta with notice; governing law.
- [ ] **human** Privacy policy (also required on Stripe receipts) and a processor
  agreement: Yearclock is a processor for the planning content customers enter, and
  a controller for account and billing data. List the sub-processors: Stripe,
  Scaleway (email), and the hosting provider.
- [ ] **human** Review the drafted records in `docs/gdpr/` (records of processing,
  breach procedure, DPIA and DPO note, staff rules), set up the private registers
  folder from `docs/gdpr/private-registers.md`, and decide the retention periods
  listed as open in `docs/gdpr/README.md`.
- [ ] **human** A short storage notice: the application sets only a strictly
  necessary session cookie and a few settings in the browser, so no consent banner
  is needed; keep it that way by adding no tracking to the application.
- [ ] **human** Name the person who answers data requests
  (`personal-data-request.md`) and the person who is told within 72 hours of a
  personal data breach.

## Operating the beta

- **Support.** One address (an alias to a person, not a personal mailbox), a
  response target during business days, and a place to log what was asked. Answer
  quickly in week one: the first impression is the product.
- **Incidents.** A short note: who decides, how customers are told (email to
  Owners), and where the timeline is written. After an incident write down what
  changed.
- **Changes.** Deploy outside business hours at first, tell the invitees about
  noticeable changes, and keep a changelog.
- **Watching.** Daily for the first two weeks: failed jobs and emails
  (`/platform/jobs`), the uptime monitor, disk use, Stripe's failed webhooks, and
  support mail. Then weekly.
- **Feedback.** A direct channel (a reply-to address and a short call after the
  first week) beats a form. Keep a list of what people ask for and map it to the
  roadmap.

## Success measures and leaving the beta

Write the measures down before the first invitation so the beta can end on
evidence:

- Invited organizations that create an Organization, invite a colleague, and add
  Events in the first week.
- Organizations still active in week four, and why the others stopped.
- At least one **real renewal** and one failed-then-recovered payment seen end to
  end.
- No data loss, no unrecovered incident, and three consecutive successful restore
  rehearsals.
- Support load per organization and the most common questions (they become
  documentation and product fixes).

General availability needs, in addition to the beta gates: managed PostgreSQL or a
justified decision to stay, an external penetration test, the accessibility and
Finnish reviews done, SEPA handled if wanted, the opened signup mode, and a decision
on the pricing model (P13).

## Open decisions

1. The product name, domain, and selling entity.
2. The access mechanism (an email-bound Beta Invitation, as proposed in ADR-0034).
3. The beta price (section on pricing).
4. Container PostgreSQL with hourly off-host backups for the beta, and the managed
   database as a gate for general availability.
5. Where the off-host copies live and who holds the encryption key.
6. Who answers support and who is on call.
7. The rate-limiting approach (Caddy module, a provider firewall, or a CDN in
   front).
