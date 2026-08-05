# TASK-036B Customer Backend API

Status: Implemented

## Source Plan

Approved plan: implement Customer Domain backend APIs after TASK-036A has
defined and migrated the Customer, Contact and Customer Address persistence
model. The API provides customer lookup, search and lifecycle operations plus
nested contact and address management.

## Goal

Implement a trusted FastAPI service boundary for customer profiles, contacts
and customer addresses. The API must enforce validation, parent ownership and
soft-delete behavior while keeping route handlers thin and database operations
inside the Customer Domain service.

Customer deletion must soft-delete the customer and all active child records in
one transaction. Normal reads must never expose soft-deleted records.

## Requirements

- Depend on the completed schema, models and documented rules from TASK-036A.
- Add Pydantic request and response schemas inheriting from `StrictBaseModel`.
- Use `Field` declarations and validators consistently with existing backend
  API modules.
- Add Customer Domain service logic under `backend/app/api/v1/customers/`.
- Keep route handlers thin and register the Customer router under `/api/v1`.
- Implement customer endpoints:
  - `GET /api/v1/customers`
  - `GET /api/v1/customers/{customer_id}`
  - `POST /api/v1/customers`
  - `PUT /api/v1/customers/{customer_id}`
  - `DELETE /api/v1/customers/{customer_id}`
- `GET /api/v1/customers` must:
  - return active and archived customers by default
  - exclude deleted customers
  - support an optional case-insensitive `q` search over name and email
  - support an optional `status=active|archived` filter
  - return deterministic case-insensitive name order with customer id as the
    tie-breaker
- Customer creation accepts a required name and optional email and always
  creates an `active` customer.
- Customer replacement uses `PUT` and accepts the complete editable profile:
  name, email and status. Only `active` and `archived` are accepted from API
  callers.
- Customer deletion accepts both active and archived customers, sets status to
  `deleted`, sets customer deletion/modification timestamps and soft-deletes
  every active contact and address in the same transaction.
- Implement contact endpoints:
  - `GET /api/v1/customers/{customer_id}/contacts`
  - `POST /api/v1/customers/{customer_id}/contacts`
  - `PUT /api/v1/customers/{customer_id}/contacts/{contact_id}`
  - `DELETE /api/v1/customers/{customer_id}/contacts/{contact_id}`
- Contact create and replacement support required name and optional email,
  phone and job title.
- Return contacts in deterministic case-insensitive name order with contact id
  as the tie-breaker.
- Implement address endpoints:
  - `GET /api/v1/customers/{customer_id}/addresses`
  - `POST /api/v1/customers/{customer_id}/addresses`
  - `PUT /api/v1/customers/{customer_id}/addresses/{address_id}`
  - `DELETE /api/v1/customers/{customer_id}/addresses/{address_id}`
- Address create and replacement support required label, address line 1 and
  country code plus optional address line 2, postal code, city and region.
- Return addresses in deterministic case-insensitive label order with address
  id as the tie-breaker.
- Every nested endpoint must require an active or archived parent customer.
- A nested contact or address id must belong to the customer in the route;
  missing, deleted or cross-customer resources return `404` without exposing
  another customer's data.
- Normal list/get operations exclude soft-deleted customers, contacts and
  addresses.
- Contact and address deletion sets their deletion and modification timestamps
  and returns `204`; it does not physically delete rows.
- Trim required text before persistence and reject blank required values.
- Trim optional text and normalize omitted, empty or whitespace-only optional
  values to `NULL`.
- Validate optional email values conservatively for length and basic shape
  without adding an email-validation dependency.
- Normalize address country codes to uppercase and require exactly two ASCII
  letters; do not introduce a country-reference dependency or catalog.
- Do not add name, email or label uniqueness behavior.
- Keep audit user foreign keys nullable until authentication is implemented.
- Expose frontend-compatible response DTOs:
  - customer: `id`, `name`, `email`, `status`, `createdAt`, `updatedAt`
  - contact: `id`, `name`, `email`, `phone`, `jobTitle`, `createdAt`, `updatedAt`
  - address: `id`, `label`, `addressLine1`, `addressLine2`, `postalCode`,
    `city`, `region`, `countryCode`, `createdAt`, `updatedAt`
- Use the existing FastAPI/Pydantic error behavior and return `404` for missing
  domain resources. Do not introduce a repository-wide error-format change.
- Keep commits transactional and roll back failed customer/child mutations.
- Do not create AuditEvent records. The shared audit-event subsystem remains a
  separately planned concern.

## Acceptance Criteria

- [x] The Customer router is registered under `/api/v1` and exposes every
      customer, contact and address endpoint in this task.
- [x] Routes delegate business and persistence logic to the Customer Domain
      service.
- [x] Customer list/search/filter behavior is deterministic and excludes
      deleted rows.
- [x] Customer create trims input and always creates an active customer.
- [x] Customer PUT supports active-to-archived and archived-to-active
      transitions and rejects `deleted` as caller-controlled status.
- [x] Customer DELETE soft-deletes the customer, contacts and addresses in one
      transaction and returns `204`.
- [x] Contact and address CRUD enforce parent existence and route ownership.
- [x] Cross-customer child ids return `404` and cannot be read or mutated.
- [x] Contact and address DELETE operations are soft deletes and deleted rows
      disappear from normal reads.
- [x] Required values are trimmed and blank values are rejected.
- [x] Optional blank values become `NULL`, email shape is validated and country
      codes are normalized and validated without a new dependency.
- [x] Response payloads match the documented frontend DTOs and timestamps are
      serialized consistently.
- [x] Mutation timestamps are updated and failed multi-row operations roll back
      without partial deletion.
- [x] No authentication, authorization, organisation scoping, AuditEvent or
      uniqueness behavior is introduced.
- [x] Backend API tests, lint and type checking pass.
- [x] Migration/model tests from TASK-036A continue to pass.

## Out Of Scope

- Database migrations or changes to the approved TASK-036A schema except a
  separately approved corrective migration.
- Frontend API clients or Customer tab UI.
- Customer merge, restore or permanent deletion.
- Restoring contacts or addresses.
- Organisation-specific customer ownership.
- Authentication, authorization, roles or Entra ID mapping.
- Billing, Document or AI Domain integration.
- A shared AuditEvent model or audit-event creation.
- Advanced fuzzy search, pagination or full-text search infrastructure.
- New dependencies or repository-wide API error refactoring.

## Implementation Notes

- Read `AGENTS.md`, `ARCHITECTURE.md`,
  `docs/decisions/ADR-001-tech-stack.md`,
  `tasks/TASK-036A-customer-domain-schema.md`,
  `docs/concepts/CUSTOMER.md`, `docs/domains/CUSTOMER.md`,
  `docs/data/DATA-MODEL.md`, `docs/data/DATABASE.md`, `docs/TESTING.md` and
  this task before implementation.
- This task depends on TASK-036A. Do not re-decide fields or persistence rules
  in the API implementation.
- Expected backend locations are:
  - `backend/app/api/v1/customers/__init__.py`
  - `backend/app/api/v1/customers/models.py`
  - `backend/app/api/v1/customers/schemas.py`
  - `backend/app/api/v1/customers/service.py`
  - `backend/app/api/v1/customers/router.py`
  - `backend/app/api/v1/router.py`
  - a focused backend API test file
- Use SQLAlchemy ORM queries and parameterized expressions. Frontend validation
  added later is not a trusted boundary.
- Prefer helper functions for loading an active-or-archived parent and for
  checking nested-resource ownership so every endpoint applies the same rules.
- Customer delete should use one timestamp for the customer and all children
  and should commit only after every row has been updated.
- `PUT` is intentional for Customer Domain replacement operations and matches
  the approved plan; do not silently substitute `PATCH`.
- No ADR is expected. Stop and request a decision if implementation would
  require a new integration, dependency or domain ownership change.

## Testing

Required:

- [x] Backend unit tests for schema normalization and validation
- [x] Backend API integration tests for customer CRUD, search and lifecycle
- [x] Backend API integration tests for contact CRUD and ownership
- [x] Backend API integration tests for address CRUD and ownership
- [x] Transactional soft-delete propagation and rollback tests
- [x] Failure-path and invalid-input tests
- [x] Backend lint
- [x] Backend type checking

Not applicable:

- [x] Frontend tests and build: frontend implementation belongs to TASK-036C.
- [x] Browser automation: this task exposes backend behavior only.
- [x] New migration verification: TASK-036A owns migrations unless this task
      receives approval for a corrective migration.

Backend automated coverage must include:

- create/list/get/update/delete for customers
- active and archived listing and filtering
- case-insensitive name/email search
- blank name, invalid status and malformed email rejection
- active-to-archived and archived-to-active transitions
- exclusion and `404` behavior for deleted customers
- contact and address normalization, sorting and CRUD
- missing and deleted parent behavior
- cross-customer contact and address id rejection
- child soft deletion and repeat-access `404` behavior
- atomic customer/child soft deletion
- rollback when a child update in the delete transaction fails
- modified/deleted timestamp behavior
- rejection of unexpected request fields through `StrictBaseModel`

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Manual API verification should cover representative customer, contact and
address flows against local PostgreSQL after migrations 001 through 008 have
been applied. Record the commands and results in the PR.

## Documentation

- Update `ARCHITECTURE.md` to describe the implemented Customer Domain backend
  module and API boundary.
- Update `docs/domains/CUSTOMER.md` and `docs/concepts/CUSTOMER.md` only if the
  implementation clarifies the already approved contract without changing its
  meaning.
- Update `docs/TESTING.md` only if a permanent Customer Domain test section
  adds value beyond this task.
- Do not change domain ownership, schema documentation or diagrams unless an
  approved corrective schema change is required.

## Notes For AI Agent

- Toteuta vain tassa taskissa maaritelty scope.
- Ala muuta TASK-036A:ssa hyvaksyttya tietomallia ilman ihmisen paatosta.
- Ala lisaa frontendia, autentikointia, valtuutusta tai organisaatiorajausta.
- Ala lisaa uusia riippuvuuksia ilman hyvaksyntaa.
- Kayta backendia luotettavana validointi- ja lifecycle-rajana.
- Lisaa testit onnistumis-, validointi-, omistajuus- ja virhepoluille.
- Kerro lopuksi mita muutit ja miten tarkistit tyon.
