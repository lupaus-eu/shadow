# Customer Concept

Status: persistence baseline defined; backend API and frontend UI pending

## Purpose

Customer tarkoittaa asiakasta tai asiakasorganisaatiota, johon järjestelmän
muut tiedot voivat liittyä.

Customer ei tarkoita laskua, tilausta, yhteyshenkilöä tai käyttäjätiliä.
Contact ja Customer Address ovat Customer-käsitteen omistamia alikäsitteitä,
ja ne määritellään tässä samassa dokumentissa.

---

# Owner

Owning Domain:

- Customer Domain

Related Domain Document:

- `docs/domains/CUSTOMER.md`

Owned Tables:

- `customers`
- `contacts`
- `customer_addresses`

---

# Customer

## Definition

```text
A Customer is the primary business entity representing an organization or person that the system serves or tracks.
```

## Key Fields

- `customer_id`: internal bigint identity
- `name`: required customer display name
- `email`: optional general customer email address
- `status`: `active`, `archived` or `deleted`
- `created_by`, `created_time`
- `modified_by`, `modified_time`
- `deleted_by`, `deleted_time`

## Invariants

- Customer must always have `customer_id`.
- Customer must always have a non-blank `name`.
- Customer starts in `active` status.
- `deleted_time` is present exactly when status is `deleted`.
- Customer names and email addresses are not unique.
- Customer deletion is a soft delete.
- A deleted Customer is excluded from normal application reads.
- Other domains may reference Customer but may not modify Customer-owned tables
  directly.

## Lifecycle

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

`deleted` is terminal in this baseline. Customer merge, restore and permanent
deletion are not defined.

Archived customers remain visible and editable, including their active
contacts and addresses.

---

# Contact

## Definition

```text
A Contact is a customer-owned person or contact channel used to communicate with that Customer.
```

## Key Fields

- `contact_id`: internal bigint identity
- `customer_id`: required owning Customer
- `name`: required contact display name
- `email`: optional email address
- `phone`: optional phone number
- `job_title`: optional role or job title
- `created_by`, `created_time`
- `modified_by`, `modified_time`
- `deleted_by`, `deleted_time`

## Invariants

- Contact must always have `contact_id`.
- Contact must reference exactly one Customer.
- Contact must always have a non-blank `name`.
- Contact names are not unique within or across customers.
- Contact deletion is a soft delete through `deleted_time`.
- A deleted Contact is excluded from normal application reads.
- Contact has no archive state and no restore lifecycle in this baseline.

## Lifecycle

```text
active -> deleted
```

The active state is represented by `deleted_time IS NULL`; Contact has no
separate status column.

---

# Customer Address

## Definition

```text
A Customer Address is a labelled postal or visiting address owned by one Customer.
```

## Key Fields

- `customer_address_id`: internal bigint identity
- `customer_id`: required owning Customer
- `label`: required address label, for example `Billing` or `Visiting`
- `address_line_1`: required primary address line
- `address_line_2`: optional secondary address line
- `postal_code`: optional postal code
- `city`: optional city or locality
- `region`: optional state, province or region
- `country_code`: required two-letter uppercase ASCII country code
- `created_by`, `created_time`
- `modified_by`, `modified_time`
- `deleted_by`, `deleted_time`

## Invariants

- Customer Address must always have `customer_address_id`.
- Customer Address must reference exactly one Customer.
- `label` and `address_line_1` must be non-blank.
- `country_code` must contain exactly two uppercase ASCII letters.
- Address labels are not unique within or across customers.
- Customer Address deletion is a soft delete through `deleted_time`.
- A deleted Customer Address is excluded from normal application reads.
- Customer Address has no archive state and no restore lifecycle in this
  baseline.

## Lifecycle

```text
active -> deleted
```

The active state is represented by `deleted_time IS NULL`; Customer Address has
no separate status column.

---

# Normalization And Validation

- The database enforces required fields, non-blank Customer/Contact names,
  non-blank address label and first line, Customer status/deletion consistency,
  and country-code shape.
- The trusted backend service trims required and optional text before
  persistence.
- The trusted backend service normalizes blank optional values to `NULL`.
- Email format and length validation belongs to the trusted backend service.
- Country codes are normalized to uppercase by the trusted backend service.
- Backend validation and normalization are implemented in TASK-036B; frontend
  validation is only a user-experience aid.

---

# Relationship And Deletion Rules

- One Customer owns zero or more Contacts.
- One Customer owns zero or more Customer Addresses.
- Contacts and Customer Addresses cannot exist without their owning Customer.
- Normal Customer deletion must soft-delete the Customer and all of its active
  Contacts and Customer Addresses atomically in the Customer Domain service.
- Physical foreign-key cascades exist only for hard-delete cleanup/safety and
  are not the normal application deletion flow.
- Billing, Document and AI domains may reference Customer data but may not
  modify Customer-owned tables directly.

Related Concepts:

- Invoice
- Document
- AI Extraction

---

# Related APIs

The Customer Domain owns the following API direction. Backend routes are
implemented in TASK-036B.

```text
/api/v1/customers
/api/v1/customers/{customer_id}
/api/v1/customers/{customer_id}/contacts
/api/v1/customers/{customer_id}/contacts/{contact_id}
/api/v1/customers/{customer_id}/addresses
/api/v1/customers/{customer_id}/addresses/{address_id}
```

---

# AI Agent Guidance

When implementing Customer features:

- read `docs/domains/CUSTOMER.md`
- keep Customer, Contact and Customer Address definitions in this document
- preserve all soft-delete behavior
- enforce child ownership through the Customer Domain boundary
- do not add uniqueness rules that are not documented here
- do not modify billing tables directly
- do not modify document lifecycle directly
- do not create AuditEvent records until a shared audit-event model is approved

---

# Open Questions

- customer merge workflow
- customer restore policy
- permanent deletion policy
- AuditEvent ownership and writing workflow
