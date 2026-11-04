# Data Model

Tämä dokumentti kuvaa järjestelmän loogisen datamallin.

Status: core, customer and Forecasting durable-request/saved-version models
defined. The AI Domain's MCP OAuth entities (TASK-069D, migration 017, with
the single MCP resource of TASK-074, migration 020) and change-set entities
(TASK-069I, migration 018, with the review channel of TASK-069O, migration
019) are migrated. Billing remains TBD.

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
| Derived Metric Equation | Scenario-owned formula defining one derived numeric Timeserie. |
| Prediction Request | Mutable, organisation-owned durable request with a frozen calculation snapshot and retained terminal history. |
| Prediction Version | Immutable, organisation-owned named execution with its cutoff, selected nominal prediction-interval level and model configuration snapshot. |
| Prediction Target | One target scenario and metric in a saved version, including effective-observation/source snapshots and metric eligibility. |
| Prediction Model Result | One persisted requested output kind with eligibility, cross-validation and prediction-interval availability metadata. |
| Prediction Point | One dated numeric value belonging to a model result, with an optional complete lower/upper prediction-interval pair. |
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
- Authentication configuration, provider tokens and Entra/Authentik resources
  are not logical entities. A session is bounded by a 30-minute idle timeout
  and fixed eight-hour absolute expiry; exact `(issuer, subject)` remains the
  durable link after guarded email-based first discovery.
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
- Scenario copy creates independent active event and timeserie rows in the
  target scenario. The selected source organisation state's `target_date` is
  the inclusive cutoff for copied events and timeserie values; every active
  source timeserie is copied even when it has no qualifying value.
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
- A derived metric equation belongs to one scenario and one derived Timeserie.
  It references normal numeric Timeseries in the same scenario by their locked
  short names. Derived values are materialized only for the referenced-value
  date intersection and are marked `is_derived`.
- An active Timeserie name is unique after trimming and case-insensitive
  comparison within its scenario.
  An optional `short_name` is an equation-safe identifier and is unique within
  its active scenario when present; both values are reusable after soft delete.
- Active timeserie values must use dates that are valid starts for the owning
  timeserie's time unit and typed values that match the owning timeserie's value
  unit.
- A normal Timeserie value replacement recalculates all active derived metrics
  that reference it. Derived Timeserie values are never manually replaced.
- Graph nodes may reference primary and secondary timeseries owned by the same
  scenario.
- Scenario copy remaps copied graph-node timeserie references to the matching
  copied target-scenario timeseries.
- A Prediction Request belongs to one organisation and has a stable request key,
  immutable submission snapshot, state, submitter, optional cancellation actor,
  worker ownership, safe failure information and optional completed Prediction
  Version. Existing versions have no synthesized historical request.
- A Prediction Request state is one of `queued`, `running`, `cancelling`,
  `completed`, `cancelled` or `failed`. Queued requests survive restarts;
  interrupted running work fails and abandoned cancelling work is cancelled,
  without automatic retry.
- A Prediction Version belongs to one organisation; its name is case-insensitively
  unique within that organisation and is never updated or overwritten. Active
  Prediction Requests reserve names too; cancelled and failed request history
  releases them. Publication/cancellation serialization permits either a
  completed version or a cancelled request, never a partial version.
- A Prediction Version records one integer prediction-interval level from 50
  through 99, defaulting to 80. Its configuration snapshot records the selected
  level and supported model interval methods.
- A Prediction Version owns Prediction Targets; each target owns exactly one result
  for every result kind selected for the version, and a result owns dated
  Prediction Points. The non-empty selection is frozen into the request snapshot
  and recorded as `modelKinds` in the version's configuration snapshot (ADR-014);
  an unselected kind has no result. A version without `modelKinds` predates
  ADR-014, and its kinds are the kinds of its saved results.
- Prediction Targets retain stable target keys and source and input JSON
  snapshots rather than source-table foreign keys. The source snapshot records
  target-scenario-only effective observations, so source soft deletion cannot
  make saved forecasts unreadable.
- A Prediction Model Result records whether its interval is available,
  unavailable with a safe reason, or not applicable. Available intervals are
  complete: every Prediction Point has finite ordered bounds containing its
  value; otherwise every bound is null.
- Forecasting reads only the selected target scenario's values, graph history
  and events; it does not own or write Scenario, Timeserie or Timeserie Value
  rows.
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

# AI Domain Entities

ADR-015 accepts these logical entities. The four MCP OAuth tables are created
by TASK-069D (`017_create_mcp_oauth_schema`), and TASK-074
(`020_alter_mcp_oauth_single_resource`) restricts their grants and
authorization requests to the one MCP resource. The two change-set tables are
created by TASK-069I (`018_create_ai_change_sets`). Both are described in
`docs/data/DATABASE.md` and the physical diagram.

| Entity | Table | Notes |
| --- | --- | --- |
| MCP OAuth Client | `mcp_oauth_clients` | Dynamically registered public client with a unique `client_id`, bounded self-declared name and allowlisted redirect URIs; soft-deleted when stale, then hard-deleted once unreferenced. |
| MCP Authorization Request | `mcp_oauth_authorization_requests` | Ten-minute pending authorization request keyed by request-id hash, with PKCE challenge, scopes (`schatten.read` or both), resource, state and redirect URI; after approval it holds the deciding User and a 60-second single-use code hash; after denial it holds only the deciding User. |
| MCP Grant | `mcp_oauth_grants` | One User's consent for one client and the MCP resource, with `schatten.read` or both scopes and a 30-day absolute expiry; revocable. |
| MCP Token | `mcp_oauth_tokens` | Opaque access or refresh token keyed by SHA-256 hash, with expiry, rotation link and revocation. |
| AI Change Set | `ai_change_sets` | Organisation-owned staged proposal with status, optional derived scenario reference, creator, grant, copied `client_id`, client name, validation and applied results, and review fields, including the review channel and reviewing MCP client (migration 019). |
| AI Change Set Operation | `ai_change_set_operations` | Ordered typed operation with a stable position, an optional `$ref` symbol for the server-generated key it creates, payload, frozen generated values and generator version, and its latest error. |

Relationship rules:

- An MCP OAuth Client has many Authorization Requests and Grants.
- A Grant belongs to one User and one Client and has many Tokens. It holds
  `schatten.read` or `schatten.read schatten.write` and is bound to the one
  MCP resource `<PUBLIC_ORIGIN>/api/mcp`, so one Grant covers read and write.
  Its tokens are accepted only by that resource and carry no scope of their
  own. A reused Grant takes the scopes of the newest consent. Until migration
  020 (TASK-074) a Grant held exactly one scope and was bound to that scope's
  resource, `/api/mcp/read` or `/api/mcp/write`; migration 020 deleted those
  Grants with their Tokens.
- A Grant's `expires_time` is 30 days after creation and is never extended. A
  re-authorization reuses only an active Grant and revokes its earlier Tokens.
  No Token expires after its Grant.
- A Token's `kind` is `access` or `refresh`. A rotated refresh token
  references its replacement. Reuse of a replaced refresh token revokes the
  Grant and all its Tokens.
- The `mcp_oauth_*` tables store no plaintext request id, code or token, only
  SHA-256 hashes. (ADR-015 allows the pending request id inside the existing
  login transaction's `return_to` for up to ten minutes.)
- Grant revocation, User soft deletion or Token expiry ends MCP access on the
  next request. The effective scopes are the Grant's scopes intersected
  with the scopes allowed for the User's current role; each MCP tool and
  prompt checks its own scope against them.
- An AI Change Set belongs to one Organisation and one creating User, and
  owns ordered Operations unique by position and by `ref`. Its reference to the
  staging Grant is nullable (`ON DELETE SET NULL`). When lazy cleanup deletes
  a revoked or expired Grant, or migration 020 deleted a Grant on a former
  resource, the change set keeps `created_by`, a copied
  `client_id` (a plain value, not a foreign key) and `client_name` as its audit
  record. Change-set history is never deleted.
  Its optional Scenario reference is derived from the Operations whenever
  they are added or removed: it is set only when all of them target the same
  existing Scenario, and null when the change set creates or copies a
  Scenario or touches several.
- An Operation's position stays stable when another Operation is removed. A
  `ref` names only a key the server generates (a created or copied Scenario,
  an Organisation State, an Event or a Derived Metric) and is used only by
  later Operations; Graph Node, Graph Edge and Timeserie keys are
  client-supplied and repeated verbatim.
- An AI Change Set's status is one of `draft`, `submitted`, `applied`,
  `rejected`, `failed` or `discarded`; only humans move `submitted` change
  sets to `applied` or `rejected`, in the Metrics tab (`web`) or by approving
  an MCP client's call (`mcp`). The review records that channel and, for
  `mcp`, the reviewing client.
- An applied AI Change Set creates or patches Scenario, Organisation State,
  Event, Timeserie, Timeserie Value, Derived Metric Equation, Graph Node and
  Graph Edge rows only through the owning domains' services. Those rows have no
  foreign key to the change set; the change set's `applied_result` records the
  created keys.
- Lazy cleanup during token and registration operations deletes expired
  authorization requests, expired access tokens, and revoked or expired Grants
  with their Tokens (cascade). It soft-deletes (`deleted_time`) Clients without
  an active Grant and unused for 30 days, counting fully validated
  authorization requests as use. It then hard-deletes soft-deleted Clients that
  no Authorization Request or Grant references. Replaced refresh Tokens of an
  active Grant are kept, because reuse detection depends on them. An
  Authorization Request's reference to the Grant its code was redeemed for is
  nullable (`ON DELETE SET NULL`).

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
- `prediction_key`
- `prediction_request_key`
- `grant_key` (migration 017) and `change_set_key` (migration 018)

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
| AIExtraction | AI Domain | `docs/concepts/AI_EXTRACTION.md` | Unplanned document-AI candidate outside ADR-015's scope |

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
