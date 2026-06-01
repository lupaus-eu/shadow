# Data Model

Tämä dokumentti kuvaa järjestelmän loogisen datamallin.

Status: initial candidate model

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

Alustavat candidate-entiteetit:

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

---

# Relationship Rules

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
