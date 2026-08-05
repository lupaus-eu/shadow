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

Current init scripts:

| Script | Purpose |
| --- | --- |
| `002_seed_development_data.sql` | Local/dev-only seed for a dummy admin user and the default metamodel from `db/init/metamodel_state_##default##.json`. |

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

Run migrations before seed scripts. For the current local database baseline:

```bash
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/migrations/001_create_core_schema.sql
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/migrations/002_add_org_state_name_and_org_name_unique_index.sql
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/migrations/003_alter_scenario_target_dates_not_null.sql
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/migrations/004_alter_graphs_to_scenarios.sql
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/migrations/005_add_graph_logical_delete_dates.sql
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/migrations/006_create_customers.sql
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/migrations/007_create_contacts.sql
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/migrations/008_create_customer_addresses.sql
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/init/002_seed_development_data.sql
```

`002_seed_development_data.sql` is idempotent for normal local use:

- it inserts `Development Admin` only when `users` is empty
- it inserts the default metamodel only when no active default metamodel exists
- it does not create organisations, scenarios, org states, events, graph nodes,
  graph edges, timeseries, timeserie values, customers, contacts or customer
  addresses
