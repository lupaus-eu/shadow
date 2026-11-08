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
- Events of a Model's timeline (`event.created`, `event.updated`, `event.deleted`): the Model, line and event ids, the event date, the operations changed and how many of each (`change_counts`, and for an update the `fields` that changed, the previous date and the previous counts); never an element name, an event title or a note, which are customer content
- Lines of a Model's timeline (`line.created`, `line.renamed`, `line.deleted`): the Model, line, parent line and branch event ids, the fields a rename changed, and the number of events a deleted Scenario held; never a line name or description. Moving nodes (positions) and acknowledging a changed start are drawing and notice state and are not audited
- Recommendation decisions when that future capability is implemented
- Support Access grants, use, and revocation
- Stripe subscription projection changes
- Organization deletion lifecycle changes
- Exports of a Yearclock's Events (`yearclock.export`: format, scope, row count, language; never the content); imports (`yearclock.import_preview` and `yearclock.import` with the import reference, counts, and format, plus one `event.created` per created Event carrying `import_id`); Data transfers (`data.export`, `data.import_preview`, `data.import`: one entry per Organization with the format, import reference, and counts, never content); Organization Exports (`organization.export`: the schema and counts of what the file holds, never content)

Agent calls through MCP are recorded separately in `mcp_calls` (ADR-0047): every call, including reads, without content. That table is not part of the Audit Events guarantee above: the application role may delete only successful read rows, and only the retention job under its own worker scope does so (default 90 days). Writes through MCP also produce their normal Audit Event with `source: "mcp"`.

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
