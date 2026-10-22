# AI Domain

Status: accepted design in ADR-015; implementation pending TASK-069B through
TASK-069O. Nothing in this document is runtime behaviour yet.

## Purpose

AI Domain hallitsee sitä, miten käyttäjän oma AI-asiakas (esimerkiksi Claude
Desktop, claude.ai tai Claude Code) käyttää Schattenia MCP:n kautta, ja sitä,
miten AI:n ehdottamat muutokset päätyvät ihmisen hyväksymänä business-dataan.

AI Domain owns:

- the OAuth 2.1 authorization server data for MCP clients (clients, pending
  authorization requests, grants and tokens);
- AI change sets: staged, typed operations proposed by an AI client and
  applied or rejected by a human in Schatten; and
- the deterministic timeseries generator contract used by previews and change
  sets.

Schatten never calls an LLM and never stores LLM keys. The chat happens in the
user's own MCP client on the user's own AI subscription.

AI Domain is not the source of truth for any business data. Business data
created through a change set is owned by Organisation States and Organisation
Twin Structure exactly as if it had been created through REST.

The architecture is documented in
[ADR-015](../decisions/ADR-015-ai-via-mcp.md) and the LikeC4 model in
`docs/diagrams/likec4/schatten-ai-mcp/`:

- [System context](../diagrams/generated/likec4-index.png)
- [Containers](../diagrams/generated/likec4-schattenContainers.png)
- [Backend components](../diagrams/generated/likec4-backendComponents.png)
- [Production MCP deployment](../diagrams/generated/likec4-productionMcp.png)
- [Development MCP deployment](../diagrams/generated/likec4-developmentMcp.png)
- [Connect flow](../diagrams/generated/likec4-connectFlow.png)
- [Generate flow](../diagrams/generated/likec4-generateFlow.png)

---

# Responsibilities

Owns:

- MCP OAuth clients, authorization requests, grants and tokens
- AI change sets and their operations
- the timeserie generation specification and generator version
- AI skills content and MCP prompts

Provides:

- MCP read service `/api/mcp/read` (scope `schatten.read`)
- MCP write service `/api/mcp/write` (scope `schatten.write`), which only
  stages draft change sets
- OAuth discovery, registration, authorization, token and revocation endpoints
- consent and connections APIs for the SPA
- change-set review API for the Metrics tab (apply, reject)
- deterministic generated-timeserie previews and frozen values

Does NOT Own:

- users, roles, identities or browser sessions (Users Domain)
- scenarios, org states, events, timeseries, timeserie values or derived
  metrics (Organisation States Domain)
- metamodels, graph nodes or graph edges (Organisation Twin Structure Domain)
- prediction requests or versions (Forecasting Domain)
- LLM inference, prompts sent to an LLM or LLM credentials

---

# Domain Rules

## Rule 1: No MCP Tool Applies Changes

The MCP write service creates, edits, validates, submits and discards draft
change sets only. No MCP tool, prompt or resource applies a change set or
writes another domain's data. **A human apply in Schatten is always required.**

## Rule 2: Human Review In Schatten

Apply and reject happen only through cookie-session endpoints with the session
CSRF token and exact Origin, used by the Metrics tab AI panel. Both `admin`
and `consultant` may review, including the creator. The reviewer is the actor
for the business rows the apply creates.

## Rule 3: Change Sets Use Domain Services

A change set executes operations only through the owning domains'
`*_in_transaction` service cores. It never writes `scenarios`, `org_states`,
`events`, `timeseries`, `timeserie_values`, `derived_metrics_equations`,
`graph_nodes` or `graph_edges` directly. Domain validation, audit columns and
derived-metric recalculation therefore match REST.

## Rule 4: Dry-Run Always Rolls Back, Apply Is Atomic

Validation runs the operations in order in a fresh session guarded against
commit and always rolls back. Without SAVEPOINTs it stops at the first failing
operation: later operations report `not_run`. Apply locks the change set,
requires `submitted`, checks the `reviewFingerprint`, re-validates, executes
all operations in one transaction and commits once.

- Any error before re-validation, in the lock, status or fingerprint steps,
  aborts without changing anything and never writes `failed`. These are:
  - the terminal `409` for a change set that is not `submitted`;
  - `409 review_stale`;
  - the retryable `409 apply_in_progress` when the lock is not acquired within
    the short `lock_timeout`;
  - a retryable `503` for any other error in these steps, including a
    statement timeout during the fingerprint recomputation or a status-check
    error.

  A stale review leaves the change set `submitted`.
- The step alone decides whether the status changes. Only a re-validation,
  operation or commit failure, or a lock or statement timeout during
  re-validation or execution, rolls everything back and then marks the change
  set `failed`, through a conditional update that changes only a
  still-`submitted` change set.

Re-validation checks validity against current data, not general staleness.
Apply can overwrite values a human changed after submit, as the same REST call
would.
The review UI therefore flags every operation that replaces existing values
(`replaces_existing`) and shows what it replaces.

The flags are recomputed against current data whenever the review detail is
read. The baseline is data that existed before the change set, so operations
on rows the same change set creates are never flagged. Apply must return the
review's `reviewFingerprint`, a hash of the flags, the summaries and a
per-target checksum of each flagged target's current data, and recomputes it
in its locked transaction. If the flagged summaries or any flagged target's
data changed after the review was loaded, apply fails with `409 review_stale`
and the reviewer must confirm again. A REST commit between apply's own
recomputation and its writes is an accepted short window, because target rows
are not locked.

## Rule 5: Generated Values Are Deterministic And Frozen

The AI chooses generator parameters, never the values. The generator is
deterministic for a spec and seed. Generated values are frozen with the
generator version at submit, and apply uses the frozen values.

## Rule 6: Same People, Roles And Login

An MCP token belongs to an existing User and is issued only after that User
signs in with the existing Entra login and approves consent. Every MCP request
re-reads the User and role; effective scopes are the grant's scopes
intersected with the role's allowed scopes. Both current roles have both
scopes. The Entra registration does not change.

A grant is bound to one MCP resource and its single scope, and a token works
only at that resource. A grant lives at most 30 days, and refresh tokens expire
after 7 days without use. That is longer than ADR-004's browser sessions and
has no Entra re-check, which ADR-015 accepts as a trade-off. Offboarding must
therefore soft-delete the Schatten User or revoke the User's grants; disabling
the Entra account alone does not end MCP access.

## Rule 7: Secrets Are Hashed And Never Logged

In the `mcp_oauth_*` tables, pending request ids, authorization codes, access
tokens and refresh tokens are stored only as SHA-256 hashes. Tokens, codes,
request ids and tool arguments are never logged; ADR-015's "Pending Request Id
Handling" names the Caddy and backend log filters, and no URL path carries a
request id.

## Rule 8: No Background Work

All MCP work is short and synchronous. AI Domain adds no worker, queue or
scheduler and never uses the prediction worker. Expired OAuth rows are cleaned
up lazily during token and registration operations. Replaced refresh tokens
of an active grant are kept for reuse detection.

## Rule 9: Data Leaves Schatten By User Choice

Business data read through MCP flows to the user's AI vendor. Consent text
must say so, and users can grant read only and revoke grants.

---

# Database Ownership

Planned tables (not migrated yet):

| Table | Task | Purpose |
| --- | --- | --- |
| `mcp_oauth_clients` | TASK-069D | Dynamically registered public clients and their allowlisted redirect URIs |
| `mcp_oauth_authorization_requests` | TASK-069D | Pending authorization requests and one-time codes, stored by hash |
| `mcp_oauth_grants` | TASK-069D | A User's consent for one client, one scope and its resource, with a 30-day expiry |
| `mcp_oauth_tokens` | TASK-069D | Hashed access and refresh tokens with rotation and revocation |
| `ai_change_sets` | TASK-069I | Change-set header, status, derived scenario reference, creator, grant, copied `client_id`, client name, review and results |
| `ai_change_set_operations` | TASK-069I | Ordered typed operations, refs, frozen values and errors |

Deleting a revoked or expired grant during lazy cleanup cascades to its
tokens. It sets `ai_change_sets.grant_id` and
`mcp_oauth_authorization_requests.grant_id` to null, so change-set history is
kept with `created_by`, a copied `client_id` and `client_name` as its audit
record. Stale clients are soft-deleted, then hard-deleted once no authorization
request or grant references them. Authorize locks the client row at its
initial check and updates its `last_used_time` only after the request has been
fully validated and stored. Cleanup skips locked clients.

Owned exclusively by AI Domain. Other domains do not read or write them; the
Users Domain is referenced for User foreign keys and audit columns.

---

# API Ownership

Public OAuth endpoints (outside `/api/v1`, rate-limited, `no-store`):

```text
GET  /.well-known/oauth-authorization-server
GET  /.well-known/oauth-protected-resource/api/mcp/read
GET  /.well-known/oauth-protected-resource/api/mcp/write
POST /api/oauth/register
GET  /api/oauth/authorize
POST /api/oauth/token
POST /api/oauth/revoke
```

MCP endpoints (bearer token only, never the session cookie):

```text
GET|POST|DELETE /api/mcp/read     scope schatten.read
GET|POST|DELETE /api/mcp/write    scope schatten.write
```

Cookie-session APIs (`/api/v1`, business session; unsafe methods need CSRF
and exact Origin):

```text
GET    /api/v1/ai/oauth/consent?request=<id>
POST   /api/v1/ai/oauth/consent/approve          body {"request": "<id>"}
POST   /api/v1/ai/oauth/consent/deny             body {"request": "<id>"}
GET    /api/v1/ai/connections
DELETE /api/v1/ai/connections/{grant_key}
POST   /api/v1/ai/users/{user_id}/connections/revoke    admin only
GET    /api/v1/ai/skills/{name}.zip
GET    /api/v1/organisations/{organisation_key}/ai/change-sets
GET    /api/v1/organisations/{organisation_key}/ai/change-sets/{change_set_key}
POST   /api/v1/organisations/{organisation_key}/ai/change-sets/{change_set_key}/apply
POST   /api/v1/organisations/{organisation_key}/ai/change-sets/{change_set_key}/reject
```

With `MCP_ENABLED=false` (the default):

- the MCP endpoints, the public OAuth endpoints, the consent API and the skill
  zip download are not registered and return 404 (TASK-069E, TASK-069F,
  TASK-069G, TASK-069N);
- the connections API, the admin per-user revocation and the change-set
  review API stay registered, so grants can be revoked and staged change sets
  reviewed while MCP is disabled (TASK-069F, TASK-069K); and
- the session response's `features.mcp` is `false`, and the SPA hides the
  consent page, connect instructions and skill links (TASK-069L, TASK-069M,
  TASK-069N).

The incident procedure (disable MCP, then revoke affected Users' grants) and
the offboarding rule (soft-delete the User or revoke the User's grants) are in
ADR-015.

## MCP Tools

Read service (`readOnlyHint`, `idempotentHint`, `openWorldHint=False`):

```text
whoami
list_organisations
list_scenarios(organisation_key)
list_org_states(organisation_key, scenario_key)
get_type_catalog(organisation_key, scenario_key)
get_graph(organisation_key, scenario_key, org_state_key)
list_timeseries(organisation_key, scenario_key, include_values=False)
get_timeserie(organisation_key, scenario_key, timeserie_key, from_date, to_date)
list_events(organisation_key, scenario_key)
preview_generated_timeserie(spec)
list_change_sets(organisation_key, status, scenario_key)
get_change_set(change_set_key)
```

Read service MCP prompts: `model_building`, `timeseries_generation`.

Write service (`openWorldHint=False`):

```text
create_change_set(organisation_key, title, rationale)
add_operations(change_set_key, operations)
remove_operation(change_set_key, position)       destructiveHint
validate_change_set(change_set_key)              idempotentHint
submit_change_set(change_set_key)
discard_change_set(change_set_key)               destructiveHint
```

There is no apply tool.

---

# Timeserie Generation Specification

`TimeserieGenerationSpec` (TASK-069C) is numeric-only and validated:

- `start_date`, and exactly one of `periods` or `end_date`
- `time_unit`: `day|week|month|year`; the start date must be aligned (Monday,
  first of month, 1 January)
- `base_level`
- `trend`: `none|linear|percent|logistic` with its parameters
- `seasonality[]`: period, amplitude, `additive|multiplicative`
- `noise`: `std` or `relative_std`, optional `ar1`
- `level_shifts[]`: date and delta
- optional `clamp_min`, `clamp_max`
- `decimals`
- `seed`

The generator uses `numpy.random.default_rng(seed)`, produces at most 20,000
points and records `GENERATOR_VERSION`. TASK-069C documents the exact version
here when implemented.

---

# Dependencies

Depends On:

- Users Domain for Users, roles, the Entra login and session/CSRF guard
- Organisations Domain for the organisation of a change set
- Organisation States Domain service cores for scenarios, org states, events,
  timeseries, values and derived metrics
- Organisation Twin Structure Domain service cores and type catalog for graph
  nodes and edges

Referenced By:

- None. Other domains do not depend on AI Domain.

---

# Common Workflows

## Connect An AI Client

1. The MCP client calls an MCP endpoint, receives 401 with resource metadata
   and discovers the authorization server.
2. It registers dynamically with an allowlisted redirect URI.
3. The browser opens `/api/oauth/authorize`; Schatten stores a hashed pending
   request and redirects to the SPA consent page.
4. An anonymous user signs in with the existing Entra login.
5. The user approves or denies; approval returns a one-time code to the
   client's redirect URI.
6. The client exchanges the code with its PKCE verifier for an access and a
   refresh token.

## Generate A Model And Timeseries

1. The AI reads the type catalog, graph and existing timeseries.
2. It previews generator specs.
3. It creates a change set and adds operations. Server-generated keys are
   referenced with `$ref`, and client-supplied node, edge and timeserie keys
   verbatim. It validates, fixes errors and submits. Generated values are
   frozen.
4. The AI gives the user the review URL.
5. A human reviews the change set in the Metrics tab, which flags operations
   that replace existing values, and applies or rejects it. Apply creates the
   business rows atomically.

---

# AI Agent Guidance

When implementing AI Domain features:

- read ADR-015 and `docs/concepts/AI_CHANGE_SET.md`;
- keep MCP code in `backend/app/mcp/`, OAuth code in
  `backend/app/api/v1/mcp_oauth/`, change sets in
  `backend/app/api/v1/ai_change_sets/`, the generator in
  `backend/app/api/v1/timeserie_generation/` and UI in `frontend/src/features/ai/`;
- reuse domain service functions and response schemas; call the
  `*_in_transaction` cores for change-set execution;
- write precise tool docstrings, because they are the LLM-facing contract.

Avoid:

- adding an apply tool or any MCP write to business tables;
- calling an LLM or storing LLM credentials;
- adding background workers, queues or schedulers;
- logging tokens, codes, request ids or tool arguments;
- changing the Entra registration.

---

# Unplanned Candidate: Document AI

Status: unplanned candidate, outside ADR-015's scope.

Before ADR-015 this document described a candidate AI Domain for document
classification, summarization and structured extraction
(`ai_classifications`, `ai_summaries`, `ai_extractions`; `/ai/classify`,
`/ai/extract`, `/ai/summarize`; see `docs/concepts/AI_EXTRACTION.md`). It
depended on the candidate Customer and Document domains. That idea is
retained as an unplanned candidate. It is not part of the MCP feature, has no
task, and would need its own plan and ADR, in particular because ADR-015
decides that Schatten itself does not call an LLM.

---

# Open Questions

- Client ID Metadata Documents support instead of, or next to, Dynamic Client
  Registration.
- More operation types (edge and event patches, deletions) when needed.
- A future role limited to `schatten.read`.
- Retention of terminal change sets and their frozen values.
