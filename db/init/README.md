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
| `001_seed_reference_data.sql` | Shared metamodel-only insertion logic used by the production CLI and development wrapper. |
| `002_seed_development_data.sql` | Local/dev-only wrapper that inserts consultant/admin users and invokes the shared reference seed. |
| `metamodel_state_##default##.json` | The single approved default-metamodel source for both callers. |

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

Init scripts may help create a local database quickly, but production schema
changes must flow through migrations.

Run migrations before seed scripts. For the current local database baseline:

```bash
uv run --project backend python backend/migrate.py up
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/init/002_seed_development_data.sql
```

Do not run the development seed before the migration runner reports that no
migrations are pending.

`002_seed_development_data.sql` is idempotent for normal local use. It reads the
JSON source, stores it in the transaction-local
`schatten.seed_reference_data.metamodel_json` PostgreSQL setting and includes
`001_seed_reference_data.sql` in the same transaction. The shared SQL obtains a
transaction-scoped advisory lock before checking for an active default, so local
and production callers cannot interleave reference inserts.

The development wrapper:

- it ensures active `Development Consultant` (`consultant@example.local`) and
  `Development Admin` (`admin@example.local`) rows when those active emails are
  absent; these emails match the local Authentik fixtures
- it does not insert external identities, login transactions or sessions
- it inserts the default metamodel only when no active default metamodel exists
- it does not create organisations, scenarios, org states, events, graph nodes,
  graph edges, timeseries, timeserie values, customers, contacts or customer
  addresses

The production backend image packages only the shared SQL and JSON, not the
development wrapper. After migrations, run its database-only command explicitly:

```bash
DATABASE_URL=postgresql://user:password@database:5432/schatten \
  python -m app.seed_reference_data
```

The command inserts one complete default only when no active default exists;
otherwise it succeeds as a no-op without repairing or changing existing content.
It never inserts development Users or runs automatically at application startup.
