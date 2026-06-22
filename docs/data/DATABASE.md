# Database

Tämä dokumentti kuvaa järjestelmän fyysisen tietokantamallin ja tietokantakäytännöt.

Status: initial candidate model, database stack decided

Tietokantateknologia ja ORM on päätetty ADR-001:ssä:

- PostgreSQL
- SQLAlchemy

Migraatiotyökalu päätetään erikseen.

---

# Sources

Lue nämä yhdessä tietokantamallin kanssa:

- `docs/data/DATA-MODEL.md`
- `docs/domains/DOMAIN.md`
- `docs/concepts/CONCEPTS.md`
- `db/migrations/README.md`
- `db/init/README.md`
- `docs/decisions/ADR-001-tech-stack.md`
- `docs/decisions/ADR-002-database.md`, jos se luodaan migraatiotyökalua tai tarkempaa tietokantastrategiaa varten

---

# Physical Schema Ownership

Taulun omistaa yksi domain.

Sääntö:

```text
Only the owning domain may modify its tables directly.
```

Muut domainit saavat viitata tauluihin foreign keyllä tai domainin tarjoaman API/service-rajapinnan kautta, mutta eivät kirjoita toisen domainin tauluihin suoraan.

---

# Candidate Tables

| Table | Owning Domain | Notes |
| --- | --- | --- |
| customers | Customer Domain | Customer source of truth |
| contacts | Customer Domain | Customer contacts |
| customer_addresses | Customer Domain | Customer addresses |
| invoices | Billing Domain | Invoice headers |
| invoice_lines | Billing Domain | Invoice rows |
| payments | Billing Domain | Payment records |
| subscriptions | Billing Domain | Subscription records |
| documents | Document Domain | Document metadata |
| document_versions | Document Domain | Document versions |
| ai_classifications | AI Domain | AI classification outputs |
| ai_summaries | AI Domain | AI summary outputs |
| ai_extractions | AI Domain | AI extraction outputs |

---

# Physical Schema Diagram

PlantUML source:

```text
docs/diagrams/db-physical-schema.puml
```

Generated SVG:

```text
docs/diagrams/generated/db-physical-schema.svg
```

Create or update this diagram when tables, columns, foreign keys or indexes change materially.

---

# Migration Policy

All schema changes are done as versioned migration scripts in:

```text
db/migrations/
```

Do not change production schema manually.

Each migration must be:

- ordered
- committed
- reviewable
- safe to run once
- connected to a task or PR

---

# Init Script Policy

Database initialization scripts live in:

```text
db/init/
```

Init scripts are for local/dev bootstrap only unless explicitly documented otherwise.

Do not use `db/init/` as a replacement for migrations.

---

# Change Rules

When database schema changes:

1. Update `docs/data/DATABASE.md`.
2. Update `docs/data/DATA-MODEL.md` if logical model changes.
3. Update relevant domain and concept documents.
4. Add migration script in `db/migrations/`.
5. Update init scripts only if local bootstrap needs them.
6. Update `docs/diagrams/db-physical-schema.puml`.
7. Regenerate `docs/diagrams/generated/db-physical-schema.svg`.
