# Checklist for counsel

The drafts in [`backend/legal/`](../../backend/legal/) were prepared by the product team from the repository's
documentation. They are not legal advice and nothing in them is in force. Every place that needs a decision or
wording is marked `TODO(lawyer)`; find them all with:

```bash
grep -rn "TODO(lawyer)" backend/legal
```

The lists below collect what counsel must confirm before any document is set to `status: published`
(see [README.md](README.md)). Items marked **verify** rest on secondary sources in
`.scratch/yearclock-v2-legal-documents/research.md`.

## Facts the operator supplies

- [ ] VAT ID and registered address (`provider`). Known: Lupaus Palvelut Oy, business ID 2355166-5, registered office Helsinki.
- [ ] The monitored support address and the legal and privacy contact (`LEGAL_CONTACT_EMAIL`).
- [ ] The price, any beta price, and the notice period for changes (30 days, with a right to object, was decided).
- [ ] The real hosting location (UpCloud), the Scaleway regions for email and backups, and the signed agreements with
  Stripe, Scaleway, and UpCloud (`subprocessors`, `dpa`).

## Decisions and wording for counsel

- [ ] Terms: authority and exclusion of consumers, acceptable use, liability, force majeure, termination, court and venue,
  the effect of an objection to a change, the beta wording (`terms`).
- [ ] DPA: the Article 28(3) wording, instructions that conflict with the law, staff confidentiality undertakings, breach
  notification time, audit scope, handling of special categories, what happens at the end of a subscription (`dpa`).
- [ ] Privacy notice: legal basis per purpose, the retention of audit events, queued email, billing identity, and
  acceptance records (including the e-mail snapshot kept with each acceptance), transfers outside the EU and EEA, whether
  a data protection officer is needed (`privacy`).
- [ ] **verify** Switching terms under the EU Data Act (Regulation 2023/2854, Chapter VI, Article 25): notice, transition,
  charges, and information duties; the phase-out of switching charges (`switching`).
- [ ] **verify** Browser storage under section 205 of the Finnish Act on Electronic Communications Services and the Data
  Protection Ombudsman's current guidance; the identity provider's cookie names (`storage`).
- [ ] How to describe the open security items (penetration test, dependency audit, edge rate limiting) and the recovery
  point and time to commit to (`security`).
- [ ] **verify** The Finnish provision on provider identification and invoice content (`provider`).
- [ ] **verify** Statutory accounting retention period for Billing Records.
- [ ] **verify** NIS2 (Finnish Cybersecurity Act 124/2025): whether the provider is in scope by size, and the registration duty.
- [ ] **verify** Whether an accessibility statement is required (European Accessibility Act; business-only SaaS and
  microenterprise exemptions) and whether the AI Act creates any duty (connected agents are the user's choice).

## After counsel

- [ ] Replace each draft text, raise nothing else than the content, set `status: published` in both languages, and
  release as described in [`docs/operations/README.md`](../operations/README.md#legal-documents).
- [ ] Set the privacy and terms URLs in Stripe ([`stripe-production.md`](../runbooks/stripe-production.md)) and the
  footer links in Authentik ([`authentik-local.md`](../runbooks/authentik-local.md)).
