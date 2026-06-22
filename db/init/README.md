# Database Init Scripts

Tämä hakemisto sisältää paikallisen tai kehitysympäristön tietokanta-alustuksen skriptejä.

Status: convention defined, PostgreSQL selected

Paikallinen database container käyttää PostgreSQL:ää.

---

# Purpose

Init scripts are for:

- local development bootstrap
- empty database setup for Docker Compose
- optional seed baseline for developer environments

Init scripts are not a substitute for migrations.

---

# Naming Convention

Käytä kolminumeroista prefixiä ja lowercase snake_case -nimeä:

```text
001_create_database.sql
002_create_extensions.sql
003_seed_development_data.sql
```

Muoto:

```text
NNN_<action>_<purpose>.sql
```

Esimerkkejä:

```text
001_create_extensions.sql
002_seed_reference_data.sql
003_seed_development_users.sql
```

---

# Rules

- Init scripts are local/dev bootstrap scripts unless explicitly documented otherwise.
- Do not store production secrets.
- Do not store production data.
- Do not use init scripts to bypass migrations.
- If schema changes, add a migration in `db/migrations/`.
- Keep seed data clearly non-production.

---

# Relationship To Migrations

The schema source of truth is:

```text
db/migrations/
```

Init scripts may help create a local database quickly, but production and staging schema changes must flow through migrations.
