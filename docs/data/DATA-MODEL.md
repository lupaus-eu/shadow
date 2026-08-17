# Data Model

Tämä dokumentti kuvaa järjestelmän loogisen datamallin.

Status: core and customer model baseline defined. AI and billing still TBD.

Looginen datamalli kuvaa:

- käsitteet
- entiteetit
- suhteet
- domain ownershipin
- tärkeät invariantit

Fyysinen tietokantamalli kuvataan tiedostossa `docs/data/DATABASE.md`.

---

# Sources

Lue nämä yhdessä datamallin kanssa:

- `docs/domains/DOMAIN.md`
- `docs/concepts/CONCEPTS.md`
- `docs/data/DATABASE.md`
- `docs/decisions/ADR-002-database-migrations.md`

---

# Logical Entities

| Entity | Notes |
| --- | --- |
| User | Application user allowlist entry with required email and role `consultant` or `admin`. |
| User Identity | Permanent exact `(issuer, subject)` binding to one User. |
| OIDC Login Transaction | Ten-minute browser-bound, single-use login flow state. |
| Authentication Session | Opaque server-side session represented by a hashed identifier. |
| Organisation | Tenant-like organisation boundary for scenarios and organisation-specific metamodels. Active organisation names are case-insensitively unique. |
| Scenario | Versioned planning or analysis context within an organisation. |
| Organisation State | Scenario-specific named snapshot state with target date and version. |
| Event | Scenario-specific dated event. |
| Metamodel | Default or organisation-specific model that defines allowed node and edge types. |
| Node Type | Metamodel-owned type definition for graph nodes. |
| Edge Type | Metamodel-owned type definition for graph edges. |
| Type Attribute | Attribute definition owned by a node type or edge type. |
| Allowed Connection | Rule allowing an edge type between a source node type and target node type. |
| Graph Node | Scenario-owned node with a logical creation date and optional logical deletion date. |
| Graph Edge | Scenario-owned connection whose logical lifetime must remain inside both endpoint node lifetimes. |
| Timeserie | Scenario-specific timeseries definition. |
| Timeserie Value | Date-specific value for a timeserie. |
| Customer | Application-wide customer profile with active, archived and soft-deleted lifecycle states. |
| Contact | Customer-owned contact person or communication channel. |
| Customer Address | Customer-owned labelled postal or visiting address. |

---

# Relationship Rules

- Nullable `created_by`, `modified_by` and `deleted_by` values may remain null
  for historical, seed or pre-authentication rows. Authenticated application
  mutations write the current User as creator, modifier or soft-deleter as
  appropriate; no historical backfill is implied.
- A User owns zero or more identities across different issuers and zero or more
  application sessions.
- Active User emails are case-insensitively unique; soft-deleted emails are
  reusable.
- An exact `(issuer, subject)` belongs to one User, and a User has at most one
  identity per issuer.
- Login transactions are browser-bound through a separate hash and contain no
  User or provider-token relationship.
- Sessions reference one User and persist no raw session identifier or provider
  token.
- An organisation owns many scenarios.
- Active organisations cannot share the same name when compared case-insensitively.
- A scenario owns many organisation states and events.
- Organisation states and events have required `target_date` values.
- Normal application-level scenario deletion is a soft delete using `deleted_time`.
- When the application soft-deletes a scenario, it must also soft-delete owned
  organisation states, events, graph nodes, graph edges, timeseries and
  timeserie values through `deleted_time`.
- Physical database cascades exist only as hard-delete cleanup/safety behavior, not as the normal application deletion flow.
- A scenario can reference a source scenario.
- A scenario can reference one initial organisation state.
- A metamodel can be default when `organisation_id` is `NULL`.
- An organisation can have one active organisation-specific metamodel.
- A metamodel owns node types, edge types, type attributes and allowed connection rules.
- Type attributes are owned by exactly one node type or edge type.
- A scenario owns graph nodes and graph edges.
- Graph nodes and graph edges have logical lifetimes defined by `create_date`
  and nullable `delete_date`, separate from persistence `deleted_time`.
- An organisation-state graph projection includes an element when
  `create_date <= target_date` and `delete_date` is null or
  `delete_date >= target_date`.
- Logical deletion dates cannot precede creation dates.
- Deleting a graph node or edge on its `create_date` uses persistence
  `deleted_time` instead of creating an inclusive zero-day logical lifetime.
- Same-day node deletion also persistence-soft-deletes connected edges.
- Graph edges reference source and target graph nodes.
- A graph edge lifetime must remain inside both endpoint node lifetimes.
- A timeserie belongs to one scenario and owns dated values.
- Active timeserie values must use dates that are valid starts for the owning
  timeserie's time unit and typed values that match the owning timeserie's value
  unit.
- Graph nodes may reference primary and secondary timeseries owned by the same
  scenario.
- A customer owns zero or more contacts and customer addresses.
- Customer names, emails, contact names and address labels are not unique.
- Active and archived customers remain readable and editable.
- Normal customer deletion atomically soft-deletes the customer and its active
  contacts and customer addresses through `deleted_time`.
- Contacts and customer addresses have no archive state or restore lifecycle in
  the current baseline.
- Physical customer-to-child cascades exist only as hard-delete cleanup/safety
  behavior, not as the normal application deletion flow.

---

# Stable Keys

The physical model uses bigint primary keys internally and stable text keys for imported or externally meaningful identifiers.

Examples:

- `organisation_key`
- `scenario_key`
- `org_state_key`
- `event_key`
- `node_type_key`
- `edge_type_key`
- `node_key`
- `edge_key`
- `timeserie_key`

These keys preserve Varjo-style identifiers while allowing relational foreign keys to use bigint primary keys.

---

# Future TBD Entities

The following candidate entities are retained as planned future work. They are not part of the core schema baseline migration yet.

| Entity | Owning Domain | Concept Document | Notes |
| --- | --- | --- | --- |
| Invoice | Billing Domain | `docs/concepts/INVOICE.md` | Billing document |
| InvoiceLine | Billing Domain | TBD | Invoice row |
| Payment | Billing Domain | TBD | Payment record |
| Document | Document Domain | `docs/concepts/DOCUMENT.md` | Uploaded document |
| DocumentVersion | Document Domain | TBD | Versioned document content |
| AIExtraction | AI Domain | `docs/concepts/AI_EXTRACTION.md` | Derived AI output |

Future relationship rules:

- Billing records may reference Customer records.
- Document records may reference Customer records.
- AI records may reference Document and Customer records.
- A domain may reference another domain's data but may not modify another domain's owned tables directly.

---

# Logical Data Model Diagram

PlantUML source:

```text
docs/diagrams/data-logical-model.puml
```

Generated SVG:

```text
docs/diagrams/generated/data-logical-model.svg
```

Create or update this diagram when logical entities or relationships change.

---

# Change Rules

When logical data model changes:

1. Update relevant concept document.
2. Update relevant domain document.
3. Update this document.
4. Update database documentation if physical schema changes.
5. Add or update migration scripts in `db/migrations/`.
6. Update PlantUML diagrams and generated SVGs.
7. Add ADR if the change affects architecture or data strategy.
