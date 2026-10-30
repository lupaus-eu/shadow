# AI Domain

Status: accepted design in ADR-015; TASK-069B (the domain service transaction
cores this domain will use), TASK-069C (the deterministic timeseries
generator), TASK-069D (the MCP OAuth schema), TASK-069E (OAuth discovery,
client registration, the authorization request and the consent API, see
[MCP OAuth Authorization](#mcp-oauth-authorization-task-069e)), TASK-069F
(tokens, refresh rotation, revocation, `verify_access_token` and the
connections API, see
[MCP OAuth Tokens And Connections](#mcp-oauth-tokens-and-connections-task-069f)),
TASK-069G (the MCP read and write endpoints, bearer authentication,
resource protection and the first read tools, see
[MCP Servers (TASK-069G)](#mcp-servers-task-069g)), TASK-069H (the
remaining read tools and the generator preview, see
[MCP Read Tools (TASK-069H)](#mcp-read-tools-task-069h)), TASK-069I (the
change-set schema and engine, see
[AI Change-Set Engine (TASK-069I)](#ai-change-set-engine-task-069i)) and
TASK-069J (the change-set staging write tools and change-set read tools, see
[MCP Write Tools (TASK-069J)](#mcp-write-tools-task-069j)), TASK-069K (the
cookie-session review API, see
[Change-Set Review API (TASK-069K)](#change-set-review-api-task-069k)) and
TASK-069L (the SPA consent page, the connections list and the admin per-user
revocation action, see
[Consent Page And Connections UI (TASK-069L)](#consent-page-and-connections-ui-task-069l))
and TASK-069M (the Metrics tab AI panel, see
[Metrics Tab AI Panel (TASK-069M)](#metrics-tab-ai-panel-task-069m))
and TASK-069N (the skills, the Claude Code plugin, the MCP prompts and the
skill zips, see
[Skills And Distribution (TASK-069N)](#skills-and-distribution-task-069n))
and TASK-069O (the MCP change-set review of the 2026-10-29 ADR-015
amendment, see [MCP Change-Set Review (TASK-069O)](#mcp-change-set-review-task-069o))
are implemented and the rest is pending TASK-069P. The MCP endpoints, the
public OAuth endpoints, the consent API and the skill zip download are
registered only with `MCP_ENABLED=true`, which is off by default and in
production; the connections and change-set review APIs are always registered.
The MCP apply and reject tools are registered only with
`MCP_CHANGE_SET_REVIEW_ENABLED=true` as well, also off by default and in
production.

## Purpose

AI Domain hallitsee sitä, miten käyttäjän oma AI-asiakas (esimerkiksi Claude
Desktop, claude.ai tai Claude Code) käyttää Schattenia MCP:n kautta, ja sitä,
miten AI:n ehdottamat muutokset päätyvät ihmisen hyväksymänä business-dataan:
Schattenin Metrics-välilehdellä tai ihmisen hyväksymällä MCP-klientin
kutsulla.

AI Domain owns:

- the OAuth 2.1 authorization server data for MCP clients (clients, pending
  authorization requests, grants and tokens);
- AI change sets: staged, typed operations proposed by an AI client and
  applied or rejected by a human, in Schatten or by approving the AI client's
  call; and
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
- MCP write service `/api/mcp/write` (scope `schatten.write`), which stages
  draft change sets and, with `MCP_CHANGE_SET_REVIEW_ENABLED`, applies or
  rejects submitted ones on the human's approval
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

## Rule 1: Only A Human-Approved Apply Changes Business Data

The MCP staging tools create, edit, validate, submit and discard draft change
sets only. Only `apply_change_set`, registered with
`MCP_CHANGE_SET_REVIEW_ENABLED=true`, applies a change set through MCP, and
only through the engine's apply. No other MCP tool, prompt or resource applies
or rejects a change set or writes another domain's data. **A human decision is
always required** (Rule 2).

## Rule 2: Human Review In Schatten Or In The AI Client

A human applies or rejects each submitted change set in one of two ways:

- in the Metrics tab AI panel, through cookie-session endpoints with the
  session CSRF token and exact Origin; or
- with `MCP_CHANGE_SET_REVIEW_ENABLED=true`, by approving the MCP client's
  `apply_change_set` or `reject_change_set` call. Apply needs the
  `review_fingerprint` of `get_change_set_review`.

Both `admin` and `consultant` may review any submitted change set, including
its creator. The reviewer is the actor for the business rows the apply
creates, and every review records its channel (`web` or `mcp`, with the
reviewing MCP client).

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
must say so, and users can grant read only and revoke grants. With MCP
change-set review on, the write consent also says that the client can apply
and reject change sets on the User's behalf.

---

# Database Ownership

The `mcp_oauth_*` tables are created by migration
`017_create_mcp_oauth_schema` (TASK-069D); their SQLAlchemy models are in
`backend/app/api/v1/mcp_oauth/models.py`. The change-set tables are created by
migration `018_create_ai_change_sets` (TASK-069I); their models are in
`backend/app/api/v1/ai_change_sets/models.py`.

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
- the session response's `features.mcp` is `false` (TASK-069E); the SPA
  consent page then shows a "not available" state without calling the
  consent API (TASK-069L), and the connect instructions and skill links are
  hidden (TASK-069M, TASK-069N). The connections list and the admin
  "Revoke AI connections" action do not depend on the flag, and the Metrics
  tab AI panel is then offered only when the organisation has change sets or
  the User has connections (TASK-069M).

## MCP OAuth Authorization (TASK-069E)

The code is in `backend/app/api/v1/mcp_oauth/`: `service.py`, `router.py`
(public endpoints), `consent_router.py` (cookie-session consent API) and
`schemas.py`. `create_app()` includes both routers only when `MCP_ENABLED` is
true. Settings are in `backend/app/core/config.py` and documented in
`docs/DEPLOYMENT.md` and `docs/LOCAL-DEVELOPMENT.md`.

Public endpoints return RFC 6749 JSON errors
(`{"error": ..., "error_description": ...}`) and `Cache-Control: no-store`:

- `GET /.well-known/oauth-authorization-server` (RFC 8414): issuer
  `PUBLIC_ORIGIN`, the authorize, token, registration and revocation
  endpoints, scopes `schatten.read` and `schatten.write`, response type
  `code`, grant types `authorization_code` and `refresh_token`, auth method
  `none`, code challenge method `S256` and
  `authorization_response_iss_parameter_supported: true`. The token and
  revocation endpoints are implemented by TASK-069F (see
  [below](#mcp-oauth-tokens-and-connections-task-069f)).
- `GET /.well-known/oauth-protected-resource/api/mcp/{read,write}` (RFC 9728):
  resource `<PUBLIC_ORIGIN>/api/mcp/<server>` with no trailing slash, the
  authorization server `PUBLIC_ORIGIN`, the server's single scope and bearer
  method `header`.
- `POST /api/oauth/register` (RFC 7591) answers `201` with `client_id` (a
  random 256-bit value), `client_id_issued_at`, the trimmed `client_name`,
  the de-duplicated `redirect_uris`, the grant and response types and
  `token_endpoint_auth_method: none`. The body is at most 64 KiB of JSON.
  Errors:
  - `invalid_client_metadata`: a body that is not a JSON object, an auth
    method other than `none`, a missing or disallowed `client_name` (ADR-015's
    ASCII allowlist after trimming edge spaces), or `redirect_uris` that is
    missing, empty, longer than 10 entries or has a non-string entry or one
    longer than 2,048 characters;
  - `invalid_redirect_uri`: a URI that matches no allowlist entry;
  - `503 temporarily_unavailable` with a warning log entry when the
    non-deleted client cap is reached after cleanup.

  Other metadata is ignored. The registration log entry carries the
  `client_id` and the name as `self_declared_client_name`.
- `GET /api/oauth/authorize` locks the client row (`FOR NO KEY UPDATE`) and
  then checks, in this order:
  1. a single `client_id` without a NUL character, of a registered,
     non-deleted client, otherwise `400 invalid_client`, shown and never
     redirected;
  2. a single `redirect_uri` that matches the current allowlist and repeats a
     registered URI exactly, or for a loopback URI differs only in the port,
     otherwise `400 invalid_request` ("Invalid redirect_uri"), shown and never
     redirected;
  3. at most one `state`, without a NUL character (PostgreSQL text cannot
     hold one), `response_type=code` (`unsupported_response_type`
     for another value), a 43-character `code_challenge` with
     `code_challenge_method=S256`, exactly one canonical `resource`
     (`invalid_target`), and `scope` omitted or exactly the resource's scope
     (`invalid_scope`); every repeated parameter is `invalid_request`;
  4. the live undecided request caps per client and in total
     (`temporarily_unavailable`). The client row lock serialises the
     per-client count; a transaction-scoped PostgreSQL advisory lock, held
     until authorize commits or rolls back, serialises the total count across
     clients, so both caps are exact.

  Errors from step 3 onwards are a `303` to the validated redirect URI with
  exactly `error`, `state` (when the client sent exactly one valid state) and
  `iss`. On
  success it stores the hashed request, then updates the locked client's
  `last_used_time`, commits and answers `303` to
  `<PUBLIC_ORIGIN>/ai/authorize?request=<id>`. A failing authorize stores
  nothing and does not touch `last_used_time`.

All public endpoints except discovery use the per-IP buckets of
`app.state.oauth_rate_limiter`, a separate `FixedWindowRateLimiter` that never
touches the login `auth_rate_limiter`: `register`, `authorize`, and `token`
and `revoke` for TASK-069F (`oauth_rate_limit_allows()` in `router.py`). A
limited request gets `429 temporarily_unavailable` and is never redirected.

Registration runs `cleanup_stale_clients()` before its cap check. It locks
candidates `FOR UPDATE SKIP LOCKED`, at most 1,000 per step:

1. it soft-deletes clients whose `last_used_time` (or creation time) is older
   than 30 days and that have no active grant (not revoked, not expired);
2. it hard-deletes soft-deleted clients that no authorization request and no
   grant references.

A client locked by an in-flight authorize is skipped. Token requests also run
this cleanup, after TASK-069F's request, token and grant cleanup.

Consent API (business session; approve and deny need the CSRF token and exact
Origin; `Cache-Control: no-store`):

- `GET /api/v1/ai/oauth/consent?request=<id>` returns `clientName`,
  `clientNameSelfDeclared: true`, `redirectIsLoopback` (from the allowlist
  entry the redirect URI matches), `redirectHost` (the host in URL form, for
  example `claude.ai`, `127.0.0.1`, `[::1]` or `localhost`), `scope`,
  `resource` and `expiresTime`.
- `POST /api/v1/ai/oauth/consent/approve` with `{"request": "<id>"}` locks the
  request, records the deciding User, stores the SHA-256 hash of a new 256-bit
  code that expires after 60 seconds and returns `{"redirectUrl"}`: the stored
  redirect URI with `code`, `state` (omitted when the client sent none) and
  `iss`.
- `POST /api/v1/ai/oauth/consent/deny` records the deciding User without a
  code and returns an `access_denied` `redirectUrl` built the same way.
- Errors use the `/api/v1` error body: `404 AUTHORIZATION_REQUEST_NOT_FOUND`
  for a missing, malformed or unknown id, a deleted client or a redirect URI
  no longer on the allowlist; `409 AUTHORIZATION_REQUEST_DECIDED`; and
  `410 AUTHORIZATION_REQUEST_EXPIRED`.

A request is undecided while its `user_id` is null. Approval sets `user_id`,
`code_hash` and `code_expires_time`; denial sets only `user_id`. A decided
request cannot be decided again, and denied requests have no code to exchange.
Only undecided, unexpired requests count towards the pending caps.

The incident procedure (disable MCP, then revoke affected Users' grants) and
the offboarding rule (soft-delete the User or revoke the User's grants) are in
ADR-015.

## MCP OAuth Tokens And Connections (TASK-069F)

The code is in `backend/app/api/v1/mcp_oauth/token_service.py`, with the token
and revoke routes in `router.py` and the cookie-session connections API in
`connections_router.py`. The sequence is drawn in
[MCP OAuth tokens](../diagrams/generated/sequence-mcp-oauth-tokens.svg)
(`docs/diagrams/sequence-mcp-oauth-tokens.puml`). The lifetimes are the
settings `MCP_OAUTH_ACCESS_TOKEN_LIFETIME_SECONDS` (default 1 hour),
`MCP_OAUTH_REFRESH_TOKEN_IDLE_LIFETIME_SECONDS` (7 days) and
`MCP_OAUTH_GRANT_LIFETIME_SECONDS` (30 days); startup fails if a token
lifetime exceeds the grant lifetime.

`POST /api/oauth/token` (registered only with `MCP_ENABLED=true`, `token`
bucket, `Cache-Control: no-store`, RFC 6749 JSON errors) takes an
`application/x-www-form-urlencoded` body of at most 16 KiB and 20 fields.
Empty values count as omitted, and a repeated parameter or a NUL character is
`invalid_request`, except for `resource`, which is checked as described below.
An unknown `grant_type` is `unsupported_grant_type`. Every
`authorization_code` or `refresh_token` request first runs lazy cleanup (below)
in its own transactions.

- `authorization_code` requires `code`, `redirect_uri` and `code_verifier`
  (otherwise `invalid_request`), exactly one `resource` (otherwise
  `invalid_target`) and the `client_id` of a registered, non-deleted client
  (otherwise `invalid_client`). It locks the request by code hash and then
  checks, in this order:
  1. a code that was already redeemed: the second redemption revokes the
     still-active grant recorded on the request and all its tokens
     (`code_reuse`) and fails with `invalid_grant`. If lazy cleanup already
     deleted that grant, nothing is left to revoke;
  2. the code was issued to this client, has not expired (60 seconds), the
     `redirect_uri` equals the request's exactly (including a loopback port)
     and the RFC 7636 `code_verifier` matches the S256 challenge; otherwise
     `invalid_grant`;
  3. `resource` equals the request's canonical resource; otherwise
     `invalid_target`;
  4. the approving User is not soft-deleted; otherwise `invalid_grant`.

  A failed exchange changes nothing, so the code stays redeemable until it
  expires. A successful exchange marks the request consumed and records its
  grant. It locks and reuses the User's active grant (not revoked, not
  expired) for the same client and resource, keeping its `expires_time` and
  revoking all its earlier access and refresh tokens (`reauthorization`).
  Without an active grant it creates one (`grant_<uuid>`) that expires after
  the grant lifetime. A transaction-scoped PostgreSQL advisory lock per
  client, User and resource, taken before the lookup, makes a concurrent
  exchange wait and then reuse that grant, so concurrent first authorizations
  never create two active grants.
- `refresh_token` requires `refresh_token`, `client_id` and `resource`; an
  optional `scope` must equal the grant's scope (otherwise `invalid_scope`).
  It locks the grant and then the token, the same order as every revocation.
  An unknown token, an access token or another client's token is
  `invalid_grant`, and a resource other than the grant's is `invalid_target`,
  both without effect. Then ADR-015's order decides, first match wins:
  1. grant revoked or past its `expires_time`: `invalid_grant`, no effect;
  2. token `revoked_time` set (for example after a re-authorization):
     `invalid_grant`, no effect;
  3. token has `replaced_by_hash`: reuse detected, whatever the token's own
     expiry. The grant and all its tokens are revoked
     (`refresh_token_reuse`) and the answer is `invalid_grant`;
  4. token past its idle expiry: `invalid_grant`;
  5. otherwise, unless the User is soft-deleted (`invalid_grant`), the token
     is rotated: a new pair is stored and only the old row's
     `replaced_by_hash` is set, never its `revoked_time`.
- Both grant types store a new access token and refresh token, each expiring
  after its lifetime but never after the grant's `expires_time`, and answer
  `{"access_token", "token_type": "Bearer", "expires_in", "refresh_token",
  "scope"}`. Tokens are `secrets.token_urlsafe(32)` values (256 bits) and only
  their SHA-256 hashes are stored.
- The last write before commit is the client's `last_used_time`, a
  conditional update that writes only when the value is missing or at least
  five minutes old. It conflicts with an in-flight authorize's
  `FOR NO KEY UPDATE` client row lock and can wait until that authorize
  commits; the grant and token inserts before it take only key-share locks and
  never wait.

`POST /api/oauth/revoke` (RFC 7009, registered only with `MCP_ENABLED=true`,
`revoke` bucket, the same form body rules) requires `token` (otherwise
`invalid_request`) and the `client_id` of a registered, non-deleted client
(otherwise `invalid_client`); `token_type_hint` is ignored. Revoking a refresh
token revokes its grant and all the grant's tokens (`client_revoke`); revoking
an access token revokes only that token. An unknown token, or a token issued to
another client, answers 200 without effect.

Lazy cleanup (`cleanup_expired_oauth_rows()`) runs during token requests, with
no scheduler or worker. It locks candidates `FOR UPDATE SKIP LOCKED`, at most
1,000 per kind, and deletes, in three steps that each commit on their own:

- authorization requests past their expiry whose code has also expired, so a
  code approved late in the ten-minute window can still be redeemed;
- expired access tokens;
- revoked or expired grants. The database deletes their tokens
  (`ON DELETE CASCADE`) and sets `mcp_oauth_authorization_requests.grant_id`
  and `ai_change_sets.grant_id` to null.

Refresh tokens of an active grant, including replaced ones, are never deleted,
so reuse detection works for the grant's whole lifetime. The cleanup then runs
TASK-069E's client cleanup, which hard-deletes a soft-deleted client once its
last authorization request and grant are gone.

`SKIP LOCKED` only skips locked candidates: a grant deletion's cascades can
still wait for a token or request row that another operation holds. Because
each step commits before the next, no step keeps another step's locks, so two
concurrent cleanups cannot deadlock on each other's expired access tokens.
Each step also runs with a PostgreSQL `lock_timeout` of 500 ms, below the
default 1 s `deadlock_timeout`, so cleanup gives way first. Cleanup is best
effort: a step that hits the timeout or a deadlock is rolled back, logged as a
warning without secrets and left to a later token request, and the token
request itself continues.

`verify_access_token(session, token, required_resource, required_scope)` is
the verification that TASK-069G's `McpBearerAuth` uses. It re-reads the token,
grant, client and User on every call and returns an `McpPrincipal` (`user_id`,
`role`, `grant_id`, `grant_key`, `client_id`, `client_name`, `scopes`), or
raises `TokenVerificationError` with:

- `invalid_token` for a missing, malformed, unknown, expired or revoked access
  token, a revoked or expired grant, a grant bound to another resource than
  `required_resource`, or a soft-deleted User;
- `insufficient_scope` when `required_scope` is not in the effective scopes,
  `grant.scopes` intersected with `allowed_scopes_for_role(user.role)`. Both
  current roles have both scopes (`ROLE_SCOPES`).

A role change, User soft deletion or revocation therefore acts on the next
call. A successful verification writes the grant's `last_used_time` at most
every five minutes.

Every grant revocation, and the token revocation on re-authorization, writes
one `INFO` entry on the `app.api.v1.mcp_oauth.token_service` logger after its
transaction commits, so the audit survives the grant row's later deletion.
`fastapi run` configures only the uvicorn loggers and leaves the root logger at
`WARNING` without a handler, so `create_app()` installs
`install_mcp_oauth_audit_log()` (`audit_log.py`): the `app.api.v1.mcp_oauth`
logger is set to `INFO` with its own standard-error handler. These revocation
entries and TASK-069E's registration entries therefore appear once in the
backend container log under `fastapi run` (production) and `fastapi dev`. The
entries still propagate so that test log capture sees them; a log
configuration that also gives the root logger a handler would print them
twice:

```text
MCP OAuth grant revoked: reason=<reason> actor=<actor> user_id=<User id> grant_key=<key> client_id=<client_id> self_declared_client_name='<name>' revoked_tokens=<count>
```

| Reason | Actor | `revoked_by` |
| --- | --- | --- |
| `user_revoke` | `user:<id>` | the User |
| `admin_revoke` | `user:<admin id>` | the admin |
| `client_revoke` | `client` | null |
| `refresh_token_reuse` | `system` | null |
| `code_reuse` | `system` | null |
| `reauthorization` | `user:<id>` | the grant stays active; the message is `MCP OAuth grant tokens revoked` |

`revoked_tokens` counts the tokens revoked by that entry. No entry contains a
token, code or request id.

Connections API (`/api/v1/ai`, business session, always registered so grants
stay revocable while `MCP_ENABLED=false`):

- `GET /api/v1/ai/connections` lists the current User's active grants, newest
  first, with `grantKey`, `clientId`, `clientName` (a label the client declared
  itself), `scope`, `resource`, `createdTime`, `lastUsedTime` and
  `expiresTime`.
- `DELETE /api/v1/ai/connections/{grant_key}` (session CSRF token and exact
  Origin) revokes one of the User's own active grants and all its tokens,
  records `revoked_by` and answers 204. Another User's grant, an unknown key or
  an inactive grant is `404 CONNECTION_NOT_FOUND`.
- `POST /api/v1/ai/users/{user_id}/connections/revoke` (`admin` only, CSRF and
  exact Origin) revokes every active grant of that User, also of a
  soft-deleted User, records `revoked_by` and answers `{"revokedCount": n}`.
  An unknown User, including a `user_id` outside the `BIGINT` range, is
  `404 USER_NOT_FOUND`. It serves ADR-015's offboarding rule and incident
  procedure.

`tests/test_api_authorization.py` sweeps these routes in both app
configurations.

## MCP Servers (TASK-069G)

The code is in `backend/app/mcp/`: `endpoints.py` builds both servers,
`auth.py` holds `McpBearerAuth`, `runtime.py` runs tool database work,
`read_server.py` the read tools and `write_server.py` the write tools.
`fastmcp` 4 is the one approved MCP dependency (ADR-015).

- `create_app()` builds both FastMCP servers inside the factory, only with
  `MCP_ENABLED=true`, stateless (`stateless_http=True`) with JSON responses
  (`json_response=True`). It registers the exact routes `/api/mcp/read` and
  `/api/mcp/write` for GET, POST and DELETE, outside the OpenAPI schema, each
  wrapped in `McpBearerAuth`. `app.mount` is not used, because it redirects
  `/api/mcp/<server>` to a trailing slash. One combined lifespan runs both
  session managers; the OIDC provider initialisation in it stays skipped in the
  test environment, which now also runs the lifespan. Stateless servers keep
  no MCP session or server-sent event stream, so an authenticated GET or DELETE
  answers 405. With `MCP_ENABLED=false` no MCP route exists and every method
  answers 404, and `fastmcp` is not even imported: `create_app()` imports
  `app.mcp.endpoints` only when MCP is enabled, so a disabled backend saves
  fastmcp's memory, import time and import-time logging setup.
- `McpBearerAuth` accepts exactly one `Authorization: Bearer` header and never
  the session cookie. It calls `verify_access_token` with the endpoint's
  canonical resource `<PUBLIC_ORIGIN>/api/mcp/<server>` and scope in a worker
  thread under the shared capacity limiter, so a token for the other resource,
  an expired or revoked token or grant and a soft-deleted User are rejected on
  the next call, and the role is re-read on every call. It answers:
  - `401` with
    `WWW-Authenticate: Bearer resource_metadata="<origin>/.well-known/oauth-protected-resource/api/mcp/<server>"`
    when no bearer token was presented (also for another scheme such as
    `Basic`);
  - `401` with `Bearer error="invalid_token", resource_metadata="..."` when a
    token was presented but rejected, including a repeated `Authorization`
    header and the resource mismatch;
  - `403` with
    `Bearer error="insufficient_scope", scope="<scope>", resource_metadata="..."`
    when the effective scopes after the role mapping lack the endpoint's scope;
  - `429 temporarily_unavailable` when the grant exceeded
    `MCP_RATE_LIMIT_PER_MINUTE` (default 120) in the current minute. The count
    is kept per grant key in `app.state.mcp_rate_limiter`, a separate
    `FixedWindowRateLimiter` that never touches `auth_rate_limiter` or
    `oauth_rate_limiter`.

  Error bodies are `{"error", "error_description"}` and every `/api/mcp/*`
  response has `Cache-Control: no-store`. On success it places the
  `McpPrincipal` in the `current_principal` context variable for the tools.
- `McpToolRuntime.run()` runs a tool's database work through
  `anyio.to_thread.run_sync` in its own session under one
  `anyio.CapacityLimiter` of `MCP_TOOL_CONCURRENCY` (default 4) tokens, shared
  by both servers and the bearer verification. `validate_change_set` and
  `submit_change_set` hold two database connections per token, the tool's own
  (with the change-set row lock) and the dry-run's, from the pool the REST API
  shares, so twice the setting must stay well below the pool size. A domain `HTTPException` below
  500 becomes a tool error with the service's message, for example
  `Organisation not found.`. Any other error reaches the client only as
  `Internal error` (the servers also set `mask_error_details`) and is logged
  with its type and stack frames but without its message, because messages
  such as SQL errors may contain tool arguments. Tokens and tool arguments are
  never logged.
- Read tools return the existing response schemas, which FastMCP serialises
  as structured content by field name: list results are wrapped as
  `{"result": [...]}` and `OrgStateResponse.target_date` appears as
  `target_date`, not REST's `targetDate` alias. Key arguments are strings of 1
  to 128 characters.

The first read tools are `whoami` (`UserResponse` of the principal's User),
`list_organisations` (`OrganisationResponse` list),
`list_scenarios(organisation_key)` (`ScenarioResponse` list) and
`list_org_states(organisation_key, scenario_key)` (`OrgStateResponse` list).
TASK-069H added the remaining read tools and TASK-069J the write tools
(below).

How to connect Claude Code locally is in `docs/LOCAL-DEVELOPMENT.md`.

## MCP Read Tools (TASK-069H)

Every read tool has the TASK-069G annotations (`readOnlyHint`,
`idempotentHint`, `openWorldHint=False`), needs `schatten.read` and runs
through `McpToolRuntime`. The tool docstrings in
`backend/app/mcp/read_server.py` are the LLM-facing contract; they state what
each argument means, the date rules and the limits. Results are serialised by
field name (snake_case). An unknown or soft-deleted organisation, scenario, org
state or timeserie is a tool error with the service's message, such as
`Scenario not found.`.

| Tool | Service function | Result |
| --- | --- | --- |
| `whoami` | `users_service.get_user` | `UserResponse` |
| `list_organisations` | `organisations_service.list_organisations` | `OrganisationResponse` list |
| `list_scenarios(organisation_key)` | `list_organisation_scenarios` | `ScenarioResponse` list |
| `list_org_states(organisation_key, scenario_key)` | `list_organisation_scenario_org_states` | `OrgStateResponse` list |
| `get_type_catalog(organisation_key, scenario_key)` | `get_scenario_type_catalog_with_attributes` | `TypeCatalogWithAttributesResponse` |
| `get_graph(organisation_key, scenario_key, org_state_key)` | `org_twin_structure_service.get_graph` | `GraphResponse` |
| `list_timeseries(organisation_key, scenario_key, include_values=False)` | `list_scenario_timeseries(include_values=...)` | `TimeserieListResult` |
| `get_timeserie(organisation_key, scenario_key, timeserie_key, from_date=None, to_date=None)` | `get_timeserie_values_page` | `TimeserieValuesResult` |
| `list_events(organisation_key, scenario_key)` | `list_scenario_events` | `EventResponse` list |
| `preview_generated_timeserie(spec)` | `timeserie_generation.generator.generate` | `GeneratedTimeseriePreview` |

- `get_type_catalog` returns the REST type catalog (node types with UI
  metadata, the timeserie defaults `timeserie_id`, `timeserie_secondary_id`
  and `timeserie_id_rule`, edge types and allowed connections) plus
  `type_attributes`: the active attribute definitions (`owner_kind`,
  `owner_type_id`, `id`, `name`, `display_name`, `data_type`, `mandatory`,
  `max_length`, `multiline`) of active node and edge types. REST has no
  attribute metadata, so the org twin structure domain adds the service
  function `get_scenario_type_catalog_with_attributes` and the schema
  `TypeCatalogWithAttributesResponse`; the REST type-catalog responses are
  unchanged. Graph element `attributes` stay a free JSON object that is not
  validated against these definitions.
- `get_graph` returns the graph visible at the org state's target date, as the
  REST graph endpoint does.
- `list_timeseries` returns `TimeserieResponse` items (definitions, short
  names, units, `derived_formula`) in timeserie key order. Without
  `include_values` every `values` list is empty and no value is read from the
  database. With it, values are filled in
  key and date order up to `LIST_TIMESERIES_MAX_VALUES` (2,000) in total;
  `truncated` and `truncated_timeserie_ids` name every timeserie whose values
  were cut or left out.
- `get_timeserie` returns the timeserie with only its values between the
  inclusive, unaligned `from_date` and `to_date` (ISO dates, `from_date` not
  after `to_date`), at most `GET_TIMESERIE_MAX_POINTS` (1,000) in date order.
  `value_count` counts all values in the bounds; when more remain, `truncated`
  is true and `next_from_date` is the `from_date` of the next page. The service
  function `get_timeserie_values_page` filters the dates and limits the rows in
  SQL and counts the values in the bounds, so one page reads at most 1,001
  values.
- `list_events` returns the active events by target date.
- `preview_generated_timeserie` validates its `TimeserieGenerationSpec`
  argument (camelCase JSON, see
  [Timeserie Generation Specification](#timeserie-generation-specification)),
  so an invalid spec is a validation error naming the field. It returns
  `generator_version`, `point_count`, `first_date`, `last_date`, `min`, `max`,
  `mean` and the first and last `PREVIEW_SAMPLE_POINTS` (5) points. It is
  deterministic for a fixed spec and seed, runs no database query and
  persists nothing. `TimeserieGenerationError` becomes a tool error with its
  message.

`get_type_catalog`, `get_graph` and `list_events` are bounded by the size of
the model itself and are not truncated. Only `list_timeseries` with
`include_values=true` still reads every value of the scenario's timeseries
before cutting them to 2,000, so that opt-in call bounds the response, not the
database read (accepted in ADR-015's resource protection).

## AI Change-Set Engine (TASK-069I)

`backend/app/api/v1/ai_change_sets/engine.py` stages, validates, freezes and
applies change sets; `schemas.py` holds the `ChangeSetOperation` union, results
and replacement summaries. The engine adds no MCP tool, REST route or UI:
TASK-069J's write tools call `create_change_set`, `add_operations`,
`remove_operation`, `discard_change_set`, `validate_change_set`,
`submit_change_set` and, for information only, `compute_replacements`, and
TASK-069K's review API calls `compute_replacements`, `apply_change_set` and
`reject_change_set`.
A tool commits its change-set edits before it validates or submits, because
the dry-run runs on its own connection and the engine refuses a transaction
that has written or locked rows. The operation JSON, `$ref` rules, results,
replacement summaries, apply error codes and the settings
`AI_CHANGE_SET_STATEMENT_TIMEOUT_MS` and `AI_CHANGE_SET_LOCK_TIMEOUT_MS` are
described in
[AI Change Set](../concepts/AI_CHANGE_SET.md#engine-task-069i), and the
lifecycle is drawn in
[AI change-set lifecycle](../diagrams/generated/state-ai-change-set.svg).

Execution goes only through the `*_in_transaction` cores of Organisation
States and Organisation Twin Structure. The replacement flags read through
their public service functions: `get_org_state`, `get_timeserie` and the
read-only `get_graph_node_visible_at`, which returns a node as an org state
with a given target date would show it, also for an org state the change set
creates. The engine reads `scenarios` and `organisations` rows directly only
to map between keys and ids: the derived scenario reference and a change set's
organisation key.

## MCP Write Tools (TASK-069J)

`backend/app/mcp/write_server.py` holds the write tools; the change-set read
tools are in `read_server.py` and read through
`backend/app/api/v1/ai_change_sets/service.py`. Every write tool needs
`schatten.write`, runs through `McpToolRuntime` under the shared capacity
limiter and is annotated `openWorldHint=False` and `readOnlyHint=False`;
`remove_operation` and `discard_change_set` are `destructiveHint`, the others
explicitly not, and `validate_change_set` is `idempotentHint`. The server's
instructions and the tool docstrings explain the workflow create, add,
validate, fix, submit, the `$ref` rules (only server-generated scenario,
organisation state, event and derived metric keys; node, edge and timeserie
keys are client-supplied and referred to verbatim), that the dry-run stops at
the first failing operation and that nothing is applied until a human approves
it. TASK-069O adds `apply_change_set` and `reject_change_set`, see
[MCP Change-Set Review (TASK-069O)](#mcp-change-set-review-task-069o).

| Tool | Engine call | Result |
| --- | --- | --- |
| `create_change_set(organisation_key, title, rationale=None)` | `create_change_set` | `ChangeSetSummary`; its `id` is the change set key |
| `add_operations(change_set_key, operations)` | `add_operations` | `OperationsAdded`: the summary and the `added_positions` |
| `remove_operation(change_set_key, position)` | `remove_operation` | `ChangeSetSummary` |
| `validate_change_set(change_set_key)` | `validate_change_set`, then `compute_replacements` | `ChangeSetValidation`: `ok`, per-operation results, provisional `refs` and the informational `replacements` |
| `submit_change_set(change_set_key)` | `submit_change_set` | `ChangeSetSubmission`: `status`, `ok`, per-operation results and `review_url` |
| `discard_change_set(change_set_key)` | `discard_change_set` | `ChangeSetSummary` with status `discarded` |

- `create_change_set` records the principal's User as `created_by` and the
  principal's grant, copied `client_id` and client name. `title` is 1 to 200
  characters (trimmed) and `rationale` at most 4,000.
- Only a `draft` can be changed, and only through a grant of the User who
  created it: any of that User's grants, not only the staging one. Another
  User's change set is the tool error `Only the User who created this change
  set can change it; other Users can only read it.`; a change set that is not
  a draft is the engine's `409` message. The ownership check is a plain read
  without a row lock; the engine locks the row and checks the status.
- `add_operations` takes 1 to 500 typed operations (`ChangeSetOperation`,
  validated by the tool's input schema). The engine enforces the limits of
  500 operations and 20,000 set or generated values per change set and checks
  every reference. Before any database work the tool rejects NUL characters
  in the title, rationale and operation JSON (PostgreSQL text and JSONB cannot
  hold them) and more than `MAX_ADD_OPERATIONS_BYTES` (2 MiB) of operation
  JSON per call.
- `validate_change_set` commits the stored dry-run result first and then runs
  `compute_replacements` read-only. The replacement report is returned for
  information only; it is not stored, and the human review and apply
  recompute it against current data.
- `submit_change_set` re-validates and freezes generated values. When every
  operation is `ok` the status becomes `submitted` and `review_url` is
  `<PUBLIC_ORIGIN>/schatten/<org>/metrics?changeSet=<key>`; otherwise the
  change set stays a draft with the stored result and `review_url` is null.
- Every write tool's transaction runs under
  `AI_CHANGE_SET_STATEMENT_TIMEOUT_MS`, so a lock wait on a busy draft also
  ends. A lock-not-available or query-cancelled error outside the dry-run is
  the retryable tool error `The change set is busy or the database timed out;
  try again shortly.`
- Edits commit before validation and submit, because the dry-run runs on its
  own connection and the engine refuses a transaction that has written or
  locked rows.

Read tools (read-only annotations, `schatten.read`):

- `list_change_sets(organisation_key, status=None, scenario_key=None)` returns
  `ChangeSetListResult`: at most `LIST_CHANGE_SETS_MAX_ITEMS` (100)
  `ChangeSetSummary` items, newest first, with `truncated`. `status` is one of
  the six statuses; `scenario_key` filters on the derived scenario reference
  and must name an active scenario of the organisation.
- `get_change_set(change_set_key)` returns `ChangeSetDetail`: the summary, each
  operation with `position`, `type`, `ref`, the stored `operation` JSON, its
  latest `error` and a `frozen_values` summary (generator version, count and
  first and last date; the values themselves are not returned), and the
  stored `validation_result` and `applied_result`.

Any User may read any change set of an active organisation. An unknown change
set, or one of a soft-deleted organisation, is `Change set not found.`.
`ChangeSetSummary` has `id`, `organisation_key`, `scenario_key`, `title`,
`rationale`, `status`, `operation_count`, `client_id`, `client_name`,
`created_by`, `created_time`, `modified_time`, `reviewed_by`, `reviewed_time`,
`review_note` and (TASK-069O) `reviewed_via`, `review_client_id` and
`review_client_name`.

## Change-Set Review API (TASK-069K)

`backend/app/api/v1/ai_change_sets/router.py` is the cookie-session API the
Metrics tab uses; `review_schemas.py` holds its models and `service.py` builds
them. It is registered with and without `MCP_ENABLED`, uses the router-level
`require_business_request`, and both roles may use every route, including the
creator. JSON keys are camelCase; the stored operation JSON is returned as it
was staged, and the path parameters keep their snake_case names.

| Route | Result |
| --- | --- |
| `GET …/ai/change-sets` | Newest first, at most `limit` (default 100, at most 200) list items |
| `GET …/ai/change-sets/{change_set_key}` | `ChangeSetReviewDetail` |
| `POST …/{change_set_key}/apply` (CSRF, exact Origin) | `ChangeSetApplyResponse` |
| `POST …/{change_set_key}/reject` (CSRF, exact Origin) | The list item of the rejected change set |

- **List.** `status` filters by one of the six statuses. `scenarioKey`
  filters on the derived scenario reference and must name an active scenario
  of the organisation (otherwise 404); with `includeUnscoped=true` the change
  sets without a scenario reference (they create or copy a scenario, or touch
  several) are included. A list item has `id`, `scenarioKey` (or null),
  `title`, `rationale`, `status`, `operationCount`, `clientId`, `clientName`
  (self-declared by the client, not verified), `createdBy`, `createdByName`,
  `createdTime`, `modifiedTime`, `reviewedBy`, `reviewedByName`,
  `reviewedTime` and `reviewNote`.
- **Detail.** The list item plus `operations`, `reviewFingerprint`,
  `validationResult` and `appliedResult`. Each operation has `position`,
  `type`, `ref`, the stored `operation` JSON, its latest `error`,
  `frozenValues` (`generatorVersion`, `valueCount`, `firstDate`, `lastDate`
  and the `values` themselves up to 1,000 per operation, otherwise null),
  `replacesExisting` and `replaces`. The detail reads the change set, its
  summary (including `operationCount` and `validationResult`) and its
  operation rows in one statement, and `compute_replacements` computes the
  flags and summaries from exactly those rows against current data on every
  read, so a draft edited meanwhile cannot make any part of the detail
  disagree. Every read, the lookup by key included, runs under the change-set
  `statement_timeout`; a timeout or other database error is the retryable
  `503` `{"error": {"code": "review_unavailable", "message"}}`. A
  target deleted after submit has `"missing": true` and the domain message. A
  node summary names the patched `fields` as the operation's payload does
  (`nodeTypeId`). A change set of another organisation is
  `404 Change set not found.`. A change set whose stored operations no longer
  parse has no detail (`500`); it can still be rejected by the key from the
  list (see the open question in
  [AI Change Set](../concepts/AI_CHANGE_SET.md#open-questions)).
- **Apply** takes `{"reviewFingerprint": "<64 hex characters>"}`; a missing or
  malformed value is a `422`. It calls `apply_change_set` with the reviewer as
  the actor. Success returns `changeSet` (the list item, now `applied`),
  `operations` (each with `opType`, `status`, `scenarioKey` and the created or
  changed `key`) and `refs` (each `$ref` symbol's created key). Engine errors
  are `{"error": {"code", "message"}}`:

  | Code | HTTP | Status change |
  | --- | --- | --- |
  | `not_submitted` | 409 | none |
  | `review_stale` | 409 | none; reload and confirm again |
  | `apply_in_progress` | 409, retryable | none |
  | `apply_unavailable` | 503, retryable | none |
  | `apply_failed` | 409 | `failed`; the detail's `appliedResult` and operation `error` explain it |

- **Reject** takes an optional body `{"note": "..."}`. The note is trimmed, a
  blank note is stored as null, and it has at most 2,000 characters and no
  NUL characters (otherwise 422). `reject_change_set` locks the change set
  under apply's timeouts, requires `submitted` and records `rejected`,
  `reviewed_by`, `reviewed_time`, `review_note` and `modified_by`. It does not
  parse the stored operations, so a change set whose operations no longer
  parse can still be rejected, although its detail fails. It returns
  `not_submitted`, `apply_in_progress` or `apply_unavailable` (whose message
  then says the change set could not be rejected) in the same error body as
  apply.

## Consent Page And Connections UI (TASK-069L)

The SPA code is in `frontend/src/features/ai/` with the API wrappers in
`frontend/src/api/ai.ts`, which use `authenticatedFetch` (session cookie, and
the CSRF token on unsafe methods). `AiApiError` keeps the HTTP status and the
`/api/v1` error code, so the page can tell the consent states apart.
`AuthProvider` reads the session's `features.mcp`; a missing or malformed
flag counts as `false`.

Consent page `/ai/authorize` (`AuthorizePage.tsx`):

- An anonymous visitor gets the existing login page, whose "Sign in" sends
  `return_to=/ai/authorize?request=<id>` to `GET /api/v1/auth/login`, so the
  page reopens with the same request after the Entra login.
- With `features.mcp` false the page shows "AI connections are not available"
  and calls no API. Without a `request` query parameter it shows the "not
  found" state.
- The page reads `request` only from its own query string and loads
  `GET /api/v1/ai/oauth/consent?request=<id>`. The id is sent in that query
  parameter and in the approve and deny JSON bodies, never in a URL path, and
  it is never rendered or logged by the SPA.
- It shows:
  - the signed-in User the client will act as;
  - the client name in its own `<bdi>` element, labelled "(self-declared by
    the client)" (`SelfDeclaredClientName.tsx`);
  - for `redirectIsLoopback: false`, the server's `redirectHost`; for `true`,
    "A program on this computer" and a "Local program" notice that the code
    goes to a program on this computer and that local programs cannot be
    verified by name. The SPA never parses host strings;
  - the request expiry;
  - the requested access: "Read access" (the client can read what the User
    can see and cannot change anything) or "Write access: proposals only"
    (changes are only proposed, and nothing changes until a person reviews
    and applies the change set in Schatten). With the session's
    `features.mcpChangeSetReview` (TASK-069O) write access is "Write access:
    propose, apply and reject changes" instead: on the User's instruction the
    client can also apply or reject change sets awaiting review, including
    other people's, the User is recorded as reviewer, and the client should
    ask before each call. An unknown scope is shown verbatim with advice to
    deny;
  - that data the client reads from Schatten is sent to the User's AI vendor,
    and that the connection lasts for a limited time (30 days by default)
    unless revoked. The grant lifetime is the deployment setting
    `MCP_OAUTH_GRANT_LIFETIME_SECONDS`, which the consent API does not return,
    so the page names only the default.
- Approve and Deny post `{"request": "<id>"}` to
  `/api/v1/ai/oauth/consent/approve` or `/deny`. On success the page calls
  `navigateBrowser(redirectUrl)` (`window.location.assign`) with exactly the
  server-returned `redirectUrl`; it never builds or changes a redirect URL.
  This is a script navigation, so the CSP `form-action 'self'` is unchanged.
  Both buttons are disabled while a decision is pending.
- `410 AUTHORIZATION_REQUEST_EXPIRED` shows the expired state,
  `409 AUTHORIZATION_REQUEST_DECIDED` the already-decided state and any `404`
  the not-found state, on load or on a decision. Every final state tells the
  User to start the connection again from the AI client. Another load error
  offers Retry; another decision error keeps the request decidable.

`ConnectionsList.tsx` lists `GET /api/v1/ai/connections`: each grant with its
isolated, self-declared client name, `clientId`, scope, and created, last used
("Never" when null) and expiry times. Revoke asks for confirmation and calls
`DELETE /api/v1/ai/connections/{grant_key}`; a `404` removes the row as
already revoked or expired. The component does not read `features.mcp`, so
grants stay revocable while MCP is disabled. The Metrics tab AI panel shows it
in its Connections section (TASK-069M).

Users administration (`frontend/src/features/users/UsersTab.tsx`, `admin`
only) has a "Revoke AI connections" action for the selected User. After
confirmation it calls
`POST /api/v1/ai/users/{user_id}/connections/revoke` and shows the returned
`revokedCount`. It is independent of `features.mcp` and serves ADR-015's
offboarding rule and incident procedure. Consultants have no Users tab and
therefore no action; the backend enforces the role.

## Metrics Tab AI Panel (TASK-069M)

The panel is in `frontend/src/features/ai/` and uses the review API wrappers
`fetchAiChangeSets`, `fetchAiChangeSet`, `applyAiChangeSet` and
`rejectAiChangeSet` in `frontend/src/api/ai.ts`. `MetricsTab.tsx` adds only
the toolbar toggle (`AiPanelToggle.tsx`) and the panel slot; the workspace
route passes `features.mcp` and the `changeSet` query parameter.

- **Toggle.** With `features.mcp` true the "AI panel" toggle is always shown.
  With it false the toggle loads one change set of the organisation and the
  User's connections and is shown only when either exists.
- **Deep link.** `/schatten/<org>/metrics?changeSet=<key>`, the review URL of
  `submit_change_set`, opens the panel on that change set, also before a
  scenario is selected. Opening a change set from the list and going back set
  and clear the parameter and keep the panel open, also when a review link
  opened it; closing the panel clears it.
- **Sections** (`AiPanel.tsx`): Change sets, Connections (TASK-069L's
  `ConnectionsList`) and Connect. Connect (`ConnectInstructions.tsx`) shows
  `<origin>/api/mcp/read` and `<origin>/api/mcp/write` with copy buttons, the
  custom-connector steps for Claude Desktop and claude.ai, and the
  `claude mcp add --transport http …` commands and `/mcp` authentication for
  Claude Code. It is hidden when `features.mcp` is false.
- **List** (`ChangeSetList.tsx`): newest first with status badges, operation
  count, creator and the derived scenario key. With a selected scenario it
  requests `scenarioKey=<scenario>&includeUnscoped=true`; "Show all change sets
  of the organisation" drops the filter.
- **Review** (`ChangeSetReview.tsx`):
  - each operation in readable form (`changeSetOperations.ts`), for example
    "Create node *Revenue* (GOAL)" and "Create edge *Revenue → Company*
    (MEASURED_BY)", naming nodes and timeseries the change set creates, with
    its scenario, organisation state, key and `$ref`;
  - for `set_timeserie_values` and `generate_timeserie_values`, a values table
    (at most 1,000 rows, in staged order) and an inline SVG sparkline of the
    numeric values sorted by date (`Sparkline.tsx`), since staged values may
    come in any order; frozen values the detail returns only as a summary are
    shown as their count and date range;
  - validation errors: each operation's latest `error` and a failed apply's
    step and error;
  - a "Replaces existing data" badge on every operation with
    `replacesExisting`, with the recomputed summary (the existing value count
    and date range, or the patched node fields with their current and proposed
    values), and a summary line before Apply counting these operations;
  - a "Target missing" state for a target deleted after submit, which apply's
    re-validation will reject;
  - the creator, and the client as its `clientId` plus the client name in
    `<bdi>` labelled self-declared (`SelfDeclaredClientName.tsx`). AI-supplied
    titles, names and notes are also rendered in `<bdi>`.
- **Apply and reject** need a confirmation; reject takes an optional note.
  Apply sends the `reviewFingerprint` of the detail shown. On success the
  panel lists the created or changed keys and `$ref` keys and the Metrics tab
  reloads its grid. The reload discards unsaved grid edits, so the apply
  confirmation names the number of timeseries with unsaved changes and asks
  to save them first. `409 review_stale` reloads the detail, says that the
  replaced data changed and requires a fresh confirmation. The retryable
  `409 apply_in_progress` and any `503` keep the shown review and offer "Try
  again", which resends the same fingerprint without a reload or a new
  confirmation. Any other `409` (`not_submitted`, `apply_failed`) reloads the
  detail and shows the change set's current status. Reject maps the same
  codes the same way.

## Skills And Distribution (TASK-069N)

The skills teach what a model cannot infer from the tool docstrings. Each has
one source text in `backend/app/mcp/plugin/skills/<name>/SKILL.md`, with
frontmatter holding exactly `name` and `description`:

- `schatten-model-building`: agree the organisation and scenario, call
  `get_type_catalog` first and keep to its types and allowed connections,
  date nodes and edges with organisation-state target dates and keep edge
  lifetimes within node lifetimes, link timeseries to nodes following
  `timeserie_id_rule`, use `$ref` only for server-generated keys, follow the
  create → add → validate → fix → submit loop, and never claim that changes
  are applied before a person applies them. When the write server lists the
  apply tools (TASK-069O), it also teaches the in-chat review:
  `get_change_set_review`, showing the operations and replaced data and
  whether the user or another User staged it (`created_by` compared with
  `whoami`'s `id`), waiting for the user's explicit decision, then
  `apply_change_set` with the fingerprint or `reject_change_set`.
- `schatten-timeseries-generation`: choosing `timeUnit`, `unit` and
  `valueUnit`, realistic trend, seasonality (including `peakOffset`), noise,
  bound and seed parameters with worked example specs, date alignment,
  derived-metric formulas over short names, and always previewing with
  `preview_generated_timeserie` before staging the same spec.

The same files are distributed three ways:

| Channel | Where | For |
| --- | --- | --- |
| Claude Code plugin `schatten` | `backend/app/mcp/plugin/` (`.claude-plugin/plugin.json`, `.mcp.json` with `https://schatten.lupaus.eu/api/mcp/read` and `/api/mcp/write`, `skills/`), listed by the repository-root marketplace `.claude-plugin/marketplace.json` | Claude Code: `/plugin marketplace add reflector-oy/schatten`, then `/plugin install schatten@schatten` (needs read access to the repository) |
| Skill zip | `GET /api/v1/ai/skills/{name}.zip` in `backend/app/api/v1/ai_skills/router.py`, business session, `MCP_ENABLED=true` only | Upload to claude.ai or Claude Desktop (Customize, Skills) |
| MCP prompts | Read server prompts `model_building` and `timeseries_generation` | Any MCP client, including clients without skills support |

- `backend/app/mcp/skills.py` reads the files for the prompts and the zip
  route. It does not import `fastmcp`, so the zip route does not load it.
- A prompt has no arguments and returns the `SKILL.md` body (the Markdown
  after the frontmatter) as one user message; its description is the
  frontmatter `description`. No prompt changes data.
- The zip holds the skill folder under its own name (`<name>/SKILL.md`), as
  claude.ai uploads expect, with fixed timestamps so the same files always
  give the same bytes. An unknown name is `404 SKILL_NOT_FOUND`; with MCP
  disabled the route does not exist (404).
- The Metrics tab Connect section shows the plugin commands with copy buttons,
  a note on non-production origins that the plugin's servers are the
  production ones, and the zip links with short upload steps. It is hidden
  when `features.mcp` is false.
- Tests check the frontmatter, the plugin and marketplace JSON, and that every
  JSON example in the skills validates against the change-set operation and
  generation spec schemas, so the skills stay current with the tool
  contracts.

## MCP Change-Set Review (TASK-069O)

The 2026-10-29 amendment of ADR-015 lets an MCP client apply and reject
submitted change sets on behalf of its User, next to the Metrics tab review.

- `get_change_set_review(change_set_key)` (read server, always registered,
  read-only annotations) returns `ChangeSetReview`: everything
  `get_change_set` returns plus `replacements` (per operation
  `replaces_existing` and the summary of the current data it replaces) and
  `review_fingerprint`. `service.change_set_review` loads the change set,
  summary and operation rows in the review API's one statement
  (`_load_review`) and recomputes `compute_replacements` under the change-set
  statement timeout, so the fingerprint equals the review API's. A lock or
  statement timeout is the retryable busy tool error.
- With `MCP_CHANGE_SET_REVIEW_ENABLED=true` (and `MCP_ENABLED=true`) the write
  server registers two more tools, annotated `destructiveHint=True`,
  `idempotentHint=False` and `openWorldHint=False`, and its instructions
  describe the in-chat review (`REVIEW_INSTRUCTIONS`). The staging tools'
  descriptions also name it: `REVIEW_WORDING` replaces their "approved in
  Schatten" sentences, and `submit_change_set` points to
  `get_change_set_review`; a sentence missing from a docstring fails the
  server build. With the switch off the two tools are not registered and the
  instructions and staging tool docstrings say that a person applies in
  Schatten.

| Tool | Engine call | Result |
| --- | --- | --- |
| `apply_change_set(change_set_key, review_fingerprint)` | `apply_change_set` with `ReviewChannel.mcp(client_id, client_name)` | `ChangeSetApplied`: the summary, per-operation results with created keys, and `refs` |
| `reject_change_set(change_set_key, note=None)` | `reject_change_set` with the same channel, then commit | `ChangeSetSummary` with status `rejected` |

- Any submitted change set of a non-deleted organisation can be decided,
  whoever created it, as in the Metrics tab. The organisation is looked up
  from the change set (`service.organisation_key_of`). The grant's User is
  the reviewer and the actor of the created rows.
- `review_fingerprint` must be 64 lowercase hex characters. The `note` is at
  most 2,000 characters, may not contain NUL and is trimmed, blank meaning
  none.
- The engine's `ChangeSetApplyError` becomes a tool error `<code>: <message>`
  with the review API's codes: `review_stale` (read the review again and
  confirm with the user), `not_submitted`, `apply_in_progress` and
  `apply_unavailable` (retry), and `apply_failed`, which adds that the change
  set is now failed and a corrected one must be staged. An unknown change set
  is `Change set not found.`.
- `ReviewChannel` (`engine.py`) is passed explicitly to apply, reject and the
  conditional `failed` update. The review API passes `web`. Migration 019 adds
  `reviewed_via`, `review_client_id` and `review_client_name`, backfills
  `web` for change sets reviewed before it, and checks that the channel is
  set exactly with the review time and the client exactly for `mcp`. The
  review API list and detail return them as `reviewedVia`, `reviewClientId`
  and `reviewClientName`, and the Metrics AI panel shows "Reviewed through AI
  client (MCP)" with the self-declared client name.
- The session's `features.mcpChangeSetReview` is true only when both settings
  are on. It switches the consent page's write explanation, the connect
  instructions and the connections list's write badge ("Propose and apply
  changes").

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
get_change_set_review(change_set_key)
```

Read service MCP prompts (TASK-069N), served from the skills' `SKILL.md`
bodies: `model_building`, `timeseries_generation`.

Write service (`openWorldHint=False`):

```text
create_change_set(organisation_key, title, rationale)
add_operations(change_set_key, operations)
remove_operation(change_set_key, position)       destructiveHint
validate_change_set(change_set_key)              idempotentHint
submit_change_set(change_set_key)
discard_change_set(change_set_key)               destructiveHint
apply_change_set(change_set_key, review_fingerprint)   destructiveHint, only with MCP_CHANGE_SET_REVIEW_ENABLED
reject_change_set(change_set_key, note)          destructiveHint, only with MCP_CHANGE_SET_REVIEW_ENABLED
```

No other tool applies or rejects a change set.

---

# Timeserie Generation Specification

`TimeserieGenerationSpec` (TASK-069C,
`backend/app/api/v1/timeserie_generation/schemas.py`) is numeric-only and
validated. It is a `StrictBaseModel`: unknown fields are rejected, every
number must be finite, and JSON uses the camelCase aliases below (the
snake_case names are also accepted). Numeric fields are strict, because specs
come from AI clients: strings and booleans are never coerced to numbers, and
integer fields (`periods`, `decimals`, `seed`) also reject floats such as
`12.0`. Number fields accept integers. Dates should be given as ISO
`YYYY-MM-DD` strings. Date fields are not strict, so pydantic also parses some
other forms, such as Unix timestamps, but the alignment rules still apply.

| Field | Default | Rules |
| --- | --- | --- |
| `startDate` | required | Aligned to `timeUnit`: any day, a Monday, the 1st of a month or 1 January. An unaligned date is rejected with a validation error naming the rule. |
| `periods` | — | 1 to 20,000. Exactly one of `periods` or `endDate`. |
| `endDate` | — | Inclusive, not before `startDate`, need not be aligned. The last point is the last period start on or before it, and at most 20,000 points may result. |
| `timeUnit` | required | `day`, `week`, `month` or `year` (the existing timeserie literal). |
| `baseLevel` | required | Starting level of the trend, before level shifts, seasonality and noise. It is the `t = 0` value for the `none`, `linear` and `percent` trends; a `logistic` trend leaves it asymptotically, so its `t = 0` value depends on `midpoint`. |
| `trend` | `{"type": "none"}` | Tagged by `type`, see below. |
| `seasonality[]` | `[]` | At most 10 cosine cycles: `period` (periods per cycle, at least 2), `amplitude` (at least 0), `mode` (`additive` or `multiplicative`) and optional `peakOffset` (period index of the peak, default 0). A multiplicative amplitude is relative and at most 1. |
| `noise` | none | Gaussian noise with exactly one of `std` (absolute) or `relativeStd` (fraction of the noiseless value), and optional `ar1` in (-1, 1). |
| `levelShifts[]` | `[]` | At most 100 permanent steps: an aligned `date` and a `delta` added from that period onwards. |
| `clampMin`, `clampMax` | none | Optional bounds applied before rounding; `clampMin` must not exceed `clampMax`. Use bounds with at most `decimals` decimals. |
| `decimals` | 2 | 0 to 10. |
| `seed` | required | 0 to 2^32 - 1. |

Trends, with `t` the period index from 0:

| `type` | Parameters | Level |
| --- | --- | --- |
| `none` | — | `baseLevel` |
| `linear` | `slope` | `baseLevel + slope * t` |
| `percent` | `percentPerPeriod` (above -100) | `baseLevel * (1 + percentPerPeriod / 100) ** t`; a zero `baseLevel` stays zero |
| `logistic` | `capacity`, `growthRate` (above 0), `midpoint` | `baseLevel + (capacity - baseLevel) / (1 + exp(-growthRate * (t - midpoint)))` |

`generate(spec)` in `generator.py` returns `GeneratedPoint(date, value)` items,
one per aligned period start, computed as:

```text
level(t)   = trend(t) + sum of level shift deltas whose date <= date(t)
wave_i(t)  = cos(2 * pi * (t - peakOffset_i) / period_i)
value(t)   = level(t) * product(1 + amplitude_i * wave_i(t), multiplicative)
             + sum(amplitude_i * wave_i(t), additive)
             + noise(t)
result(t)  = round_half_to_even(clamp(value(t)), decimals)
```

Rounding is NumPy's round half to even, so `0.125` with two decimals becomes
`0.12` and `2.5` with no decimals becomes `2.0`.

Noise draws `numpy.random.default_rng(seed).standard_normal(n)` and, with
`ar1`, filters it into a stationary unit-variance AR(1) process, so `std`
remains the marginal standard deviation. `relativeStd` scales it by the
absolute noiseless value. The seed only affects noise. A rounded `-0.0` is
returned as `0.0`. A valid spec whose values overflow to non-finite numbers,
either before clamping or when rounding scales a value near the float limit by
`10 ** decimals`, raises `TimeserieGenerationError`. Generated dates and values pass the
existing timeserie value validation for `valueUnit` `number`.

Identical specs give identical output with the same generator version and
NumPy release. **`GENERATOR_VERSION` is `1`.** It is bumped whenever the same
spec can produce different values. NumPy's random streams are not guaranteed
across NumPy releases, which is why change sets freeze generated values with
the version at submit rather than regenerating at apply.

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
4. An anonymous user signs in with the existing Entra login and returns to
   the consent page.
5. The consent page shows the self-declared client name, the vendor host or
   the loopback notice, and the requested access. The user approves or
   denies; the browser then goes to the server-built redirect URL, which
   carries a one-time code on approval.
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
6. Alternatively, with `MCP_CHANGE_SET_REVIEW_ENABLED=true`, the AI reads
   `get_change_set_review`, shows the user the operations and the data they
   replace, and, on the user's explicit instruction, calls `apply_change_set`
   with the fingerprint or `reject_change_set`; the client asks the user to
   approve the call.

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

- adding any MCP tool other than `apply_change_set` that applies a change
  set, or any MCP write to business tables outside the engine's apply;
- registering the apply or reject tools without the switch, or applying
  without the review fingerprint;
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
