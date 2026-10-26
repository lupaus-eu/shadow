# ADR-015: AI Via MCP With Human-Applied Change Sets

Status: Accepted design; TASK-069B through TASK-069F implemented, TASK-069G through TASK-069O pending

Date: 2026-10-21

---

# Context

Users want to build Schatten organisation models (scenarios, organisation
states, graph nodes and edges, timeseries, derived metrics and events) and
realistic example timeseries with the help of an AI chat. Entering this data
by hand is slow, and an LLM is good at proposing structure but poor at emitting
thousands of consistent numbers.

The approved plan "AI chat via MCP for generating Schatten model and timeseries
data" (accepted 2026-10-21, see `tasks/TASK-069A-ai-mcp-architecture.md`)
records these developer decisions:

- AI uses Schatten only through the Model Context Protocol (MCP).
- MCP access uses the same people, roles and authentication as the rest of
  Schatten.
- MCP is split into a read service and a write service.
- Users run the AI on their own AI subscription in their own MCP-capable
  client, such as Claude Desktop, claude.ai or Claude Code. Schatten never
  calls an LLM and never stores LLM keys, so the design is provider-neutral.
- The write service only stages change sets. A human reviews each change set
  and applies or rejects it in the Metrics tab. No MCP tool can apply changes.
- No background worker is added and the prediction worker is not extended.
  All MCP work is short and synchronous.
- The architecture is documented as a C4 model in LikeC4, including a
  deployment view of how MCP is used.

Constraints from accepted decisions:

- ADR-004: FastAPI is the trusted authorization boundary. Browser sessions are
  opaque, hashed, `SameSite=Strict`, and every authenticated unsafe request
  needs the session CSRF token and the exact Origin. Both roles may use every
  business API in every organisation; Users administration is `admin`-only.
  Provider tokens are never stored or given to React.
- ADR-012: exactly one prediction worker; no generic background-job platform,
  broker, scheduler, retries or parallel processing.
- ADR-013: direct Entra with one shared single-tenant registration, exact
  issuer, `openid profile email`, no Graph, no `offline_access`; one public
  origin per environment with Caddy as the only public ingress on a
  resource-limited UpCloud host.

---

# Decision

## Scope And Status

This ADR is an accepted design. **No MCP client can use Schatten yet.** The
implementation is delivered by TASK-069B through TASK-069O; TASK-069B (the
domain service transaction cores, which change no REST behaviour), TASK-069C
(the deterministic timeseries generator, which adds no route), TASK-069D (the
MCP OAuth schema, which adds no route), TASK-069E (discovery, registration,
authorization request and consent API, registered only with
`MCP_ENABLED=true`) and TASK-069F (token, refresh and revoke endpoints,
registered only with `MCP_ENABLED=true`, `verify_access_token` and the
always-registered connections API) are implemented and the rest is pending.
The feature stays disabled (`MCP_ENABLED=false`) until TASK-069O's separately
approved production enablement.

| Task | Delivers |
| --- | --- |
| TASK-069B | Flush-only `*_in_transaction` cores for the domain services change sets need (implemented) |
| TASK-069C | Deterministic timeseries generator (implemented) |
| TASK-069D | MCP OAuth schema (`mcp_oauth_*`: clients, authorization requests, grants, tokens) (implemented) |
| TASK-069E | OAuth discovery, client registration, authorization request, consent API and Caddy routing (implemented) |
| TASK-069F | Token, refresh, revoke, `verify_access_token` and connections API (implemented) |
| TASK-069G | FastMCP foundation, bearer authentication, resource protection, first read tools |
| TASK-069H | Remaining read tools and generator preview |
| TASK-069I | Change-set schema and engine (dry-run and atomic apply) |
| TASK-069J | Write MCP tools for staging change sets |
| TASK-069K | Cookie-session change-set review API (apply, reject) |
| TASK-069L | SPA consent page and connections list |
| TASK-069M | Metrics tab AI panel and change-set review UI |
| TASK-069N | Skills, Claude Code plugin bundle, MCP prompts, skill zips |
| TASK-069O | End-to-end QA, runbook and approved production enablement |

## Provider Neutrality And No In-App LLM

Schatten exposes MCP and OAuth 2.1 only. The user brings any MCP-capable
client and AI subscription. Schatten has no in-app chat, never calls an LLM,
never stores an LLM API key and has no vendor SDK. Claude clients are the
first verified clients; TASK-069O also verifies at least one non-Claude MCP
client.

## Two MCP Services In The Existing FastAPI App

Two FastMCP servers run inside the existing FastAPI process and backend image,
using the MCP Streamable HTTP transport:

| Endpoint | Required scope | Purpose |
| --- | --- | --- |
| `/api/mcp/read` | `schatten.read` | Inspect organisations, scenarios, org states, type catalog, graph, timeseries, events and change sets; preview generated series; MCP prompts |
| `/api/mcp/write` | `schatten.write` | Create, edit, validate, submit and discard **draft change sets** only |

- Both servers run `stateless_http=True` with `json_response=True`. No MCP
  session state, server-sent event stream or long-running request is kept.
- Both servers are built inside `create_app()` and registered as exact routes
  (GET, POST, DELETE) wrapped in bearer authentication. `app.mount` is not
  used because it causes a trailing-slash redirect. One combined lifespan runs
  both session managers.
- With `MCP_ENABLED=false` (the default) the MCP endpoints, the public OAuth
  endpoints, the consent API and the skill zip download are not registered and
  return 404. The cookie-session connections API and change-set review API stay
  registered, so users and administrators can still revoke grants and humans
  can still review, apply or reject already staged change sets while MCP is
  disabled (see [Incident Procedure](#incident-procedure)). The session
  response gains a `features.mcp` flag, and the SPA hides the consent page,
  connect instructions and skill links when it is false; the connections list
  and the Metrics AI panel stay visible only when they have rows to show.
- Read tools are annotated `readOnlyHint`, `idempotentHint` and
  `openWorldHint=False`. Write tools are annotated `openWorldHint=False`, with
  `destructiveHint` on removal and discard.
- **Neither server has an apply tool.** No MCP tool, prompt or resource can
  change business data. Write tools change only draft change-set rows owned by
  the AI domain.
- Tools call existing domain service functions and reuse existing response
  schemas; they do not duplicate query logic or write other domains' tables.
- Users administration, session revocation, prediction requests and every
  other capability not listed in the tasks are not exposed through MCP.

### Dependency Approval

This ADR records the developer's approval, given with the accepted plan and
explicitly confirmed on 2026-10-22 during the TASK-069A review, of exactly one
new backend runtime dependency: **`fastmcp`**, pinned to a
compatible major version. TASK-069G must first verify compatibility with the
locked FastAPI and Starlette versions. If it is not compatible, the approved
fallback is the official `mcp` SDK's bundled FastMCP (`mcp.server.fastmcp`).
Only one of the two is added. No frontend dependency is approved.

TASK-069C declares `numpy` directly in `backend/pyproject.toml`. It is already
locked transitively through the forecasting stack, so `uv.lock` gains no new
package. The direct declaration is approved here and was confirmed on the
same date.

## Schatten As Its Own OAuth 2.1 Authorization Server

MCP clients authenticate as existing Schatten Users. Schatten is the OAuth 2.1
authorization server and the MCP resource server; the user signs in with the
existing Entra login.

Endpoints (public, outside `/api/v1`, `Cache-Control: no-store`, RFC 6749 JSON
errors, rate-limited as described in
[resource protection](#no-background-execution-and-resource-protection)):

| Endpoint | Standard | Contract |
| --- | --- | --- |
| `GET /.well-known/oauth-authorization-server` | RFC 8414 | Issuer `PUBLIC_ORIGIN`; grant types `authorization_code`, `refresh_token`; code challenge method `S256` only; scopes `schatten.read`, `schatten.write`; token endpoint auth method `none` |
| `GET /.well-known/oauth-protected-resource/api/mcp/read` and `.../write` | RFC 9728 | Resource `<origin>/api/mcp/<server>`, authorization server `PUBLIC_ORIGIN`, the server's one scope |
| `POST /api/oauth/register` | RFC 7591 | Dynamic Client Registration for public clients only |
| `GET /api/oauth/authorize` | OAuth 2.1 | Validates and stores a pending request, then redirects to the SPA consent page |
| `POST /api/oauth/token` | OAuth 2.1 | `authorization_code` with PKCE, and rotating `refresh_token` |
| `POST /api/oauth/revoke` | RFC 7009 | Token revocation |

Rules:

- **Registration** accepts only public clients. A requested
  `token_endpoint_auth_method` other than `none` is rejected with
  `invalid_client_metadata`, not silently overridden. Client metadata is
  bounded and sanitised:
  - `client_name` is required. A registration without it is rejected with
    `invalid_client_metadata`, and the column is `NOT NULL`. It is checked
    against an **ASCII allowlist**, not a Unicode denylist:
    1. leading and trailing ASCII spaces (U+0020 only) are trimmed;
    2. the trimmed name must be 1 to 100 characters long;
    3. every character must be an ASCII letter (`A-Z`, `a-z`), a digit
       (`0-9`), a space, or one of `. - _ ( ) : / +`;
    4. it must contain at least one ASCII letter or digit.

    Any other character anywhere in the name, including a tab, a newline,
    any other control or format character, a Unicode separator or any
    non-ASCII character, is rejected. Only edge spaces are trimmed, so the
    order of trimming and checking cannot matter. The trimmed name is what is
    stored, shown and logged. It is always shown, isolated from the
    surrounding text, and logged as a label the client declared itself.

    The allowlist is chosen over a Unicode denylist because it:
    - needs no Unicode tables or version-dependent categories;
    - excludes bidirectional overrides, zero-width and blank-rendering
      characters by construction;
    - excludes look-alike letters from other scripts, such as a Cyrillic `С`
      in place of a Latin `C`.

    The allowlist does not stop a client from copying a known client's name. It
    can register `Claude` exactly, or an ASCII look-alike such as `CIaude`.
    That is why the name is always labelled as self-declared and shown next to
    the redirect URI's host, or next to the loopback notice for a loopback
    redirect. The consent page only displays this; the server verifies the
    redirect URI against the `MCP_OAUTH_REDIRECT_URIS` allowlist. For an exact
    entry, such as a vendor connector callback, the host shows which vendor
    receives the code. For a loopback entry (`127.0.0.1`, `[::1]` or
    `localhost`), the host only identifies a program on the user's own machine,
    so the page shows the loopback notice instead. Local clients therefore
    cannot be told apart by name or host, and any local program can present
    itself as a known local client. This limitation is accepted: such a program
    already runs as the user, and the consent page's loopback notice says so.

    Accepted trade-off: a client cannot register until its name is changed if
    the name contains non-ASCII characters, or ASCII punctuation outside the
    set, such as `'`, `&`, `@`, `,`, `#`, `!`, `[` or `]`. Names such as
    `Jonatan's client` or `R&D tool` are therefore rejected. TASK-069O
    verifies that the real clients' names fit;
  - at most 10 redirect URIs of at most 2,048 characters each;
  - other metadata is ignored.

  Redirect URIs are checked against the `MCP_OAUTH_REDIRECT_URIS` allowlist
  after parsing them as URLs, never by string prefix or glob:
  - **Exact entries** (the claude.ai and claude.com connector callbacks) match
    only by exact string equality of the whole URI.
  - **Loopback entries** are written with a literal port placeholder, for
    example `http://127.0.0.1:{port}/callback`, `http://[::1]:{port}/callback`
    and `http://localhost:{port}/callback`. They are the only wildcard form. A
    parsed URI matches when the scheme is exactly `http`, the host is exactly
    the entry's host, the port is an explicit number from 1 to 65535, the path
    is exactly the entry's path, and there is no userinfo, query or fragment.
    `localhost` entries exist only because local MCP clients use them; RFC
    8252 section 8.3 prefers IP literals, and TASK-069O verifies the real
    clients' redirect URIs and trims the default allowlist accordingly.
  - Every other URI is rejected with `invalid_redirect_uri`. This includes a
    URI whose authority contains `@`, a percent-encoded or trailing-dot host,
    an `https` loopback URI or a missing port.
  - The authorization request must repeat a registered redirect URI by exact
    string equality. For loopback URIs only the port may differ from the
    registered value (RFC 8252 section 7.3); scheme, host and path may not.
- **PKCE S256 is mandatory.** A missing challenge or `plain` is rejected.
- The authorization request checks the client, the registered redirect URI,
  `response_type=code`, the scopes and the RFC 8707 `resource`. Invalid
  client or redirect URI errors are shown, never redirected. **Every other
  error is redirected** to the validated redirect URI, built by the same
  server-side builder as a successful response. The redirect carries `error`
  (for example `invalid_request`, `invalid_scope`, `invalid_target`,
  `access_denied` or `temporarily_unavailable`), `state` when the client sent
  one, and `iss` (RFC 9207), and nothing else.
- **Audience binding.** `resource` is required on both the authorization
  request and the token request, and it must equal one of the two canonical
  resource URIs `<PUBLIC_ORIGIN>/api/mcp/read` and
  `<PUBLIC_ORIGIN>/api/mcp/write` exactly. There is no trailing slash, query
  or fragment, and no other normalisation is applied. Each resource has
  exactly one scope (`schatten.read` or `schatten.write`). The requested
  `scope` must equal that scope, or be omitted, in which case it defaults to
  that scope. Any other scope set, including both scopes, is rejected with
  `invalid_scope`. A grant and all its tokens are bound to that one resource.
  Token verification takes the endpoint's resource and rejects a token issued
  for the other resource with `401 invalid_token`. A client that uses both
  services therefore holds two grants.
- The pending request id (10 minutes), authorization code (60 seconds, single
  use), access token and refresh token are CSPRNG values with at least 256
  bits of entropy. **Only SHA-256 hashes are stored.** Tokens are opaque, not
  JWTs.
- Lifetimes, all configurable:
  - Access tokens live 1 hour.
  - Refresh tokens rotate on every use and expire after 7 days without use
    (an idle timeout).
  - A grant has a 30-day absolute lifetime. It is stored as the grant's
    `expires_time`, anchored at grant creation, and never extended.
  - No token outlives its grant.
- **Reusing an already-rotated refresh token revokes the whole grant** and all
  its tokens. To keep this detectable, replaced refresh-token rows (hash,
  replacement link and expiry) are kept until their grant expires or is
  revoked. Lazy cleanup never deletes them earlier (see
  [resource protection](#no-background-execution-and-resource-protection)).
  Rotation sets only the old row's replacement link; it never sets the old
  row's `revoked_time`.
- **Refresh-token checks run in this order**, and the first match decides:
  1. the grant is revoked or past its `expires_time`: `invalid_grant`, no
     further effect;
  2. the token's `revoked_time` is set (for example after a re-authorization
     or an explicit revoke): `invalid_grant`, no further effect;
  3. the token has a replacement link: reuse detected, the grant and all its
     tokens are revoked, `invalid_grant`. This applies whatever the token's
     own idle expiry, so a replayed old token is detected for the whole grant
     lifetime;
  4. the token is past its own idle expiry: `invalid_grant`;
  5. otherwise the token is rotated.
- Redeeming an authorization code a second time fails and revokes the grant
  and every token issued from that code (OAuth 2.1).
- A User's repeated authorization of the same client and resource (and
  therefore the same single scope) reuses that User's existing grant only
  when it is active, that is not revoked and not past its `expires_time`.
  Reuse does not extend the grant's absolute lifetime, and it revokes all of
  the grant's earlier access and refresh tokens before issuing the new pair. A
  stale refresh chain then fails as revoked and cannot trigger reuse
  detection against the fresh authorization. Without an active grant, a new
  grant is created.
- Accepted consequence: when one client registration serves several
  concurrent sessions of the same User and resource, re-authorizing in one
  session signs the others out, because the reused grant's earlier tokens are
  revoked. TASK-069O verifies the effect with the real clients and records it
  in the runbook.
- **Grant deletion and references.** Lazy cleanup deletes revoked or expired
  grants, as described in
  [resource protection](#no-background-execution-and-resource-protection).
  The references to a grant behave as follows:
  - its tokens are deleted with it (`ON DELETE CASCADE`);
  - `ai_change_sets.grant_id` is `ON DELETE SET NULL`. The change set's
    lasting audit record is:
    - `created_by`;
    - `client_id`, the registered OAuth client identifier, copied as a plain
      value and not a foreign key, so it survives client deletion;
    - `client_name`, which the client declares itself and which is shown only
      as a label.

    Change-set history, including applied change sets, is never deleted and
    never blocks cleanup;
  - `mcp_oauth_authorization_requests.grant_id` is also `ON DELETE SET NULL`.
    Authorization requests expire after ten minutes and are deleted by the
    same cleanup. A second redemption fails in either case:
    - if the request row still exists but its grant is gone, it fails as an
      already-consumed code (`invalid_grant`) with nothing left to revoke;
    - if the request row is gone, it fails as an unknown code;
  - grant revocation is also written as an application log entry with the
    actor, target User id, grant key, `client_id`, sanitised client name,
    reason and revoked count, and never a token. The revocation audit
    therefore survives the grant row's deletion.

### Authorization And Consent Flow

```text
MCP client -> GET /api/mcp/<server>               401 + resource_metadata
MCP client -> GET /.well-known/oauth-*            discovery
MCP client -> POST /api/oauth/register            client_id
Browser    -> GET /api/oauth/authorize            303 /ai/authorize?request=<id>
SPA        -> (anonymous) /api/v1/auth/login?return_to=/ai/authorize?request=<id>
           -> existing Entra login, guarded linking, session cookie
SPA        -> GET  /api/v1/ai/oauth/consent?request=<id>        client, redirect host, scopes
SPA        -> POST /api/v1/ai/oauth/consent/approve {request}   CSRF + exact Origin
           <- { redirectUrl }                                   built by the server
SPA        -> window.location.assign(redirectUrl)
MCP client -> POST /api/oauth/token               access + refresh token
```

- The browser session cookie is `SameSite=Strict`, so it is not sent on the
  cross-site navigation from the AI vendor to `/api/oauth/authorize`. The
  authorize endpoint therefore only validates and stores the request and hands
  over to the SPA, where same-origin calls carry the session. Anonymous users
  go through the unchanged `GET /api/v1/auth/login?return_to=` flow.
- The consent API (`GET /api/v1/ai/oauth/consent`,
  `POST /api/v1/ai/oauth/consent/approve` and `.../deny`) uses the normal
  business session and returns `Cache-Control: no-store`. Approve and deny use
  the existing unsafe-request guard (session CSRF token and exact Origin). A
  request can be decided once. Approval records the User; deny returns an
  `access_denied` redirect URL.
- **The server builds the redirect URL** and returns it as `redirectUrl`; the
  SPA navigates only to that value and never composes a URL from a redirect
  URI. The server adds `code`, `state` (omitted when the client sent none)
  and `iss` (RFC 9207, advertised as
  `authorization_response_iss_parameter_supported`) to the registered redirect
  URI. Loopback and exact redirect URIs carry no query of their own, so
  nothing is merged or overwritten.
- The consent page shows the client name, labelled as self-declared by the
  client, and the requested access in plain words. For a redirect URI that
  matched an exact allowlist entry it shows the redirect URI's host. For one
  that matched a loopback entry it shows a loopback notice instead: the code
  goes to a program on this computer, and local programs cannot be verified
  by name. The server decides which case applies from the allowlist entry
  that matched and returns it to the SPA, so the SPA never parses host
  strings. The page does not show the request id.
- The redirect is a script navigation, not a form submission, so the CSP
  `form-action 'self'` in ADR-004 is unchanged.

### Pending Request Id Handling

The pending request id is a lookup handle, not a credential: deciding a
request needs an authenticated session and CSRF. It still must not be logged
or stored in plaintext in the `mcp_oauth_*` tables, which hold only its hash.
It may be persisted for up to ten minutes inside the existing login
transaction's `return_to` (`oidc_login_transactions`). Every place it travels
has a named control:

| Where the id appears | Control |
| --- | --- |
| `303 Location: /ai/authorize?request=<id>` from `/api/oauth/authorize` | Caddy log filter replaces `resp_headers>Location` with `REDACTED` |
| SPA page request `/ai/authorize?request=<id>` | Caddy log filter redacts the `request` query parameter |
| `/api/v1/auth/login?return_to=<encoded path with id>` | Caddy log filter redacts the `return_to` query parameter; the backend access-log filter redacts `return_to` |
| Consent lookup `GET /api/v1/ai/oauth/consent?request=<id>` | Caddy and backend access-log filters redact `request` |
| Approve and deny | The id travels in the JSON body, never in the URL path; bodies are not logged |
| Browser `Referer` | The existing `Referrer-Policy: no-referrer` |

- **No URL path carries the id.** Path-based consent routes such as
  `/requests/{id}` are not used.
- Both `frontend/Caddyfile` and `local/Caddyfile` extend their existing `log`
  `format filter`. The query filter also replaces `request` and `return_to`,
  `resp_headers>Location` is replaced, and the `Authorization` request header
  is replaced explicitly rather than relying on Caddy's default. Replacing
  `Location` also removes the Entra `state` that ADR-004's login redirect
  already carries there.
- The backend's existing sensitive-query access-log filter
  (`backend/app/api/v1/auth/logging.py`) extends its key list with `request`
  and `return_to`. Application logs never include the id, codes, tokens or
  tool arguments.

- **The Entra registration does not change.** No callback, scope, permission,
  app role or Graph call is added, because the only Entra interaction is the
  existing login.

### Rejected: FastMCP OAuthProxy / AzureProvider

FastMCP can proxy OAuth to an upstream provider such as Entra. It is rejected
because it would:

- change ADR-013: new Entra callbacks, exposed API scopes and likely
  `offline_access` on the shared registration;
- duplicate user linking: Entra identities would be mapped to Users outside
  ADR-004's guarded first link and permanent `(issuer, subject)` ownership;
- store upstream Entra tokens, which ADR-004 and ADR-013 forbid; and
- make revocation and per-request role re-reads awkward, because the tokens
  would not be tied to revocable Schatten grants and the database role.

Also rejected: Entra as the direct authorization server for MCP clients
(no Dynamic Client Registration, needs registration changes per client) and
personal static API keys (no consent, poor MCP client support, long-lived
secrets in user configuration).

Future work: **Client ID Metadata Documents** (CIMD) as an alternative to
Dynamic Client Registration, once supported clients adopt it.

## Authorization On Every MCP Request

`McpBearerAuth` wraps both MCP endpoints and on every request:

1. reads `Authorization: Bearer`, hashes the token and loads it as an
   unexpired, unrevoked access token;
2. checks its grant is not revoked, not past its `expires_time`, and bound to
   this endpoint's canonical resource; a token for the other resource gets
   `401 invalid_token`;
3. loads the grant's User and rejects a soft-deleted User; this **re-reads the
   current database role** on every call;
4. computes effective scopes as
   `grant.scopes ∩ allowed_scopes_for_role(user.role)`; and
5. requires the endpoint's scope.

Failures return `401` with
`WWW-Authenticate: Bearer resource_metadata="<origin>/.well-known/oauth-protected-resource/api/mcp/<server>"`
(with `error="invalid_token"` when a token was presented), or `403` with
`WWW-Authenticate: Bearer error="insufficient_scope", scope="<endpoint scope>", resource_metadata="..."`. The principal (User, role, grant, client name,
effective scopes) is placed in a context variable; tools use it as the actor.
`last_used_time` is written at most every five minutes.

Both current roles, `admin` and `consultant`, are allowed both scopes. This
matches ADR-004, where both roles use every business API in every
organisation. The role mapping exists so that a future role can be limited
without a token format change.

MCP endpoints accept only bearer tokens and never the browser session cookie;
`/api/v1` accepts only the session cookie and never an MCP token. Because MCP
requests carry no ambient browser credential, the cookie CSRF guard does not
apply to them. No CORS is added; browser-hosted MCP clients that need CORS are
not supported. ADR-004's rule of no provider refresh tokens is unchanged: MCP
refresh tokens are Schatten-issued, hashed and revocable.

Users list and revoke their own grants through the cookie-session
connections API (`/api/v1/ai/connections`). An `admin` can revoke all grants of
one User through `POST /api/v1/ai/users/{user_id}/connections/revoke`
(session, CSRF, exact Origin, `admin` only, like Users administration in
ADR-004). Deleting a User, revoking a grant, grant expiry or disabling
`MCP_ENABLED` stops MCP access on the next request. ADR-004's admin session
revocation ends browser sessions only and does not touch grants.

### Accepted Trade-Off Against ADR-004 Session Bounds

ADR-004 accepts that Entra-side changes are not re-checked during a browser
session because sessions are bounded by a 30-minute idle timeout and an
eight-hour absolute lifetime. An MCP grant is longer-lived: up to 30 days,
renewed by refresh-token rotation, with a 7-day refresh idle timeout and no
Entra re-check. A User disabled in Entra but not soft-deleted in Schatten keeps
MCP access until the grant expires, goes idle or is revoked. This is an
accepted trade-off of this ADR. ADR-004's browser-session bounds are
unchanged. The mitigations are:

- every MCP request re-reads the User and role, so soft deletion and role
  changes act immediately;
- **offboarding must soft-delete the Schatten User** (or an admin must revoke
  the User's grants); disabling the Entra account alone is not enough; and
- the per-user admin revocation and the incident procedure below.

### Incident Procedure

The incident procedure needs no manual database change:

1. An operator sets `MCP_ENABLED=false` and restarts the backend through the
   approved deployment procedure. All MCP and OAuth endpoints then return 404,
   so no token works and no new grant can be issued.
2. While MCP is disabled, an `admin` revokes the grants of every affected User
   through the per-user revocation endpoint (or soft-deletes the User), and
   Users may revoke their own grants. The connections and review APIs stay
   registered for this.
3. Humans reject any suspicious staged change sets in the Metrics tab.
4. MCP is re-enabled only with the separate human approval that TASK-069O
   defines for enablement.

TASK-069O documents this procedure in the runbook.

## AI Change Sets

The AI domain owns change sets: `ai_change_sets` and
`ai_change_set_operations`. A change set belongs to one organisation and holds
an ordered list of typed operations, a title and a rationale. It records the
creating User, the grant, the copied `client_id` and the client name. See
`docs/concepts/AI_CHANGE_SET.md`.

A change set also has an optional **scenario reference** (`scenario_key`). It
is derived from the operations, not chosen by the client. The engine
recomputes it whenever operations change. It is set when every operation
targets the same existing scenario, either directly or through an
organisation state, node, edge, timeserie or event in it. It is null when the
change set creates or copies a scenario, or touches several scenarios. The
review list filters by this reference.

Operation types (a discriminated union on `type`; payloads reuse the existing
request schemas):

```text
create_scenario, copy_scenario, create_org_state,
create_node, create_edge, patch_node,
create_timeserie, set_timeserie_values, generate_timeserie_values,
create_derived_metric, create_event
```

- **`$ref` covers only server-generated keys.** Scenarios (created or
  copied), organisation states, events and derived metrics get their keys
  from the server, so an operation that creates one may declare a `"$ref"`
  symbol. Later operations use that symbol where the key is needed, resolved
  in order. Graph nodes, graph edges and timeseries take client-supplied keys
  (`id`), as in REST. Later operations, such as an edge between two new
  nodes, refer to those keys verbatim without `$ref`. A client-supplied key
  that starts with `$`, and a `$` symbol that no earlier operation declares,
  are rejected.
- Lifecycle:

  ```text
  draft -> submitted -> applied
                     -> rejected
                     -> failed
  draft -> discarded
  ```

- Only `draft` change sets can be edited, and only through grants of the User
  who created them. Other Users may read them.
- **Dry-run** (`validate_change_set`) runs the operations in order through the
  domain services in a fresh session guarded against commit and **always rolls
  back**. SAVEPOINTs are not used, so after a database error the transaction
  cannot continue. Dry-run therefore **stops at the first failing operation**:
  - earlier operations report `ok`;
  - the failing operation reports its error;
  - every later operation reports `not_run`.

  The session is rolled back and cleared of pending objects before the result
  is stored and returned, so a failure that is not a database error cannot
  leak pending rows into the stored result.
- **Submit** re-validates and **freezes generated values** together with the
  generator version. A submitted change set is immutable. Submit returns the
  review URL `<PUBLIC_ORIGIN>/schatten/<org>/metrics?changeSet=<key>`.
- **Human review is required.** Apply and reject happen only in the Metrics
  tab through cookie-session endpoints with CSRF and exact Origin
  (`/api/v1/organisations/{organisation_key}/ai/change-sets/...`). Both roles
  may review, including the creator: the AI acts on the creator's behalf and
  the human apply is the gate between AI output and business data.
- **Apply** runs in this order, in one transaction:
  1. lock the change set `FOR UPDATE` under a short, configurable PostgreSQL
     `lock_timeout` (default 5 seconds). Both timeouts apply to the lock wait,
     and the short `lock_timeout` fires before the longer
     `statement_timeout`;
  2. require `submitted`, otherwise `409`;
  3. recompute the replacement flags and compare the `reviewFingerprint`,
     otherwise `409 review_stale`;
  4. re-validate against current data;
  5. execute all operations with the frozen values through the domain
     services' `*_in_transaction` cores;
  6. commit once.

  The reviewer is the actor for the created business rows. A concurrent apply
  applies once; others get 409.
  - **The step alone decides whether the status changes.** An error in steps
    1 to 3 never changes the status, and an error in steps 4 to 6 marks the
    change set `failed`, whatever its error type or SQLSTATE. The same lock
    timeout or statement timeout is therefore a pre-re-validation error in
    steps 1 to 3 and an operation failure in steps 4 to 6.
  - **Errors in steps 1 to 3** roll back without changing anything and never
    write `failed`. They are:
    - the terminal `409` for a change set that is not `submitted` (step 2);
    - `409 review_stale` when the fingerprint differs (step 3). The change set
      stays `submitted`, so the reviewer can reload and confirm again;
    - `409 apply_in_progress` when acquiring the step-1 change-set lock fails
      with the lock-not-available error (SQLSTATE `55P03`), because another
      transaction holds the lock beyond `lock_timeout`. That is normally a
      concurrent apply, or briefly lazy grant cleanup setting the change
      set's grant reference to null. It is retryable, and its code
      distinguishes it from the terminal not-submitted `409`;
    - `503` for any other unexpected error in these steps, for example a
      statement timeout during the fingerprint recomputation. It is
      retryable.
  - **Only a failure in steps 4 to 6 marks the change set `failed`.** That is a
    re-validation error, an operation error, a lock timeout or statement
    timeout during re-validation or execution (for example while waiting for a
    business row that a REST transaction holds), or a commit error. Everything
    rolls back, and then, in a new transaction, the change set becomes `failed`
    with the error through a conditional update that changes only a change set
    still in `submitted`. A concurrent apply that has meanwhile succeeded is
    therefore never overwritten. A failed change set is not retried; the AI
    stages a new one.
  - **The `lock_timeout` covers the whole apply transaction**, not only the
    step-1 lock. A wait of more than `lock_timeout` for a business row during
    re-validation or execution, for example behind a slow REST transaction,
    therefore makes the change set permanently `failed`, and the AI must
    stage a new one. This is accepted: such waits are rare, and an unbounded
    wait would hold the change-set lock.
- **Re-validation checks validity, not general staleness.** Apply runs the
  same domain validation as REST against current data: references must exist,
  keys must be unique, and values must be valid. Apart from the replacement
  fingerprint below, it does not detect that a human changed the data after
  submit. Operations that replace existing data
  (`patch_node`, `set_timeserie_values` and `generate_timeserie_values` on an
  existing timeserie) overwrite the current values at apply time, as the same
  REST call would. The review UI therefore **flags every operation that
  replaces existing values** and shows what it replaces, so the reviewer
  decides with that in view.
- **Replacement flags are computed against current data.**
  - The baseline is data that existed before the change set. An operation on a
    row created earlier in the same change set (a node, or a timeserie and its
    values) is never flagged.
  - The flags (`replaces_existing`) and their summaries are recomputed
    read-only against current data whenever the review detail is read, not
    taken from submit time. A timeserie that gained values after submit is
    therefore flagged. The summaries hold:
    - for `patch_node`, the patched fields with their current values;
    - for value replacement, the existing value count and date range; and
    - for every flagged target, a **per-target value checksum**: SHA-256 over
      the target's current replaced data in a canonical order (all date and
      value pairs of the timeserie, or the patched node fields and values).
  - Reading the review detail runs under the same PostgreSQL
    `statement_timeout` as dry-run and apply. A target deleted after submit
    is reported in its summary as missing rather than raising, and
    re-validation at apply then fails.
  - The review detail returns a `reviewFingerprint`, a hash of the recomputed
    flags, summaries and checksums, and apply must send it back. Apply
    recomputes them inside its locked transaction. If the fingerprint
    differs, apply fails with `409 review_stale` without changing anything,
    the UI reloads the change set, and the reviewer must confirm again. The
    fingerprint differs when the flagged summaries changed after the reviewer
    loaded the change set: a flag, a summary or any flagged target's data,
    including an individual timeserie value.
  - Accepted remaining window: apply locks only the change-set row, not the
    target business rows. A REST commit to a flagged target between apply's
    recomputation and its writes, inside the same short transaction, is still
    overwritten. This window is accepted.
- Change sets call other domains' service cores and **never write their
  tables directly**. Domain validation, audit columns and derived-metric
  recalculation therefore stay the same as for REST.

## Deterministic Timeseries Generator

Schatten generates timeseries values from a validated, numeric-only
`TimeserieGenerationSpec`: start date and either periods or end date, time
unit, base level, trend (`none|linear|percent|logistic`), additive or
multiplicative seasonality, noise (`std` or `relative_std`, optional AR(1)),
level shifts, optional clamps, decimals and a seed. It uses
`numpy.random.default_rng(seed)`, so identical specs give identical output,
and records `GENERATOR_VERSION`. Dates align to the existing timeserie rules
(Monday weeks, first-of-month months, 1 January years). One spec produces at
most 20,000 points.

**The LLM chooses the parameters; it never emits the values itself.** The
read tool `preview_generated_timeserie` returns statistics and samples and
persists nothing. `generate_timeserie_values` operations store the spec and
are frozen to concrete values at submit, so a human reviews exactly the values
that apply.

## Skills

Repository-owned `SKILL.md` files (`schatten-model-building`,
`schatten-timeseries-generation`) under `backend/app/mcp/plugin/` teach the
workflow and contracts that a model cannot infer from tool docstrings. The same
files are distributed as:

- a Claude Code plugin with a repository-root marketplace;
- per-skill zip downloads for claude.ai and Claude Desktop
  (`GET /api/v1/ai/skills/{name}.zip`, business session); and
- read-server MCP prompts (`model_building`, `timeseries_generation`), which
  any MCP client can use.

There is one source text per skill and no duplicated copy.

## No Background Execution And Resource Protection

There is no background execution for MCP. No worker, queue, scheduler or
`prediction_requests` use is added, and ADR-012's single prediction worker is
neither extended nor called. Every MCP request completes synchronously and
quickly. Long work is prevented by limits rather than moved to the
background.

Resource protections on the shared, resource-limited host:

- a shared `anyio.CapacityLimiter` (configurable, default 4) for MCP tool
  database work, run in worker threads with their own sessions;
- **separate in-process limiters.** Two new instances of the existing
  `FixedWindowRateLimiter` are added, each with its own entry bound, so OAuth
  and MCP traffic can never fill the login limiter `auth_rate_limiter`:
  - `oauth_rate_limiter` for the public OAuth endpoints, with a separate
    configurable bucket per endpoint, all keyed by client IP:
    - `register`, `token` and `revoke` get higher limits, because the vendor's
      connector broker calls them for every vendor-cloud user from the
      vendor's shared egress addresses;
    - `authorize` keeps a low limit, because it comes from the user's own
      browser;
  - `mcp_rate_limiter` for `/api/mcp/*`, per grant.

  TASK-069O verifies the defaults against real vendor-cloud and local
  clients. Both limiters assume one backend replica, as in ADR-004.
- **bounded OAuth rows.** At most a configurable number of live pending
  authorization requests per client (default 20) and in total (default
  1,000); beyond that `authorize` answers `temporarily_unavailable`.
- **client lifecycle.**
  - A client's `last_used_time` is updated when it is issued a grant or token,
    at most every five minutes. Authorize locks the client row (`SELECT ... FOR
    NO KEY UPDATE`) at its initial client check, in the same transaction that
    stores the pending request, and requires that it is not soft-deleted.
    Cleanup therefore cannot soft-delete or hard-delete that client until
    authorize commits. Cleanup locks candidate clients with `FOR UPDATE SKIP
    LOCKED`, an update-strength lock because it may delete the row, and skips a
    locked client instead of waiting. Authorize updates the client's
    `last_used_time` only after the request has been fully validated and
    stored. A client in the middle of a valid consent flow is therefore never
    stale, failing authorize calls never keep a client alive, and the
    pending-request insert can never meet a deleted client. `FOR NO KEY UPDATE`
    is used instead of `FOR UPDATE` because it still conflicts with cleanup's
    locks, updates and deletes, but not with the key-share lock that a grant
    insert for the same client takes. Grant inserts therefore never wait for an
    in-flight authorize. A token exchange's own update of the client's
    `last_used_time` does conflict, so it can wait briefly until authorize
    commits. To keep that rare, token operations update the client's
    `last_used_time` at most every five minutes, as for grants.
  - Lazy cleanup soft-deletes (`deleted_time`) clients with no active grant
    and a `last_used_time` (or creation time) older than 30 days. A
    soft-deleted client cannot authorize or obtain tokens.
  - Cleanup then hard-deletes soft-deleted clients that no authorization
    request and no grant references any more. Change sets keep the copied
    `client_id` and `client_name`.
  - Client row growth is therefore bounded by the registration rate over the
    30-day window, and also by a configurable cap on non-deleted clients
    (default 10,000).
    - `register` runs the lazy client cleanup first, then checks the cap.
    - Beyond the cap it answers HTTP 503 with `temporarily_unavailable` and
      writes a warning log entry, so operators notice.
    - Accepted trade-off: sustained registration at the allowed rate can fill
      the cap and block new client registrations until stale clients age out
      (up to 30 days). Existing clients and grants keep working. The
      immediate operator remedy, documented in the TASK-069O runbook, is to
      raise the cap through configuration. Lowering the registration rate
      limit only slows refilling and does not unblock a full cap.
  - A client that registers again gets a new `client_id`.
- a PostgreSQL `statement_timeout` for dry-run, apply and the review detail's
  replacement recomputation (configurable, default 30 seconds). Settings
  validation at startup requires it to be longer than the apply
  `lock_timeout`. The step-1 lock wait therefore always ends with the
  lock-not-available error (`409 apply_in_progress`), never with a statement
  timeout (`503`);
- operation and value limits: at most 500 operations and 20,000 values per
  change set and 20,000 points per generator spec, plus bounded read-tool
  responses that report truncation; and
- lazy cleanup during token and registration operations, without a scheduler.
  It deletes expired authorization requests, expired access tokens, and revoked
  or expired grants together with all their tokens. It also soft-deletes and
  then hard-deletes clients as described in the client lifecycle above.
  **Replaced refresh tokens of an active grant are never deleted**, because
  refresh-token reuse detection depends on them. Deleting a grant sets the
  references to it in change sets and authorization requests to null (see grant
  deletion and references above).

## Data Leaving Schatten

**Business data read through MCP flows to the user's AI vendor** (for example
Anthropic) under the user's own subscription and that vendor's terms. Schatten
cannot control the vendor's processing or retention. This is an accepted
product and security decision:

- the consent page names the client and explains read and write access;
- a user can grant read without write and revoke any grant at any time;
- operators can disable the feature with `MCP_ENABLED=false`; and
- users are expected to use AI subscriptions their organisation approves.

Business text returned by read tools is untrusted input to the AI and may try
to steer it (prompt injection). Because no MCP tool can apply changes, the
worst outcome is a staged change set that a human must still review.
Tokens, codes, request ids and tool arguments are never logged; see
[Pending Request Id Handling](#pending-request-id-handling) for the Caddy and
backend log filters.

## Routing And Deployment

No Compose service, container, public port, domain or Entra change is added.

- Caddy remains the only public ingress. Its API matcher becomes
  `@api path /api /api/* /.well-known/oauth-authorization-server* /.well-known/oauth-protected-resource*`
  in both `frontend/Caddyfile` and `local/Caddyfile`. This extends ADR-013's
  `/api` and `/api/*` routing without changing anything else in it.
- Production MCP URLs: `https://schatten.lupaus.eu/api/mcp/read` and
  `https://schatten.lupaus.eu/api/mcp/write`.
- Vendor-cloud connectors (claude.ai, and Claude Desktop custom connectors,
  which are brokered by the vendor cloud) call the production origin from the
  vendor's servers. Local clients such as Claude Code call it from the user's
  workstation.
- Development uses `https://app.localhost`. Vendor-cloud connectors cannot
  reach localhost, so local testing uses a local client such as Claude Code
  with `NODE_EXTRA_CA_CERTS` trusting the local Caddy CA.

## Diagram Tooling

LikeC4 is the accepted tool for this feature's C4 model, because one model
produces the context, container, component, deployment and dynamic views
consistently. Sources live in `docs/diagrams/likec4/schatten-ai-mcp/`; PNG
exports are committed as `docs/diagrams/generated/likec4-<view>.png`. LikeC4
runs through `npx` pinned to `likec4@1.60.0` and is not a project dependency.
Existing PlantUML diagrams remain as they are, and PlantUML remains the default
for other diagrams.

Views:

- [index](../diagrams/generated/likec4-index.png) (C4 L1)
- [schattenContainers](../diagrams/generated/likec4-schattenContainers.png) (L2)
- [backendComponents](../diagrams/generated/likec4-backendComponents.png) (L3)
- [productionMcp](../diagrams/generated/likec4-productionMcp.png) (deployment)
- [developmentMcp](../diagrams/generated/likec4-developmentMcp.png) (deployment)
- [connectFlow](../diagrams/generated/likec4-connectFlow.png) (dynamic)
- [generateFlow](../diagrams/generated/likec4-generateFlow.png) (dynamic)

---

# Options Considered

- **In-app LLM chat calling a vendor API:** rejected. It needs stored API keys,
  vendor coupling and billing, and the users already have AI subscriptions and
  MCP-capable clients.
- **One MCP service with mixed scopes:** rejected. Separate read and write
  services let users connect read-only clients and make the write surface
  explicit.
- **An MCP apply tool, with or without confirmation:** rejected. AI clients may
  act on untrusted text; applying business changes needs a human decision in
  Schatten.
- **Direct writes from MCP tools:** rejected for the same reason, and because
  multi-step model creation must be all-or-nothing.
- **Background jobs for MCP or for change-set apply:** rejected. ADR-012 allows
  one prediction worker only, and bounded synchronous work fits the host.
- **LLM-emitted values:** rejected. They are slow, token-expensive,
  inconsistent and not reproducible; a seeded generator is.
- **FastMCP OAuthProxy/AzureProvider, Entra as MCP authorization server,
  static API keys:** rejected as described above.
- **PlantUML C4 for this feature:** not chosen. Keeping context, deployment and
  dynamic views of the same model consistent is easier in LikeC4.

---

# Consequences

Benefits:

- Users can model and generate data with any MCP-capable AI client without
  Schatten handling LLM keys or costs.
- MCP access is tied to existing Users, roles and Entra login; role changes,
  user deletion and revocation take effect on the next call.
- Business data changes only through a reviewed, atomic, audited human apply
  that uses the same domain services as REST.
- Generated data is reproducible from its spec and seed.
- No new runtime service, worker, port or Entra change.

Costs, risks and accepted trade-offs:

- Schatten becomes an OAuth authorization server and must implement and test
  its endpoints carefully; this is the largest security surface of the
  feature.
- Business data read through MCP leaves Schatten to the user's AI vendor.
- Development cannot be tested with vendor-cloud connectors.
- MCP work shares the API process and host with the prediction worker; limits
  are the protection, not isolation.
- In-process rate limits assume one backend replica.
- A business-row lock wait longer than `lock_timeout` during apply makes the
  change set `failed`; the AI stages it again.
- The client cap can be filled by sustained registration and then blocks new
  client registrations for up to 30 days. Operators raise the cap as the
  immediate remedy; lowering the registration rate limit only slows
  refilling (see the client lifecycle).
- MCP grants outlive ADR-004's browser-session bounds (up to 30 days, no Entra
  re-check); offboarding must soft-delete the User or revoke the User's
  grants (see the accepted trade-off above).
- Apply validates but does not detect general staleness. It can overwrite
  values a human changed after submit, but only on operations the reviewer
  saw flagged against current data. A change to the flagged summaries or
  their per-target checksums after the review load makes apply fail with `409
  review_stale`, except within the short accepted window inside apply's own
  transaction.
- One new backend dependency (`fastmcp` or the fallback `mcp`).
- A second diagram tool (LikeC4) is used for this feature.

---

# Implementation Rules

- Follow the task order in [Scope And Status](#scope-and-status). Each task
  implements only its own scope; dependencies other than those approved here
  need separate approval.
- Never add an MCP tool, prompt or resource that applies a change set or
  writes business tables.
- Never store plaintext tokens, codes or request ids in the `mcp_oauth_*`
  tables, and never log them or tool arguments.
- Never accept the session cookie on `/api/mcp/*` or an MCP token on
  `/api/v1`.
- Change sets use other domains' `*_in_transaction` cores only.
- Keep `MCP_ENABLED=false` by default. Production enablement needs separate
  human approval under TASK-069O.
- If the implementation differs from the LikeC4 model, update the model and
  its PNG exports in the same task.

---

# Follow-Up

- TASK-069B through TASK-069O implement this design.
- Client ID Metadata Documents, more operation types (for example edge and
  event patches) and further roles are separate future decisions.
- Reassess per-grant rate limiting and the capacity limiter before running
  more than one backend replica.

---

# References

- `docs/decisions/ADR-002-database-migrations.md`
- `docs/decisions/ADR-004-authentication.md`
- `docs/decisions/ADR-012-background-prediction-requests.md`
- `docs/decisions/ADR-013-shared-entra-local-https-deployment.md`
- `docs/domains/AI.md`
- `docs/concepts/AI_CHANGE_SET.md`
- `docs/diagrams/likec4/README.md`
- `tasks/TASK-069A-ai-mcp-architecture.md`
