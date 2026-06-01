# Billing Domain

Status: initial candidate domain

## Purpose

Billing Domain hallitsee laskutukseen, maksuihin ja tilauksiin liittyvää tietoa.

Customer Domain omistaa asiakasprofiilin. Billing Domain saa viitata asiakkaaseen, mutta ei muokkaa asiakasprofiilidataa suoraan.

---

# Responsibilities

Owns:

- invoices
- invoice lines
- payments
- subscriptions

Provides:

- invoice creation
- payment tracking
- subscription state
- billing history

Does NOT Own:

- customer profile data
- customer contact data
- uploaded documents
- AI-generated classifications

---

# Domain Rules

## Rule 1

Invoice must reference a customer.

## Rule 2

Invoice lines belong to exactly one invoice.

## Rule 3

Paid invoices are not deleted. Corrections are handled with credit notes or explicit adjustment records.

---

# Database Ownership

Tables:

- invoices
- invoice_lines
- payments
- subscriptions

Owned exclusively by Billing Domain.

Other domains may reference billing records but may not modify them directly.

---

# API Ownership

Endpoints:

```text
GET /invoices
POST /invoices
GET /invoices/{id}
GET /payments
POST /payments
```

---

# Dependencies

Depends On:

- Customer Domain

Referenced By:

- None

---

# Common Workflows

## Create Invoice

Flow:

1. Validate request
2. Load customer reference
3. Create invoice
4. Create invoice lines
5. Create audit event
6. Return invoice

## Record Payment

Flow:

1. Validate request
2. Load invoice
3. Record payment
4. Update invoice payment state
5. Create audit event

---

# AI Agent Guidance

When implementing billing features:

Preferred locations:

- backend/billing/*
- frontend/billing/*

Avoid:

- modifying customer profile tables
- modifying document lifecycle logic
- embedding payment provider calls directly in unrelated domains

If a change affects customer data:

- create a separate Customer task

---

# Open Questions

- billing provider strategy
- credit note model
- subscription lifecycle
