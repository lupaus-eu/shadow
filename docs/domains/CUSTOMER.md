# Customer Domain

Status: initial candidate domain

## Purpose

Customer Domain hallitsee kaikkea asiakkuuteen liittyvää tietoa.

Tämä domain toimii järjestelmän source of truth -kerroksena asiakasdatalle.

---

# Responsibilities

Owns:

- customer profile
- customer contacts
- customer addresses

Provides:

- customer lookup
- customer search
- customer metadata

Does NOT Own:

- invoices
- payments
- subscriptions
- document lifecycle
- AI-generated classifications

---

# Domain Rules

## Rule 1

Customer must always have:

- id
- name

## Rule 2

Email is optional.

## Rule 3

Customer deletion is soft delete.

Customers are never physically removed.

---

# Database Ownership

Tables:

- customers
- contacts
- customer_addresses

Owned exclusively by Customer Domain.

Other domains may reference these tables but may not modify them directly.

---

# API Ownership

Endpoints:

```text
GET /customers
POST /customers
PUT /customers/{id}
GET /contacts
POST /contacts
```

---

# Dependencies

Depends On:

- None

Referenced By:

- Billing Domain
- Document Domain
- AI Domain

---

# Common Workflows

## Create Customer

Flow:

1. Validate request
2. Create customer
3. Create audit event
4. Return customer

## Update Customer

Flow:

1. Validate request
2. Load customer
3. Apply changes
4. Create audit event

---

# AI Agent Guidance

When implementing customer features:

Preferred locations:

- backend/customer/*
- frontend/customer/*

Avoid:

- modifying billing tables
- modifying invoice logic
- modifying document lifecycle logic
- modifying AI extraction logic

If a change affects invoices:

- create a separate Billing task

---

# Open Questions

- customer merge workflow
- customer archival policy
