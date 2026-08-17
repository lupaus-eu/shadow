# Customer Domain

Status: persistence baseline, backend API and frontend management UI implemented

## Purpose

Customer Domain hallitsee asiakasprofiileja, asiakaskontakteja ja
asiakasosoitteita. Domain toimii järjestelmän source of truth -kerroksena
asiakasdatalle.

---

# Responsibilities

Owns:

- customer profile and lifecycle
- customer contacts
- customer addresses
- customer lookup and search rules
- customer metadata

Does NOT Own:

- invoices
- payments
- subscriptions
- document lifecycle
- AI-generated classifications
- application users
- a shared AuditEvent model

---

# Domain Rules

## Customer

- Customer has an internal id and a non-blank name.
- Email is optional.
- Customer status is `active`, `archived` or `deleted`.
- New customers start as active.
- Active and archived customers are normal readable records.
- Archived customers and their contacts and addresses remain editable.
- Deleted customers are excluded from normal reads.
- Deletion is a soft delete and `deleted` is terminal in this baseline.
- Names and email addresses are not unique.

## Contacts

- A Contact belongs to exactly one Customer.
- Contact name is required and non-blank.
- Email, phone and job title are optional.
- Contacts use `deleted_time` soft deletion and have no status column, archive
  state or restore lifecycle.
- Contact names are not unique.

## Customer Addresses

- A Customer Address belongs to exactly one Customer.
- Label, first address line and two-letter uppercase country code are required.
- Second address line, postal code, city and region are optional.
- Customer Addresses use `deleted_time` soft deletion and have no status
  column, archive state or restore lifecycle.
- Address labels are not unique.

## Normalization

- Backend services trim required and optional text.
- Backend services reject blank required fields and normalize blank optional
  fields to `NULL`.
- Backend services validate email values and normalize country codes to
  uppercase.
- Database constraints remain the final persistence safeguard for documented
  invariants.

## Deletion

- Normal Customer deletion atomically soft-deletes the Customer and all active
  Contacts and Customer Addresses through the Customer Domain service.
- Physical `ON DELETE CASCADE` foreign keys are hard-delete cleanup/safety only.
- No database trigger performs application soft-delete propagation.

## Authorization And Audit Actors

Every Customer API requires an active application session and every unsafe
request requires the common exact-Origin and session-CSRF guard. Both current
roles may manage every application-wide Customer; Customer has no organisation
membership or ownership rule in this internal-tool baseline.

Authenticated creates set `created_by`; replacements set `modified_by`; soft
deletes set `modified_by` and `deleted_by`. Customer deletion propagates the
same actor to all soft-deleted Contacts and Customer Addresses. Historical
nullable audit values remain unchanged.

---

# Database Ownership

Tables owned exclusively by Customer Domain:

- `customers`
- `contacts`
- `customer_addresses`

Other domains may reference these tables by foreign key or through a Customer
Domain API/service boundary, but they may not modify them directly.

---

# API Ownership

Nested Customer Domain API direction:

```text
GET    /customers
GET    /customers/{customer_id}
POST   /customers
PUT    /customers/{customer_id}
DELETE /customers/{customer_id}

GET    /customers/{customer_id}/contacts
POST   /customers/{customer_id}/contacts
PUT    /customers/{customer_id}/contacts/{contact_id}
DELETE /customers/{customer_id}/contacts/{contact_id}

GET    /customers/{customer_id}/addresses
POST   /customers/{customer_id}/addresses
PUT    /customers/{customer_id}/addresses/{address_id}
DELETE /customers/{customer_id}/addresses/{address_id}
```

The versioned FastAPI routes were implemented in TASK-036B. Nested paths make
Customer ownership explicit and require the child resource to belong to the
Customer in the route.

---

# Dependencies

Depends On:

- Users Domain for nullable audit-user references

Referenced By:

- Billing Domain
- Document Domain
- AI Domain

---

# Common Workflows

## Create Customer

1. Validate and normalize the request.
2. Create an active Customer.
3. Return the Customer.

## Update Or Archive Customer

1. Validate and normalize the request.
2. Load an active or archived Customer.
3. Apply the profile and lifecycle changes.
4. Update modification metadata.
5. Return the Customer.

## Delete Customer

1. Load an active or archived Customer.
2. Use one deletion timestamp for the Customer and all active child records.
3. Soft-delete active Contacts and Customer Addresses.
4. Mark the Customer deleted.
5. Commit the complete change atomically.

## Manage Contact Or Address

1. Load an active or archived owning Customer.
2. Validate and normalize the request.
3. For updates and deletes, verify that the child belongs to the Customer.
4. Create, replace or soft-delete the child record.

AuditEvent creation is deferred until a shared audit-event model, ownership and
writing workflow are approved.

---

# AI Agent Guidance

Preferred locations:

- `backend/app/api/v1/customers/`
- `frontend/src/features/customers/`
- `frontend/src/api/customers.ts`

Avoid:

- modifying billing tables
- modifying invoice logic
- modifying document lifecycle logic
- modifying AI extraction logic
- bypassing nested child ownership checks
- adding customer/contact/address uniqueness rules
- physically deleting Customer Domain rows in normal flows

If a change affects invoices, documents or AI output lifecycles, create a
separate task for the owning domain.

---

# Open Questions

- customer merge workflow
- customer restore and permanent-deletion policy
- shared AuditEvent ownership and writing workflow
