# Database

Tämä dokumentti kuvaa järjestelmän fyysisen tietokantamallin ja tietokantakäytännöt.

Status: core, customer, authentication, Forecasting durable-request and
saved-version, and AI Domain MCP OAuth persistence schema defined. AI change
sets and billing still TBD.

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
db/migrations/010_create_prediction_schema.sql
db/migrations/011_alter_prediction_target_observation_source.sql
db/migrations/012_add_timeserie_short_name.sql
db/migrations/013_create_derived_metrics.sql
db/migrations/014_add_prediction_intervals.sql
db/migrations/015_create_prediction_requests.sql
db/migrations/016_add_prophet_result_kind.sql
db/migrations/017_create_mcp_oauth_schema.sql
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
| `timeseries` | Scenario-specific timeseries definitions | Supports `day`, `week`, `month`, `year` time units and nullable equation-safe `short_name`. |
| `timeserie_values` | Timeseries values by date | No `name` column; value is stored as `JSONB` with the public scalar under `value`; `is_derived` distinguishes materialized equation output. |
| `derived_metrics_equations` | Derived-metric formulas | One active formula per derived Timeserie, with internal referenced Timeserie IDs for recalculation and source short-name locking. |
| `prediction_versions` | Immutable named Forecasting executions | Organisation-local case-insensitive name and stable `prediction_key`; persists range, cutoff, selected 50--99 prediction-interval level and deterministic configuration. |
| `prediction_requests` | Durable mutable Forecasting request history | Stores an immutable submission snapshot, lifecycle/audit state, transient worker ownership, safe failure fields and an optional same-organisation completed-version link. |
| `prediction_targets` | Saved scenario/metric Forecasting targets | Stores stable target key, eligibility, seasonality and immutable target-source JSON snapshots; source scenario/metric IDs are snapshots, not FKs. |
| `prediction_model_results` | One result per target and selected model kind | `result_kind` is `naive`, `seasonal_naive`, `average`, `mlforecast`, `sarima` or `prophet` (migration 016); only the version's selected kinds have rows (ADR-014). Persists availability, safe ineligibility reason, cross-validation state, prediction-interval state/reason and configuration. |
| `prediction_points` | Dated numeric derived values | Owned by a Forecasting model result; nullable bounds are a complete finite interval pair enclosing the point value; never written to `timeserie_values`. |
| `customers` | Application-wide customer profiles | Status is `active`, `archived` or `deleted`; status and `deleted_time` must agree. |
| `contacts` | Customer-owned contacts | Name is required; email, phone and job title are optional. |
| `customer_addresses` | Customer-owned labelled addresses | Label, first address line and two-letter uppercase country code are required. |
| `mcp_oauth_clients` | Dynamically registered public MCP OAuth clients (ADR-015) | Unique `client_id`, trimmed self-declared `client_name` (1--100 characters), `redirect_uris` as a JSONB array of 1--10 URIs, created time and IP, throttled `last_used_time`, and `deleted_time` for stale-client soft deletion. |
| `mcp_oauth_authorization_requests` | Ten-minute pending authorization requests | Primary key is the SHA-256 request-id hash; holds client, redirect URI, `state`, S256 `code_challenge`, one scope and its resource. After consent it holds the deciding User, the 60-second code hash and expiry, the consumed time and the redeemed `grant_id`. |
| `mcp_oauth_grants` | One User's consent for one client, scope and MCP resource | Unique `grant_key`; exactly one scope (`schatten.read` or `schatten.write`) bound to the matching resource; non-null 30-day absolute `expires_time`; last used, revoked time and `revoked_by`. |
| `mcp_oauth_tokens` | Opaque MCP access and refresh tokens | Primary key is the SHA-256 token hash; `kind` is `access` or `refresh`; expiry, `replaced_by_hash` rotation link and `revoked_time`. |

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
- Runtime configuration enforces ten-minute login transactions, 30-minute idle
  sessions and an eight-hour absolute session maximum. Provider tokens, client
  secrets and raw session/pre-authentication cookie values have no columns and
  are never persisted.
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
- `derived_metrics_equations` is scenario-owned and soft-deletable; physical
  foreign-key cascades are cleanup behavior only.
- `timeseries.value_unit` is constrained to `number`, `string` or `boolean`.
- Active Timeserie names are unique after trimming and case-insensitive
  comparison within a scenario.
  Supplied active `timeseries.short_name` values are unique within a scenario;
  both constraints exclude soft-deleted rows.
- `prediction_versions.name` is non-blank and unique case-insensitively per
  organisation; its date range is ordered, cutoff mode is constrained and its
  integer `confidence_level` is from 50 through 99.
- `prediction_requests` constrains the six-state lifecycle together with
  start/finish, cancellation, worker, failure and completed-version fields.
  Its composite completed-version foreign key enforces organisation ownership.
  Partial ordered indexes support both global queued claiming and each
  organisation's active request list; a descending organisation index supports
  the bounded finished-history list.
  The migration creates no synthetic requests for old versions and its down
  migration removes request history only; workers must be stopped first.
- Prediction target/model/result-point rows are privately owned by the
  Forecasting Domain and cascade only from their own immutable version.
- Prediction source references are stable-key snapshots instead of FKs to
  scenarios or timeseries. Their source JSON records target-scenario-only
  effective observations per period, preserving auditability after a source
  soft delete.
- Prediction model kinds, eligibility and cross-validation statuses are
  constrained to the Forecasting Domain's approved values; point values and
  cross-validation MAE values must be finite, and MAE cannot be negative.
- Prediction interval statuses are constrained to `available`, `unavailable`
  or `not_applicable`. Point bounds are both null or both non-null; when
  present they are finite, ordered and enclose the finite point value.
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
- The `mcp_oauth_*` tables store no plaintext pending request id,
  authorization code or token. `request_id_hash`, `code_hash`, `token_hash` and
  `replaced_by_hash` are exactly 32 bytes (SHA-256). ADR-015 allows the
  plaintext pending request id only in the login transaction's `return_to`.
- `mcp_oauth_clients.client_id` is unique and non-blank. `client_name` is
  `NOT NULL` and 1 to 100 characters; trimming and ADR-015's ASCII allowlist
  are enforced by the registration service (TASK-069E). `redirect_uris` is a
  JSON array of 1 to 10 entries, stored exactly as validated.
- Grants and authorization requests hold exactly one scope:
  `scopes` is `schatten.read` or `schatten.write`, and the `resource` ends in
  the matching `/api/mcp/read` or `/api/mcp/write`. The exact canonical
  resource URI is validated by the application.
- `mcp_oauth_grants.expires_time` is non-null and after creation. It is the
  30-day absolute lifetime and is never extended, also not on grant reuse.
  `revoked_by` requires `revoked_time`.
- An authorization request's code hash and code expiry are set together and
  require the deciding `user_id`; `consumed_time` requires a code, and
  `grant_id` requires `consumed_time`. `code_challenge` is a 43-character
  base64url S256 challenge. Code hashes are unique.
- `mcp_oauth_tokens.kind` is `access` or `refresh`; only refresh tokens have a
  `replaced_by_hash`. A refresh token's `expires_time` is its 7-day idle
  timeout capped at the grant's `expires_time`; the cap is enforced by the
  token service because it spans tables.
- Foreign keys to `users` are plain audit references without a delete rule,
  as for other audit columns; Users are soft-deleted.
- `mcp_oauth_tokens.grant_id` is `ON DELETE CASCADE`, and
  `mcp_oauth_authorization_requests.grant_id` is `ON DELETE SET NULL`, so lazy
  cleanup of a revoked or expired grant removes its tokens and never fails on a
  redeemed request. The client foreign keys of authorization requests and
  grants are `ON DELETE RESTRICT`: cleanup hard-deletes a soft-deleted client
  only after no authorization request or grant references it.
- **Refresh-token retention.** Replaced refresh-token rows (hash,
  `replaced_by_hash` and expiry) are kept until their grant expires or is
  revoked and the grant row is deleted, which cascades to them. Lazy cleanup
  deletes expired access tokens but never a refresh token of an active grant,
  because ADR-015's refresh-token reuse detection depends on these rows.

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
- active scenario-local case-insensitive Timeserie name uniqueness and
  active scenario-local Timeserie short-name uniqueness when supplied
- active case-insensitive organisation name uniqueness
- one active default metamodel
- one active metamodel per organisation
- metamodel version uniqueness for both default and organisation-specific metamodels
- scenario-local active stable-key uniqueness for graph nodes and graph edges
- scenario/lifetime lookup indexes for persistence-active graph nodes and edges
- one timeserie value per `(timeserie_id, date)`
- one active derived equation per derived Timeserie and active scenario/formula-reference lookups
- graph traversal indexes for source and target graph node lookups
- parent lookup indexes for common list views
- non-deleted customer lookup by status and case-insensitive name
- non-deleted contact lookup by customer and case-insensitive name
- non-deleted customer-address lookup by customer and case-insensitive label
- prediction version key and organisation-local case-insensitive name uniqueness
- prediction request key, FIFO queued-work, organisation finished-history and
  case-insensitive active-name indexes; cancelled/failed history is excluded
  from active-name uniqueness
- prediction target version and prediction point result/date lookup indexes
- MCP OAuth lookups: unique `client_id`, `grant_key` and code hash; hash
  primary keys for pending requests and tokens; grants by User and by
  `(client, user, resource)` for grant reuse; tokens by grant; authorization
  requests by client and by redeemed grant
- MCP OAuth lazy-cleanup indexes: authorization request, grant and access-token
  `expires_time`; revoked grants; non-deleted clients by
  `COALESCE(last_used_time, created_time)`; soft-deleted clients

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
| ai_classifications | AI Domain (unplanned document-AI candidate) | AI classification outputs; outside ADR-015's scope, no task |
| ai_summaries | AI Domain (unplanned document-AI candidate) | AI summary outputs; outside ADR-015's scope, no task |
| ai_extractions | AI Domain (unplanned document-AI candidate) | AI extraction outputs; outside ADR-015's scope, no task |

The AI Domain's MCP OAuth tables (`mcp_oauth_*`) are created by migration 017
(TASK-069D) and listed under Core Tables. The accepted change-set tables
(`ai_change_sets`, `ai_change_set_operations`) are described in
`docs/data/DATA-MODEL.md` and ADR-015, and are added by TASK-069I.

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

Olemassa oleva production-tietokanta tarkistetaan ja backup otetaan ennen
automaation käyttöönottoa. Jos ei-tyhjältä tietokannalta
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

Its metamodel insertion logic is shared with the approved production command in:

```text
db/init/001_seed_reference_data.sql
db/init/metamodel_state_##default##.json
```

The seed creates non-production bootstrap data only:

- active `Development Consultant` (`consultant@example.local`) and `Development
  Admin` (`admin@example.local`) users when their active emails are absent;
  these match the local Authentik fixtures
- one active default metamodel when no active default metamodel exists
- node types, edge types, type attributes and allowed connections from `db/init/metamodel_state_##default##.json`

The default metamodel uses `metamodels.organisation_id = NULL` and stores the JSON root `version` field in `metamodels.version`.

The seed does not create identities, login transactions, sessions,
organisations, scenarios, org states, events, graph nodes, graph edges,
timeseries, timeserie values, customers, contacts or customer addresses.

After migrations, the production backend image exposes the explicit database-only
`python -m app.seed_reference_data` command. Both it and the development wrapper
supply the same JSON through a transaction-local PostgreSQL setting and execute
the same advisory-lock-serialized SQL. The production command inserts no Users or
business data, preserves an existing active default unchanged, and is never an
API/worker startup hook. This is reference-data initialization, not a migration.

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
