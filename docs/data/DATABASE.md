# Database

Tämä dokumentti kuvaa järjestelmän fyysisen tietokantamallin ja tietokantakäytännöt.

Status: core, customer and authentication persistence schema baseline defined. AI and billing still TBD.

Tietokantateknologia ja ORM on päätetty ADR-001:ssä:

- PostgreSQL
- SQLAlchemy

Migraatiostrategia on päätetty ADR-002:ssa. Skeeman lähde on versionhallittu,
pareittainen SQL-migraatioketju hakemistossa `db/migrations/`, ja migraatiot
ajetaan repositoryn Python/Psycopg-runnerilla.

---

# Sources

Lue nämä yhdessä tietokantamallin kanssa:

- `docs/data/DATA-MODEL.md`
- `docs/domains/DOMAIN.md`
- `docs/concepts/CONCEPTS.md`
- `db/migrations/README.md`
- `db/init/README.md`
- `docs/decisions/ADR-001-tech-stack.md`
- `docs/decisions/ADR-002-database-migrations.md`
- `docs/decisions/ADR-003-coolify-deployment.md`

---

# Physical Schema Ownership

Domain-omistajuus täsmennetään erillisissä domain- ja concept-dokumenteissa, kun Schattenin tuotemalli tarkentuu.

Sääntö:

```text
Only the owning domain may modify its tables directly.
```

Muut domainit saavat viitata tauluihin foreign keyllä tai domainin tarjoaman API/service-rajapinnan kautta, mutta eivät kirjoita toisen domainin tauluihin suoraan.

---

# Core Tables

Core schema is created and updated by:

```text
db/migrations/001_create_core_schema.sql
db/migrations/002_add_org_state_name_and_org_name_unique_index.sql
db/migrations/003_alter_scenario_target_dates_not_null.sql
db/migrations/004_alter_graphs_to_scenarios.sql
db/migrations/005_add_graph_logical_delete_dates.sql
db/migrations/006_create_customers.sql
db/migrations/007_create_contacts.sql
db/migrations/008_create_customer_addresses.sql
db/migrations/009_add_auth_identity_session_schema.sql
```

| Table | Purpose | Notes |
| --- | --- | --- |
| `users` | Application users | Required email; active emails are case-insensitively unique. `role` is `consultant` or `admin`. |
| `user_identities` | Durable provider-neutral identities | Exact `(issuer, subject)` binds to one User; one identity per User and issuer. |
| `oidc_login_transactions` | Browser-bound OIDC flow state | SHA-256 state/browser hashes, nonce, PKCE, return path and ten-minute expiry; no provider tokens. |
| `auth_sessions` | Opaque application sessions | SHA-256 session-id hash, User, CSRF token, activity and absolute-expiry timestamps. |
| `organisations` | Organisation records | Uses `organisation_key` for stable external/import identity. Active names are case-insensitively unique. |
| `scenarios` | Scenario versions within an organisation | References source scenario and optional initial org state. |
| `org_states` | Scenario-specific organisation state snapshots | `name` is the human-readable state display name; `target_date` is required and enforced as `NOT NULL`; soft-deleted with parent scenario in normal application flows. |
| `events` | Scenario events | `target_date` is required and enforced as `NOT NULL`; soft-deleted with parent scenario in normal application flows. |
| `metamodels` | Default or organisation-specific type model | `organisation_id IS NULL` means the default metamodel. |
| `node_types` | Node type definitions for a metamodel | Preserves Varjo-style `node_type_key`. |
| `edge_types` | Edge type definitions for a metamodel | Preserves Varjo-style `edge_type_key`. |
| `type_attributes` | Attribute definitions owned by node or edge types | Exactly one owner FK is allowed according to `owner_kind`. |
| `allowed_connections` | Allowed source/target node type pairs for edge types | One row per edge/source/target combination. |
| `graph_nodes` | Scenario graph nodes | `create_date` and nullable `delete_date` define the logical lifetime; dynamic attributes use `JSONB`; timeserie references are nullable FKs. |
| `graph_edges` | Scenario graph edges | References source and target graph nodes and has a logical `create_date`/`delete_date` lifetime. |
| `timeseries` | Scenario-specific timeseries definitions | Supports `day`, `week`, `month`, `year` time units. |
| `timeserie_values` | Timeseries values by date | No `name` column; value is stored as `JSONB` with the public scalar under `value`. |
| `customers` | Application-wide customer profiles | Status is `active`, `archived` or `deleted`; status and `deleted_time` must agree. |
| `contacts` | Customer-owned contacts | Name is required; email, phone and job title are optional. |
| `customer_addresses` | Customer-owned labelled addresses | Label, first address line and two-letter uppercase country code are required. |

---

# Common Columns

Most core tables use:

- bigint identity primary keys starting at `101`
- `created_by`, `modified_by`, `deleted_by` nullable FKs to `users(user_id)`
- `created_time`, `modified_time`, `deleted_time` as `TIMESTAMPTZ`
- soft-delete filtering through `deleted_time IS NULL`
- normal application deletion uses soft delete, not physical row deletion

Audit-user columns remain nullable so historical, seed and pre-authentication
rows are valid. Current authenticated application writes set `created_by` on
creation, `modified_by` on updates and domain mutation actions, and `deleted_by`
on persistence soft deletion. Cascade-style application services propagate the
same actor to every affected owned row. Existing null values are not backfilled.

Primary key names follow table-specific singular names, for example `scenario_id`, `org_state_id`, `graph_node_id` and `timeserie_value_id`.

`schema_migrations` is infrastructure metadata owned by the migration runner,
not a domain table. It stores each applied version, up filename, SHA-256 checksum
and application timestamp. It remains present even when migration 001 is rolled
back.

---

# Important Constraints

- `users.role` is constrained to `consultant` or `admin`.
- `users.email` is non-null and non-blank. A partial unique index enforces
  case-insensitive uniqueness only for active Users.
- `user_identities` requires non-blank exact issuer and subject values and
  uniquely constrains both `(issuer, subject)` and `(user_id, issuer)`.
- OIDC state, browser-binding and application session identifier hashes are
  exactly 32 bytes, representing SHA-256 output. There is no raw session ID or
  provider-token column.
- OIDC transaction expiry is after creation; session last activity is not
  before creation and absolute expiry is after creation.
- Active organisation names are unique case-insensitively through `lower(name)` where `deleted_time IS NULL`; soft-deleted historical names are reusable.
- `org_states.target_date` and `events.target_date` are required with `NOT NULL` constraints.
- `org_states.scenario_id` and `events.scenario_id` use `ON DELETE CASCADE` for physical hard-delete cleanup/safety behavior.
- `graph_nodes.scenario_id` and `graph_edges.scenario_id` use `ON DELETE CASCADE`.
- `graph_edges.source_graph_node_id` and `graph_edges.target_graph_node_id` use `ON DELETE CASCADE`.
- `timeseries.scenario_id` and `timeserie_values.timeserie_id` use `ON DELETE CASCADE`.
- `graph_nodes` timeserie references use `ON DELETE SET NULL`.
- `graph_nodes` and `graph_edges` enforce `delete_date IS NULL OR delete_date >= create_date`.
- Structure deletion sets `deleted_time` when the selected target date equals
  the element's `create_date`; same-day node deletion does the same for its
  connected edges.
- Edge lifetime containment inside endpoint node lifetimes is enforced in the
  Organisation Twin Structure service.
- `timeseries.time_unit` is constrained to `day`, `week`, `month` or `year`.
- `timeseries.value_unit` is constrained to `number`, `string` or `boolean`.
- Timeserie value replacement is application-level behavior: active omitted
  values are soft-deleted, submitted dates can reactivate soft-deleted rows and
  the service validates value type plus time-unit start date.
- `type_attributes` enforces exactly one owner reference matching `owner_kind`.
- `customers.name`, `contacts.name`, `customer_addresses.label` and
  `customer_addresses.address_line_1` cannot be blank.
- `customers.status` is `active`, `archived` or `deleted`, and status is
  `deleted` exactly when `deleted_time` is present.
- `customer_addresses.country_code` contains exactly two uppercase ASCII
  letters.
- `contacts.customer_id` and `customer_addresses.customer_id` use
  `ON DELETE CASCADE` for physical hard-delete cleanup/safety behavior.

Soft-delete propagation is not automatic in PostgreSQL. Application or service
logic must set `deleted_time` on scenario-owned rows when a scenario is
soft-deleted. The Customer Domain service must likewise soft-delete a Customer
and its active Contacts and Customer Addresses atomically.

---

# Important Indexes

The migration defines:

- active case-insensitive User email uniqueness
- exact identity uniqueness by `(issuer, subject)` and `(user_id, issuer)`
- OIDC transaction expiry and browser-binding hash indexes for cleanup and the
  per-browser live-flow cap
- application session User and absolute-expiry indexes
- active stable-key uniqueness for organisations, scenarios, org states, events, node types, edge types, graph nodes, graph edges and timeseries
- active case-insensitive organisation name uniqueness
- one active default metamodel
- one active metamodel per organisation
- metamodel version uniqueness for both default and organisation-specific metamodels
- scenario-local active stable-key uniqueness for graph nodes and graph edges
- scenario/lifetime lookup indexes for persistence-active graph nodes and edges
- one timeserie value per `(timeserie_id, date)`
- graph traversal indexes for source and target graph node lookups
- parent lookup indexes for common list views
- non-deleted customer lookup by status and case-insensitive name
- non-deleted contact lookup by customer and case-insensitive name
- non-deleted customer-address lookup by customer and case-insensitive label

---

# Future TBD Tables

The following candidate tables are retained as planned future work. They are not part of the core schema baseline migration yet.

| Table | Owning Domain | Notes |
| --- | --- | --- |
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
- paired as `NNN_name.sql` and `NNN_name.down.sql`

Run all pending migrations:

```bash
uv run --project backend python backend/migrate.py up
```

Only the latest applied migration can be rolled back, using its exact down
basename. Down migrations can destroy data and require a backup appropriate to
the target environment.

Databases whose schema predates migration tracking must be verified by an
operator and adopted with `baseline NNN`. The runner does not infer historical
migration state. ADR-002 defines history checksums, transactions, advisory
locking and rollback policy.

ADR-003 deploymentissa `up` ajetaan samalla immutable backend-imagella
one-shot release jobina ennen uuden backendin käynnistymistä. Epäonnistunut job
estää uuden backendin käynnistymisen. Onnistuneita forward-migraatioita ei
peruta automaattisesti deployment- tai application rollbackin yhteydessä.

Jokainen olemassa oleva staging- tai production-tietokanta tarkistetaan ja
backup otetaan ennen automaation käyttöönottoa. Jos ei-tyhjältä tietokannalta
puuttuu migraatiohistoria, operaattori varmistaa skeematason ja ajaa
`baseline NNN`:n eksplisiittisesti. Deployment ei päättele baseline-versiota.

---

# Init Script Policy

Database initialization scripts live in:

```text
db/init/
```

Init scripts are for local/dev bootstrap only unless explicitly documented otherwise.

Do not use `db/init/` as a replacement for migrations.

Current local/dev seed:

```text
db/init/002_seed_development_data.sql
```

The seed creates non-production bootstrap data only:

- one `Development Admin` user with `admin@example.local` when `users` is empty
- one active default metamodel when no active default metamodel exists
- node types, edge types, type attributes and allowed connections from `db/init/metamodel_state_##default##.json`

The default metamodel uses `metamodels.organisation_id = NULL` and stores the JSON root `version` field in `metamodels.version`.

The seed does not create identities, login transactions, sessions,
organisations, scenarios, org states, events, graph nodes, graph edges,
timeseries, timeserie values, customers, contacts or customer addresses.

Migration 009 assumes there is no retained User data at migration 008. It adds
required email directly, without a nullable transition or backfill. Disposable
local databases containing User rows must be reset before upgrading.

---

# Change Rules

When database schema changes:

1. Update `docs/data/DATABASE.md`.
2. Update `docs/data/DATA-MODEL.md` if logical model changes.
3. Update relevant domain and concept documents.
4. Add paired up and down migration scripts in `db/migrations/`.
5. Update init scripts only if local bootstrap needs them.
6. Update `docs/diagrams/db-physical-schema.puml`.
7. Regenerate `docs/diagrams/generated/db-physical-schema.svg`.
