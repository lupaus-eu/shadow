# Invoice Concept

Status: initial candidate concept

## Purpose

Invoice tarkoittaa laskutettavaa tai laskutettua kokonaisuutta, joka viittaa asiakkaaseen.

Invoice ei tarkoita asiakasprofiilia, maksutapahtumaa yksinään tai tilaussopimusta.

---

# Owner

Owning Domain:

- Billing Domain

Related Domain Document:

- `docs/architecture/domains/BILLING.md`

---

# Definition

```text
An Invoice is a billing document containing one or more invoice lines and a payment state.
```

---

# Key Fields

- id
- customer_id
- invoice_number
- status
- total_amount
- currency
- created_at
- updated_at

---

# Invariants

- Invoice must reference a Customer.
- Invoice must have at least one invoice line before it can be issued.
- Paid invoices are not physically deleted.

---

# Lifecycle

States:

- draft
- issued
- paid
- cancelled

Transitions:

```text
draft -> issued
issued -> paid
issued -> cancelled
```

---

# Relationships

Related Concepts:

- Customer

Related Tables:

- invoices
- invoice_lines
- payments

Related APIs:

- `/invoices`
- `/payments`

---

# Domain Rules

- Billing Domain owns invoice state.
- Customer Domain owns customer profile data.
- Payment provider details must be isolated from unrelated domains.

---

# AI Agent Guidance

When implementing Invoice features:

- read `docs/architecture/domains/BILLING.md`
- do not modify Customer-owned tables directly
- create a separate Customer task if customer profile data must change

---

# Open Questions

- invoice numbering strategy
- credit note model
