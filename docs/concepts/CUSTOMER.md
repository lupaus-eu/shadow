# Customer Concept

Status: initial candidate concept

## Purpose

Customer tarkoittaa asiakasta tai asiakasorganisaatiota, johon järjestelmän muut tiedot voivat liittyä.

Customer ei tarkoita laskua, tilausta, yhteyshenkilöä tai käyttäjätiliä.

---

# Owner

Owning Domain:

- Customer Domain

Related Domain Document:

- `docs/domains/CUSTOMER.md`

---

# Definition

```text
A Customer is the primary business entity representing an organization or person that the system serves or tracks.
```

---

# Key Fields

- id
- name
- email
- status
- created_at
- updated_at
- deleted_at

---

# Invariants

- Customer must always have `id`.
- Customer must always have `name`.
- Customer deletion is soft delete.

---

# Lifecycle

States:

- active
- archived
- deleted

Transitions:

```text
active -> archived
archived -> active
active -> deleted
archived -> deleted
```

---

# Relationships

Related Concepts:

- Invoice
- Document
- AI Extraction

Related Tables:

- customers
- contacts
- customer_addresses

Related APIs:

- `/customers`
- `/contacts`

---

# Domain Rules

- Email is optional.
- Customer records are not physically removed.
- Other domains may reference Customer but may not modify Customer-owned tables directly.

---

# AI Agent Guidance

When implementing Customer features:

- read `docs/domains/CUSTOMER.md`
- preserve soft delete behavior
- do not modify billing tables directly
- do not modify document lifecycle directly

---

# Open Questions

- customer merge workflow
- customer archival policy
