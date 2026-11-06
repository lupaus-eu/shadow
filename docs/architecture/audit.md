# Audit

## Model

Yearclock maintains an append-only application Audit Log in PostgreSQL.

Audit Events record:

- actor User Account or service identity
- Organization
- action
- target type and identifier
- timestamp
- request correlation identifier
- minimal change summary
- Support Access grant when applicable

Audit Events never contain credentials, tokens, payment details, MFA material, or unnecessary copies of customer content.

## Audited actions

- Organization creation, ownership, role, invitation, and membership changes
- Yearclock, Lane, Category, Event, Series, and Occurrence mutations
- Recommendation decisions when that future capability is implemented
- Support Access grants, use, and revocation
- Stripe subscription projection changes
- Organization deletion lifecycle changes
- Exports of a Yearclock's Events (`yearclock.export`: format, scope, row count, language; never the content); imports (`yearclock.import_preview` and `yearclock.import` with the import reference, counts, and format, plus one `event.created` per created Event carrying `import_id`); Data transfers (`data.export`, `data.import_preview`, `data.import`: one entry per Organization with the format, import reference, and counts, never content); Organization Exports (`organization.export`: the schema and counts of what the file holds, never content)

Ordinary customer read-only viewing is not logged. Reads performed through Support Access are logged.

## Storage and access

- `record_audit_event` takes the actor, Organization, and Support Access grant
  from the transaction's trusted request context.
- Migration `0025` enables row-level security on `audit_events`: reads return
  only the current Organization's events, and an insert must carry the current
  Organization context. The application role has no UPDATE or DELETE
  privilege, so Audit Events are append-only.
- Owners and Admins browse the log in the **Activity** panel; the API is
  described in `api.md`.

## Integrity

- Customer and support users cannot update or delete Audit Events.
- Audit writes occur in the same transaction as the application mutation when possible.
- Audit retention is controlled by service policy and is distinct from retaining customer-content copies.
