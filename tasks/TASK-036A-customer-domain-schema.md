# TASK-036A Customer Domain Schema

Status: Implemented

## Source Plan

Approved plan: implement the Customer Domain in three related tasks. This first
task defines Customer, Contact and Customer Address in the existing Customer
concept document, adds their physical schema and SQLAlchemy models, and updates
the logical and physical data documentation.

Contact and Customer Address are documented as parts of
`docs/concepts/CUSTOMER.md`; separate concept files are not created.

## Goal

Promote Customer, Contact and Customer Address from candidate entities into an
implemented Customer Domain persistence baseline. Define their fields,
relationships, invariants and lifecycle rules before the backend API and
frontend management UI are implemented.

The schema must follow the repository's existing PostgreSQL, SQLAlchemy, audit
column and soft-delete conventions without introducing a migration framework or
new dependency.

## Requirements

- Expand `docs/concepts/CUSTOMER.md` with dedicated Customer, Contact and
  Customer Address sections that define:
  - business meaning and Customer Domain ownership
  - key fields and relationships
  - required and optional fields
  - normalization and validation rules
  - invariants and lifecycle behavior
  - customer soft-delete propagation to contacts and addresses
  - API relationships and AI-agent implementation guidance
- Keep `docs/concepts/CUSTOMER.md` as the only concept document for all three
  entities; do not create `CONTACT.md` or `CUSTOMER_ADDRESS.md`.
- Define Customer with:
  - internal bigint `customer_id`
  - required, non-blank `name`
  - optional `email`
  - required `status` constrained to `active`, `archived` or `deleted`
  - standard audit and soft-delete columns
- Define Contact with:
  - internal bigint `contact_id`
  - required `customer_id`
  - required, non-blank `name`
  - optional `email`, `phone` and `job_title`
  - standard audit and soft-delete columns
- Define Customer Address with:
  - internal bigint `customer_address_id`
  - required `customer_id`
  - required, non-blank `label`
  - required, non-blank `address_line_1`
  - optional `address_line_2`, `postal_code`, `city` and `region`
  - required two-letter `country_code`
  - standard audit and soft-delete columns
- Document that blank optional values are normalized to `NULL` by the trusted
  backend service added in TASK-036B.
- Do not add uniqueness requirements for customer names, emails, contact names
  or address labels.
- Contacts and customer addresses use soft deletion and have no status field or
  restore lifecycle in this baseline.
- Customer deletion is a soft delete. The backend service added in TASK-036B
  must soft-delete the customer's active contacts and addresses atomically.
- Archived customers and their contacts and addresses remain visible and
  editable.
- Add three ordered, reviewable SQL migrations:
  - `db/migrations/006_create_customers.sql`
  - `db/migrations/007_create_contacts.sql`
  - `db/migrations/008_create_customer_addresses.sql`
- Use bigint identity primary keys starting at `101`, consistent with the core
  schema.
- Add `created_by`, `modified_by` and `deleted_by` nullable foreign keys to
  `users(user_id)` and `created_time`, `modified_time` and `deleted_time`
  timestamp columns consistently with existing tables.
- Enforce in the customer schema that `status = 'deleted'` exactly when
  `deleted_time IS NOT NULL`.
- Add database constraints for required non-blank text and the two-letter
  customer-address country-code shape.
- Add foreign keys from contacts and customer addresses to customers.
  `ON DELETE CASCADE` may be used only as physical hard-delete cleanup/safety;
  normal application deletion remains service-level soft deletion.
- Add partial indexes that support non-deleted customer status/name lookup and
  non-deleted contact/address lookup by customer.
- Add SQLAlchemy models in `backend/app/api/v1/customers/models.py` matching the
  migrations and existing model conventions.
- Do not add API schemas, services or routes in this task.
- Update logical and physical data documentation and diagrams to move Customer,
  Contact and Customer Address out of the future-TBD lists and into the
  implemented model.
- Add the currently referenced logical data-model PlantUML source and generated
  SVG if they are still missing when this task is implemented.
- Update migration instructions to include migrations 006 through 008.
- Do not add or modify local development seed data unless separately approved.

## Acceptance Criteria

- [x] `docs/concepts/CUSTOMER.md` completely defines Customer, Contact and
      Customer Address without adding separate Contact or Customer Address
      concept files.
- [x] `docs/domains/CUSTOMER.md` records the approved ownership, lifecycle,
      soft-delete propagation and nested API direction.
- [x] Migrations 006, 007 and 008 create the three Customer Domain tables in
      dependency order.
- [x] The migrations follow the established bigint identity, audit-column and
      soft-delete conventions.
- [x] Customer status and deletion timestamp consistency is database-enforced.
- [x] Required non-blank values and address country-code shape are
      database-enforced.
- [x] Contacts and addresses reference their owning customer and have active
      parent-lookup indexes.
- [x] No unapproved uniqueness constraint or new dependency is introduced.
- [x] SQLAlchemy models match the PostgreSQL schema and work with the existing
      SQLite-based backend test setup where applicable.
- [x] A fresh PostgreSQL database can apply migrations 001 through 008 in
      order.
- [x] A PostgreSQL database already at migration 005 can apply migrations 006
      through 008 without losing or rewriting existing data.
- [x] Logical and physical data documentation reflect the implemented Customer
      Domain schema.
- [x] PlantUML sources and generated SVGs reflect the new tables and
      relationships.
- [x] Backend model tests, lint and type checking pass.

## Out Of Scope

- Customer, contact or address API schemas, services and routes.
- Frontend Customer tab or API client.
- Customer merge, restore or permanent-delete workflows.
- Organisation ownership or organisation-specific customers.
- Authentication, authorization or Entra ID integration.
- Billing, Document or AI Domain integration.
- A shared AuditEvent entity or event-writing workflow.
- Contact or address uniqueness rules.
- Reference-data validation against a complete country-code catalog.
- New dependencies, a migration framework or seed data.

## Implementation Notes

- This is the first task in the TASK-036 series. TASK-036B depends on its
  schema, models and documented contracts.
- Read `AGENTS.md`, `ARCHITECTURE.md`,
  `docs/decisions/ADR-001-tech-stack.md`,
  `docs/concepts/CUSTOMER.md`, `docs/domains/CUSTOMER.md`,
  `docs/data/DATA-MODEL.md`, `docs/data/DATABASE.md`,
  `db/migrations/README.md`, `db/init/README.md`, `docs/TESTING.md` and this
  task before implementation.
- Keep the three migrations separate because contacts and addresses depend on
  customers and each file should represent one reviewable schema addition.
- The migration files are source of truth. Init scripts must not be used as a
  replacement for them.
- Model column names must follow the existing physical-schema convention even
  where the concept uses generic names such as `created_at` or `updated_at`.
- The child soft-delete cascade is documented here but implemented and tested
  transactionally in TASK-036B; do not add database soft-delete triggers.
- No ADR is expected because the task uses the existing database and domain
  architecture. Stop and request a decision if implementation would require a
  migration-strategy or ownership change.

## Testing

Required:

- [x] Backend model and constraint tests
- [x] PostgreSQL migration verification from an empty schema
- [x] PostgreSQL upgrade verification from migration 005
- [x] Documentation and diagram verification
- [x] Backend lint
- [x] Backend type checking

Not applicable:

- [x] Frontend tests: no frontend code changes are in scope.
- [x] Backend API integration tests: routes and services are added in
      TASK-036B.
- [x] Frontend build: no frontend changes are in scope.
- [x] End-to-end browser tests: there is no user-facing behavior in this task.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright

cd ..
docker compose --profile docs build diagram-renderer
docker compose --profile docs run --rm diagram-renderer
```

Migration verification must use disposable local PostgreSQL databases or
schemas and record the exact `psql` commands and results in the PR. It must not
modify staging or production databases.

## Documentation

Update:

- `docs/concepts/CUSTOMER.md`
- `docs/domains/CUSTOMER.md`
- `docs/data/DATA-MODEL.md`
- `docs/data/DATABASE.md`
- `db/migrations/README.md` when its current migration list or guidance needs
  updating
- `db/init/README.md` and `docs/LOCAL-DEVELOPMENT.md` migration command lists
- `docs/diagrams/db-physical-schema.puml`
- `docs/diagrams/generated/db-physical-schema.svg`
- logical data-model PlantUML and generated SVG

Do not update `ARCHITECTURE.md` to claim that the backend API or frontend tab is
implemented before TASK-036B and TASK-036C are complete.

## Notes For AI Agent

- Toteuta vain tassa taskissa maaritelty scope.
- Ala luo erillisia Contact- tai Customer Address -concept-tiedostoja.
- Ala lisaa API-reitteja tai frontend-toiminnallisuutta tassa taskissa.
- Ala lisaa uusia riippuvuuksia ilman hyvaksyntaa.
- Kaikki skeemamuutokset tehdaan migraatioina; ala muuta tuotantotietokantaa.
- Lisaa testit muutoksen riskin mukaan ja raportoi kaikki ajetut tarkistukset.
- Kerro lopuksi mita muutit ja miten tarkistit tyon.
