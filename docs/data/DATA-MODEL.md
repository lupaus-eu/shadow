# Data Model

Tämä dokumentti kuvaa järjestelmän loogisen datamallin.

Status: core model baseline defined. AI, billing and customer still TBD.

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
- `docs/decisions/ADR-002-database.md`, kun se on luotu

---

# Logical Entities

| Entity | Notes |
| --- | --- |
| User | Application user with role `consultant` or `admin`. |
| Organisation | Tenant-like organisation boundary for scenarios and organisation-specific metamodels. Active organisation names are case-insensitively unique. |
| Scenario | Versioned planning or analysis context within an organisation. |
| Organisation State | Scenario-specific named snapshot state with target date and version. |
| Event | Scenario-specific dated event. |
| Metamodel | Default or organisation-specific model that defines allowed node and edge types. |
| Node Type | Metamodel-owned type definition for graph nodes. |
| Edge Type | Metamodel-owned type definition for graph edges. |
| Type Attribute | Attribute definition owned by a node type or edge type. |
| Allowed Connection | Rule allowing an edge type between a source node type and target node type. |
| Graph | Organisation-state graph snapshot. |
| Graph Node | Node instance inside one graph snapshot. |
| Graph Edge | Edge instance inside one graph snapshot. |
| Timeserie | Scenario-specific timeseries definition. |
| Timeserie Value | Date-specific value for a timeserie. |

---

# Relationship Rules

- An organisation owns many scenarios.
- Active organisations cannot share the same name when compared case-insensitively.
- A scenario owns many organisation states and events.
- An organisation state has a required `target_date` at the application/API
  level.
- Normal application-level scenario deletion is a soft delete using `deleted_time`.
- When the application soft-deletes a scenario, it must also soft-delete owned organisation states, events, graphs, timeseries and timeserie values.
- Physical database cascades exist only as hard-delete cleanup/safety behavior, not as the normal application deletion flow.
- A scenario can reference a source scenario.
- A scenario can reference one initial organisation state.
- A metamodel can be default when `organisation_id` is `NULL`.
- An organisation can have one active organisation-specific metamodel.
- A metamodel owns node types, edge types, type attributes and allowed connection rules.
- Type attributes are owned by exactly one node type or edge type.
- A graph belongs to one organisation state.
- A graph owns graph nodes and graph edges.
- Graph edges reference source and target graph nodes.
- A timeserie belongs to one scenario and owns dated values.

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
| Customer | Customer Domain | `docs/concepts/CUSTOMER.md` | Customer source of truth |
| Contact | Customer Domain | TBD | Customer contact person or channel |
| CustomerAddress | Customer Domain | TBD | Customer address data |
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
