# Launch checklist

Decisions and credentials required before the first production customer. Keep
the values themselves outside git; record here only the decision, the owner,
and the date.

| Item | Decision needed | Owner | Status |
| --- | --- | --- | --- |
| Product name and domains | App domain (`YEARCLOCK_SITE_ADDRESS`) and identity domain (`YEARCLOCK_IDENTITY_ADDRESS`); `yearclock.example.com` is a placeholder. | Product owner | Open |
| Legal retention | Statutory retention for Billing Records, the purged Organization row (name and billing contact), audit events, and outbox messages (`docs/gdpr/README.md`; the decisions for counsel are in `docs/legal/counsel-checklist.md`). | Legal | Open |
| Tax | Stripe Tax registrations or manual rates, and the invoice legal entity. | Finance | Open |
| Stripe | Live account, Product/Price, webhook secret, Customer Portal settings (cancellation on, update quantities off; for P14 the secret key must be allowed to update subscriptions, release subscription schedules, create Checkout sessions for existing customers, and update customers; a Stripe test-mode run of cancel, resubscribe, and contact change); key owner and rotation schedule. | Finance / operator | Open |
| Beta access | Accept ADR-0034: signup mode `invite`, email-bound Beta Invitations, no typed promo codes, the beta price and its coupon (`beta-launch.md`). | Product owner | Open |
| Authentik | Production administrator, break-glass holder, MFA policy review. | Operator | Open |
| Scaleway | Account, IAM application, verified sending domain, DNS owner. | Operator | Open |
| Hosting | Host, backups destination and encryption key holder, monitoring service and on-call contact; hourly encrypted off-host backups with a heartbeat alert and a restore to a new host rehearsed; the managed PostgreSQL decision (`beta-launch.md`, ticket 08 of `.scratch/tech-beta-launch/`). | Operator | Open |
| Legal documents | Draft texts exist in `backend/legal/` (published as `draft`, hidden in production); counsel works through [`docs/legal/counsel-checklist.md`](../legal/counsel-checklist.md) and sets them to `published`. Beta terms (business customers only, no SLA, a one-hour recovery point), privacy policy (also printed on Stripe receipts), processor agreement template, and the sub-processor list (Stripe, Scaleway, the host). | Legal | Open |
| Support | A support address, a named person, a response target, and an incident note (`beta-launch.md`). | Product owner | Open |
| GDPR | Records of processing (drafted in `docs/gdpr/records-of-processing.md`, with the breach procedure, DPIA and DPO note, staff rules, and private-register templates beside it), DPAs with Stripe and Scaleway, data-subject request process (engineering procedure in `personal-data-request.md`; legal review of its wording is open; the P8 notifications and the opt-in Summary are listed in the records of processing, and the Summary is the one message that carries Event titles). | Legal | Open |
| Accessibility | Manual screen-reader and keyboard review in Finnish and English (NVDA or JAWS, and VoiceOver), including the V2 Filters panel, Label picker, search, the P1 time-scale rings, Lane tints, and centre preview, the P3 selection mode, season preview, and roll-up Yearclocks, the P4 History, restore preview, change marks, and change notice, and the P10a Groups panel, access sources, and bulk invitation preview, and the P5 displays (timeline, list, and agenda), the P7 print layout, export and import dialogs, and Organization Export card, and the P8 bell, notification inbox, and settings, the P14 Subscription card, ownership dialogs, and billing contact form, the P11 links editor, description toolbar, and time fields, and the redesigned interface (sidebar and navigation drawer, account menu, planner panel tabs, Event drawer, confirmation dialogs, and toasts). | Product owner | Open |
| Finnish wording | Native-speaker review of the Finnish interface texts, including Yearclock V2 (Classification, Labels, Filters, search, Layout and Planning Window length, P3 planning tools and Linked Lanes, P4 history and change awareness, P10a Groups, sharing, and invitations, and the P5 display names and column headings, the P7 export and import texts and error messages, the P8 notification, email, and Summary texts, the P14 subscription and ownership texts and emails, the P11 Event field labels and import messages, and the interface redesign: shell, administration pages, planner tabs, Yearclock settings, and the operator console). | Product owner | Open |
| Security | External penetration test, dependency audit, rate-limiting decision (`docs/architecture/security-review.md`). | Operator | Open |
| Capacity | Repeat the dense-Yearclock load check on production hardware and confirm the ceilings (`docs/architecture/operational-limits.md`). | Operator | Open |

Then work through `docs/runbooks/production-readiness.md` and
`docs/runbooks/v1-acceptance.md`. For the first release, an internal alpha for the corporate group, start with
`docs/runbooks/alpha-launch.md`; for the invited beta use
`docs/runbooks/beta-launch.md`; Stripe is covered in
`docs/runbooks/stripe-production.md`.
