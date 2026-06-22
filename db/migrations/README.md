# Database Migrations

Tämä hakemisto sisältää versionhallittavat tietokantamigraatiot.

Status: migration convention defined, PostgreSQL and SQLAlchemy selected

Tietokantateknologia on PostgreSQL ja ORM on SQLAlchemy. Migraatiotyökalu päätetään erikseen.

---

# Naming Convention

Käytä lineaarista kolminumeroista prefixiä ja lowercase snake_case -nimeä:

```text
001_create_customers.sql
002_create_contacts.sql
003_create_customer_addresses.sql
004_create_documents.sql
005_add_document_status.sql
006_create_ai_extractions.sql
```

Muoto:

```text
NNN_<verb>_<object>.sql
```

Sallitut yleiset verbit:

- `create`
- `add`
- `alter`
- `rename`
- `drop`
- `backfill`

Esimerkkejä:

```text
001_create_customers.sql
002_create_contacts.sql
003_add_customer_soft_delete.sql
004_create_documents.sql
005_add_document_status.sql
006_create_ai_extractions.sql
```

---

# Rules

- Yksi looginen muutos per migraatio.
- Numerointi kasvaa yhdellä.
- Älä muuta jo mainiin mergeättyä migraatiota ilman erillistä päätöstä.
- Korjaa aiempi julkaistu migraatio uudella migraatiolla.
- Migraatio ei saa sisältää salaisuuksia.
- Migraation pitää olla reviewattava.
- Tuotantotietokantaa ei muuteta käsin.

---

# Relationship To Init Scripts

`db/init/` voi sisältää kehitysympäristön alustusskriptejä.

Migraatiot ovat silti source of truth skeemamuutoksille.

Älä kopioi muutoksia vain init-skripteihin. Lisää aina migraatio, jos skeema muuttuu.

---

# Required Documentation Updates

Kun lisäät migraation, tarkista pitääkö päivittää:

- `docs/data/DATABASE.md`
- `docs/data/DATA-MODEL.md`
- `docs/domains/<DOMAIN>.md`
- `docs/concepts/<CONCEPT>.md`
- `docs/diagrams/db-physical-schema.puml`
- `docs/diagrams/generated/db-physical-schema.svg`
- relevantti ADR
