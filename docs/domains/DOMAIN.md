# Domain Overview

Tämä dokumentti kuvaa järjestelmän domainit ja niiden omistajuudet.

Status: initial candidate domain map

Tavoite:

- auttaa kehittäjiä
- auttaa AI-agentteja
- määritellä domain boundaryt
- selkeyttää datan ja APIen omistajuutta

Kun domain-malli muuttuu, päivitä tämä tiedosto ja relevantti domain-kohtainen dokumentti.

---

# Domain Documentation Rules

Jokaisella domainilla tulee olla oma tarkentava dokumentti:

```text
docs/domains/CUSTOMER.md
docs/domains/BILLING.md
docs/domains/DOCUMENT.md
docs/domains/AI.md
```

Uuden domainin dokumentti luodaan mallista:

```text
docs/domains/DOMAIN-TEMPLATE.md
```

AI-agentin tulee lukea domain-dokumentti ennen muutoksia, jotka koskevat:

- domainin omistamia tauluja
- domainin APIeja
- domainin sääntöjä
- domainien välisiä riippuvuuksia

---

# Customer Domain

Responsible for:

- customer profiles
- contacts
- addresses
- customer lifecycle

Owns:

- customers
- contacts
- customer_addresses

Does NOT Own:

- invoices
- payments
- subscriptions

Depends On:

- None

Primary APIs:

- `/customers`
- `/contacts`

Related Documents:

- `docs/domains/CUSTOMER.md`

---

# Billing Domain

Responsible for:

- invoices
- invoice lines
- payments
- subscriptions

Owns:

- invoices
- invoice_lines
- payments
- subscriptions

Does NOT Own:

- customer profile data

Depends On:

- Customer Domain

Primary APIs:

- `/invoices`
- `/payments`

Related Documents:

- `docs/domains/BILLING.md`

---

# Document Domain

Responsible for:

- uploaded documents
- document metadata
- document lifecycle

Owns:

- documents
- document_versions

Does NOT Own:

- customer data
- billing data

Depends On:

- Customer Domain

Primary APIs:

- `/documents`

Related Documents:

- `docs/domains/DOCUMENT.md`

---

# AI Domain

Responsible for:

- AI classifications
- AI summaries
- AI extractions

Owns:

- ai_classifications
- ai_summaries
- ai_extractions

Does NOT Own:

- customer data
- document data
- billing data

Depends On:

- Customer Domain
- Document Domain

Primary APIs:

- `/ai/classify`
- `/ai/extract`
- `/ai/summarize`

Related Documents:

- `docs/domains/AI.md`
