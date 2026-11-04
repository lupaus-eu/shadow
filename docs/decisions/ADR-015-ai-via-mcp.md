# ADR-015: AI Via MCP With Human-Applied Change Sets

Status: Accepted design, amended 2026-10-29 (MCP change-set review,
TASK-069O) and 2026-11-03 (one MCP service with two scopes, TASK-074);
implemented by TASK-069B through TASK-069P and TASK-074; enabled in production
on 2026-11-03 after its separate approval (`v0.2.0`); the 2026-11-03
amendment reaches production only with its own separately approved release

Date: 2026-10-21

Amended: 2026-10-29 ([MCP Change-Set Review](#mcp-change-set-review)),
2026-11-03 ([One MCP Service In The Existing FastAPI App](#one-mcp-service-in-the-existing-fastapi-app)
and [Per-Tool Scope Check](#per-tool-scope-check))

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

Amendment (2026-10-29, `tasks/TASK-069O-mcp-change-set-review.md`): the
developer asked that users can also apply and reject submitted change sets
from their MCP client, such as Claude Code or Claude Desktop, in addition to
the Metrics tab. This replaces the decision that no MCP tool can apply
changes. The developer decided that:

- the write service gains apply and reject tools, registered only when an
  operator switch `MCP_CHANGE_SET_REVIEW_ENABLED` is on (default off); OAuth,
  scopes and resources are unchanged;
- an MCP client may apply or reject any submitted change set of the
  organisation, under the same rule as the Metrics tab;
- the change set records whether it was reviewed through the web or through
  MCP, and for MCP the reviewing client.

A human still decides each apply and reject: in the Metrics tab, or by
approving the client's tool call. See
[MCP Change-Set Review](#mcp-change-set-review).

Amendment (2026-11-03, `tasks/TASK-074-single-mcp-connector.md`): after the
production enablement the developer asked for **one connector that handles
both read and write, authorized once**. The two services were separate OAuth
resources, so a user added two connectors, went through consent twice and
held two grants, and Claude Code registered two OAuth clients. It must stay
possible to limit a role, for example consultants, to read-only later. This
replaces the decision that MCP is split into a read service and a write
service. The developer decided that:

- one MCP service `/api/mcp` serves every tool and prompt, with one OAuth
  resource and one grant covering read and write;
- **read-only is decided by role only**. The consent page offers no choice; a
  client may still ask for `scope=schatten.read` and then gets a read-only
  grant;
- the scopes `schatten.read` and `schatten.write` stay the permission
  vocabulary, and `ROLE_SCOPES` stays the one place that limits a role;
- every tool and prompt checks its own scope against the caller's effective
  scopes, so a role limited later sees only the read tools on the same URL;
- the switch is clean: `/api/mcp/read` and `/api/mcp/write` are removed,
  migration 020 deletes their grants, and each user replaces the two
  connectors with the new one once.

See [One MCP Service In The Existing FastAPI App](#one-mcp-service-in-the-existing-fastapi-app)
and [Per-Tool Scope Check](#per-tool-scope-check).

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

This ADR is an accepted design. The implementation is delivered by TASK-069B
through TASK-069P and, for the 2026-11-03 amendment, TASK-074; TASK-069B (the
domain service transaction cores, which change no REST behaviour), TASK-069C (the deterministic timeseries generator,
which adds no route), TASK-069D (the MCP OAuth schema, which adds no route),
TASK-069E (discovery, registration, authorization request and consent API,
registered only with `MCP_ENABLED=true`), TASK-069F (token, refresh and revoke
endpoints, registered only with `MCP_ENABLED=true`, `verify_access_token` and
the always-registered connections API) and TASK-069G (the FastMCP read and
write endpoints, which TASK-074 merged into one, registered only with
`MCP_ENABLED=true`, bearer
authentication, resource protection and the first read tools), TASK-069H
(the remaining read tools and the generator preview), TASK-069I (the
change-set schema and engine, which add no tool or route) and TASK-069J (the
change-set staging write tools and the change-set read tools; no tool applies
a change set), TASK-069K (the always-registered cookie-session review API
that applies or rejects a submitted change set), TASK-069L (the SPA consent
page, the connections list component and the admin per-user revocation
action), TASK-069M (the Metrics tab AI panel), TASK-069N (skills, plugin and
MCP prompts) and TASK-069O (the MCP change-set review tools behind
`MCP_CHANGE_SET_REVIEW_ENABLED`, the review channel of migration 019 and the
2026-10-29 amendment) are implemented. TASK-069P verified the feature end to end locally
(`docs/qa/AI-MCP-QA-CHECKLIST.md`), trimmed the default redirect URI
allowlist and documented its operation (`docs/PRODUCTION-RUNBOOK.md` section
14). The feature stayed disabled (`MCP_ENABLED=false`) until TASK-069P's
separately approved production enablement, which enabled it and its
change-set review on 2026-11-03, with the two services of that time.
TASK-074 implements the 2026-11-03 amendment: the one MCP service
`/api/mcp`, the per-tool scope check, the single OAuth resource, migration 020,
the plugin, the UI and the documentation. Its production deployment is a
separate, approved release (`deploy-release --mcp-approval`) and not part of
TASK-074.

| Task | Delivers |
| --- | --- |
| TASK-069B | Flush-only `*_in_transaction` cores for the domain services change sets need (implemented) |
| TASK-069C | Deterministic timeseries generator (implemented) |
| TASK-069D | MCP OAuth schema (`mcp_oauth_*`: clients, authorization requests, grants, tokens) (implemented) |
| TASK-069E | OAuth discovery, client registration, authorization request, consent API and Caddy routing (implemented) |
| TASK-069F | Token, refresh, revoke, `verify_access_token` and connections API (implemented) |
| TASK-069G | FastMCP foundation, bearer authentication, resource protection, first read tools (implemented) |
| TASK-069H | Remaining read tools and generator preview (implemented) |
| TASK-069I | Change-set schema and engine (dry-run and atomic apply) (implemented) |
| TASK-069J | Write MCP tools for staging change sets (implemented) |
| TASK-069K | Cookie-session change-set review API (apply, reject) (implemented) |
| TASK-069L | SPA consent page and connections list (implemented) |
| TASK-069M | Metrics tab AI panel and change-set review UI (implemented) |
| TASK-069N | Skills, Claude Code plugin bundle, MCP prompts, skill zips (implemented) |
| TASK-069O | MCP change-set review: `get_change_set_review`, `apply_change_set`, `reject_change_set`, the switch and the review channel (amendment of 2026-10-29, implemented) |
| TASK-069P | End-to-end QA and runbook (implemented); approved production enablement (2026-11-03) (was TASK-069O until 2026-10-29) |
| TASK-074 | One MCP service `/api/mcp` with per-tool scope checks, one OAuth resource and grant, migration 020, plugin 0.3.0, UI and docs (amendment of 2026-11-03, implemented); its production deployment needs a separate approval |

## Provider Neutrality And No In-App LLM

Schatten exposes MCP and OAuth 2.1 only. The user brings any MCP-capable
client and AI subscription. Schatten has no in-app chat, never calls an LLM,
never stores an LLM API key and has no vendor SDK. Claude clients are the
first verified clients. TASK-069P verified Claude Code locally; a
non-Claude MCP client is still to be verified (the developer deferred it on
2026-10-30; OpenCode needs its own loopback allowlist entry).

## One MCP Service In The Existing FastAPI App

The 2026-11-03 amendment replaced the original design, in which two FastMCP
servers ran at `/api/mcp/read` (scope `schatten.read`) and `/api/mcp/write`
(scope `schatten.write`), each its own OAuth resource with its own grant. Now
one FastMCP server named "Schatten" runs inside the existing FastAPI process and
backend image at `/api/mcp`, using the MCP Streamable HTTP transport. It
serves every tool and prompt, and each component requires its own scope
([Per-Tool Scope Check](#per-tool-scope-check)):

| Components | Required scope | Purpose |
| --- | --- | --- |
| 13 read tools and the MCP prompts `model_building` and `timeseries_generation` | `schatten.read` | Inspect organisations, scenarios, org states, type catalog, graph, timeseries, events, change sets and change-set reviews; preview generated series; MCP prompts |
| 6 write tools; 8 with `MCP_CHANGE_SET_REVIEW_ENABLED=true` | `schatten.write` | Create, edit, validate, submit and discard **draft change sets**; with the switch also apply or reject **submitted change sets** ([MCP Change-Set Review](#mcp-change-set-review)) |

- The server runs `stateless_http=True` with `json_response=True`. No MCP
  session state, server-sent event stream or long-running request is kept.
- `build_mcp_server(runtime, settings)` (`backend/app/mcp/server.py`) creates
  the one `FastMCP("Schatten", ...)` with one combined instruction text and
  registers the read tool set (`register_read_tools`, `read_server.py`) and
  the write tool set (`register_write_tools`, `write_server.py`). The
  instructions have one variant with and one without
  `MCP_CHANGE_SET_REVIEW_ENABLED`, name the tools without naming a server and
  say that the change-set tools are listed only when both the user's role and
  the access granted to the connection allow proposing changes.
- The server is built inside `create_app()` and registered as one exact route
  `/api/mcp` (GET, POST, DELETE) wrapped in bearer authentication. `app.mount`
  is not used because it causes a trailing-slash redirect. The lifespan runs
  its session manager. `/api/mcp/read`, `/api/mcp/write`, `/api/mcp/` and
  their protected-resource metadata documents answer 404; there is no
  redirect from the old URLs.
- With `MCP_ENABLED=false` (the default) the MCP endpoint, the public OAuth
  endpoints, the consent API and the skill zip download are not registered and
  return 404. The cookie-session connections API and change-set review API stay
  registered, so users and administrators can still revoke grants and humans
  can still review, apply or reject already staged change sets while MCP is
  disabled (see [Incident Procedure](#incident-procedure)). The session
  response gains a `features.mcp` flag, and the SPA hides the consent page,
  connect instructions and skill links when it is false; the connections list
  and the Metrics AI panel stay visible only when they have rows to show.
  `MCP_CHANGE_SET_REVIEW_ENABLED` has no effect while `MCP_ENABLED` is false;
  the session's `features.mcpChangeSetReview` is true only when both are on.
- Read tools are annotated `readOnlyHint`, `idempotentHint` and
  `openWorldHint=False`. Write tools are annotated `openWorldHint=False`, with
  `destructiveHint` on removal, discard, apply and reject.
- **Only `apply_change_set` changes business data through MCP**, only through
  the change-set engine's apply, and only while
  `MCP_CHANGE_SET_REVIEW_ENABLED` is on. No other MCP tool, prompt or resource
  can change business data. The staging tools change only draft change-set
  rows owned by the AI domain; `reject_change_set` changes only the review
  state of a submitted change set.
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
TASK-069G verified `fastmcp` 4.1.4 (with its `mcp` 2.3.0) against the locked
FastAPI 0.138.1 and Starlette 1.3.1, which stay unchanged, and added
`fastmcp>=4.1.4,<5`; the fallback was not needed.

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
| `GET /.well-known/oauth-protected-resource/api/mcp` | RFC 9728 | Resource `<origin>/api/mcp`, authorization server `PUBLIC_ORIGIN`, scopes `schatten.read`, `schatten.write` (the 2026-11-03 amendment replaced the two documents `.../api/mcp/read` and `.../api/mcp/write`, each with its server's one scope; they answer 404) |
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
    `Jonatan's client` or `R&D tool` are therefore rejected. TASK-069P
    verified that Claude Code's names for the two servers of that time
    (`Claude Code (schatten-read)` and `Claude Code (schatten-write)`) fit,
    and the claude.ai and Claude Desktop connectors' name `Claude` passed in
    production (2026-11-03 and 2026-11-04);
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
    8252 section 8.3 prefers IP literals. TASK-069P found that Claude Code
    registers `http://localhost:{port}/callback` and that no verified client
    uses an IP-literal entry, so the default allowlist keeps only the two
    exact entries and `http://localhost:{port}/callback`; IP-literal entries
    remain configurable.
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
- **Audience binding** (replaced by the 2026-11-03 amendment; until then each
  of the two resources had exactly one scope and a client that used both
  services held two grants). `resource` is required on both the authorization
  request and the token request, and it must equal the one canonical resource
  URI `<PUBLIC_ORIGIN>/api/mcp` exactly, otherwise `invalid_target`. There is
  no trailing slash, query or fragment, and no other normalisation is applied.
  A grant and all its tokens are bound to that resource. Token verification
  rejects a token whose grant has another resource, for example another
  origin's `/api/mcp`, with `401 invalid_token`.
- **Requested scopes.** `scope` is optional and may appear at most once. It is
  a space-separated set of known scopes that includes `schatten.read`, in any
  order and without duplicates, and is normalised to `schatten.read` or
  `schatten.read schatten.write`. An omitted `scope` means both scopes.
  Anything else, including write-only, unknown or duplicated scopes and a
  repeated `scope` parameter, is rejected with `invalid_scope`.
- **Consent narrows to the role.** The consent API returns the requested
  scopes intersected with the User's role scopes (`ROLE_SCOPES`), so the
  consent page shows exactly what will be granted, and approval stores that
  narrowed set on the pending request. If it lacks `schatten.read`, approval
  redirects with `access_denied`; no current role reaches this. For a role
  that `ROLE_SCOPES` maps to no scope the narrowed set is empty, and the
  consent page says that the role cannot connect AI clients and offers only
  Deny (AI review finding F-004 of TASK-074). The page offers no read-only
  choice: a role, or a client that asks only for `schatten.read`, makes a
  grant read-only.
- **Granted and reported scopes.** The code exchange creates or reuses a grant
  with the pending request's scopes. The token response's `scope` is the
  effective set, the grant's scopes intersected with the current role's
  scopes, in both the exchange and refresh (RFC 6749 section 5.1 allows it to
  differ from the request). The connections API reports the same effective
  set.
- **Refresh keeps the grant's scopes.** The refresh `resource` must equal the
  grant's (`invalid_target`). A `scope` that is sent must name only known
  scopes (`invalid_scope`). The new token keeps the grant's scopes, and the
  response says which. Tokens are bound to the grant and carry no scope of
  their own, so narrowing per token is not supported. This avoids a reconnect
  loop when a client re-sends both scopes after its role was narrowed.
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
- A User's repeated authorization of the same client and resource reuses that
  User's existing grant only when it is active, that is not revoked and not
  past its `expires_time`. The reused grant takes the scopes of the newest
  consent (2026-11-03 amendment; before it, the resource fixed the single
  scope). Reuse does not extend the grant's absolute lifetime, and it revokes
  all of the grant's earlier access and refresh tokens before issuing the new
  pair. A stale refresh chain then fails as revoked and cannot trigger reuse
  detection against the fresh authorization. Without an active grant, a new
  grant is created.
- Accepted consequence: when one client registration serves several
  concurrent sessions of the same User and resource, re-authorizing in one
  session signs the others out, because the reused grant's earlier tokens are
  revoked. TASK-069P verified the effect locally and records it in the
  runbook. Whether the claude.ai and Claude Desktop connectors share one
  registration across Users is still to be recorded.
- **Grant deletion and references.** Lazy cleanup deletes revoked or expired
  grants, as described in
  [resource protection](#no-background-execution-and-resource-protection).
  Migration 020 (2026-11-03 amendment) deleted the grants and tokens on the
  removed resources `/api/mcp/read` and `/api/mcp/write` once, together with
  every pending authorization request, with the same effect on the references
  below. The references to a grant behave as follows:
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
MCP client -> POST /api/mcp                       401 + resource_metadata
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
  client, and the access that will be granted (the requested scopes narrowed
  to the User's role) in plain words. For a redirect URI that
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

`McpBearerAuth` wraps the MCP endpoint and on every request:

1. reads `Authorization: Bearer`, hashes the token and loads it as an
   unexpired, unrevoked access token;
2. checks its grant is not revoked, not past its `expires_time`, and bound to
   the canonical resource `<PUBLIC_ORIGIN>/api/mcp`; a token for another
   resource gets `401 invalid_token`;
3. loads the grant's User and rejects a soft-deleted User; this **re-reads the
   current database role** on every call;
4. computes effective scopes as
   `grant.scopes ∩ allowed_scopes_for_role(user.role)`; and
5. requires the minimum scope `schatten.read`. Until the 2026-11-03 amendment
   each endpoint required its own one scope.

Failures return `401` with
`WWW-Authenticate: Bearer resource_metadata="<origin>/.well-known/oauth-protected-resource/api/mcp"`
(with `error="invalid_token"` when a token was presented), or `403` with
`WWW-Authenticate: Bearer error="insufficient_scope", scope="schatten.read", resource_metadata="..."`. The principal (User, role, grant, client name,
effective scopes) is placed in a context variable; tools use it as the actor.
`last_used_time` is written at most every five minutes.

### Per-Tool Scope Check

Added by the 2026-11-03 amendment and implemented by TASK-074. The bearer
check admits every caller with `schatten.read`; each component then checks its
own scope:

- every read tool and both MCP prompts are registered with
  `auth=requires_scope(READ_SCOPE)` (`schatten.read`), and every write tool,
  including `apply_change_set` and `reject_change_set`, with
  `auth=requires_scope(WRITE_SCOPE)` (`schatten.write`). `requires_scope(scope)`
  (`backend/app/mcp/auth.py`) reads `current_principal` and allows the
  component when the scope is in the principal's effective scopes;
- `fastmcp` 4.1.4 hides a component whose check fails: it is not listed, and
  a call to it gets "Unknown tool". A check that raises is logged and treated
  as a denial, so the check fails closed;
- the token is verified and the effective scopes are recomputed on every
  request, so a role change shows or hides the write tools on the next
  request without a token, URL or client change.

Both current roles, `admin` and `consultant`, are allowed both scopes. This
matches ADR-004, where both roles use every business API in every
organisation. The role mapping `ROLE_SCOPES`
(`backend/app/api/v1/mcp_oauth/token_service.py`) is the one place that limits
a role: changing a role to `{READ_SCOPE}` is a one-line change with no token
format, URL or client change, and that role then sees only the read tools and
prompts on the same URL. No role is limited today.

The MCP endpoint accepts only bearer tokens and never the browser session cookie;
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
   so no token works and no new grant can be issued. When only applies or
   rejects through MCP are suspicious, setting
   `MCP_CHANGE_SET_REVIEW_ENABLED=false` instead removes those tools on the
   next request and keeps staging.
2. While MCP is disabled, an `admin` revokes the grants of every affected User
   through the per-user revocation endpoint (or soft-deletes the User), and
   Users may revoke their own grants. The connections and review APIs stay
   registered for this.
3. Humans reject any suspicious staged change sets in the Metrics tab. The
   review list shows which change sets were applied or rejected through MCP
   and by which client.
4. MCP is re-enabled only with the separate human approval that TASK-069P
   defines for enablement.

TASK-069P documents this procedure in the runbook.

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
- **Human review is required.** A human decides each apply and reject, in
  one of two ways:
  - in the Metrics tab, through cookie-session endpoints with CSRF and exact
    Origin (`/api/v1/organisations/{organisation_key}/ai/change-sets/...`);
  - with `MCP_CHANGE_SET_REVIEW_ENABLED=true`, by approving the MCP client's
    call of `apply_change_set` or `reject_change_set` (see
    [MCP Change-Set Review](#mcp-change-set-review)).

  Both roles may review, including the creator: the AI acts on the creator's
  behalf and the human decision is the gate between AI output and business
  data. Both ways use the same engine, the same `reviewFingerprint` check and
  the same reviewer audit.
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

  The reviewer is the actor for the created business rows. A concurrent apply,
  through either channel, applies once; others get 409.
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

## MCP Change-Set Review

Added by the 2026-10-29 amendment and implemented by TASK-069O. It lets an MCP
client do what the Metrics tab review does, on behalf of its User. TASK-069O
placed the apply and reject tools on the write server and the review read on
the read server; since the 2026-11-03 amendment they are a write tool and a
read tool of the one MCP service, with the same behaviour.

- **Switch.** `MCP_CHANGE_SET_REVIEW_ENABLED` (default `false`) registers
  `apply_change_set` and `reject_change_set` as write tools when the MCP
  server is built. With it off the server has exactly the six staging write
  tools, and its instructions and the staging tools' descriptions say that a
  person applies change sets in Schatten; with it on they also name the
  in-chat review. Production enablement of the switch belongs to TASK-069P.
- **Review read.** The read tool `get_change_set_review(change_set_key)` is
  always registered. It returns what the Metrics tab review detail shows:
  the change set, each operation's `replaces_existing` flag and replacement
  summary recomputed against current data, a summary of frozen values (never
  the values) and the `review_fingerprint`. It uses the same single-statement
  load, `compute_replacements` and `statement_timeout` as the review API.
- **Apply.** `apply_change_set(change_set_key, review_fingerprint)` runs the
  engine's apply unchanged (lock, status, fingerprint, re-validate, execute,
  commit). The fingerprint must come from `get_change_set_review`, so the AI
  applies exactly the replacements it showed the user; `review_stale` means
  read the review again and confirm with the user again. The engine's error
  codes become tool errors with the same codes and meanings as the review
  API's responses.
- **Reject.** `reject_change_set(change_set_key, note=None)` runs the engine's
  reject with the review API's note rules.
- **Who.** Any submitted change set of a non-deleted organisation, whoever
  created it, under the same rule as the Metrics tab: both roles, the creator
  included. The grant's User is the reviewer and the actor of the created
  business rows. Both current roles keep both scopes; no scope is added.
- **Human decision.** Both tools are annotated `destructiveHint=True`,
  `idempotentHint=False` and `openWorldHint=False`, so MCP clients ask the
  human before each call unless the human has chosen to always allow it. The
  server's instructions and the skills tell the AI to show the review
  (title, operations and every replaced value) and to call apply or reject
  only on the user's explicit instruction in the conversation, never because
  stored business text asks for it.
- **Audit.** Migration 019 adds `reviewed_via` (`web` or `mcp`),
  `review_client_id` and `review_client_name` to `ai_change_sets`. They are
  set together with `reviewed_by` and `reviewed_time` on apply, reject and
  the conditional `failed` update. For `mcp` the reviewing grant's
  `client_id` is copied as a plain value and its self-declared client name is
  stored, as for the staging client. Change sets reviewed before migration 019
  are backfilled to `web`. The review API, the MCP change-set summaries and
  the Metrics AI panel show the channel and the client name.
- **Consent wording.** When `features.mcpChangeSetReview` is true, the consent
  page, the connect instructions and the connections list describe write
  access as staging, applying and rejecting change sets. Turning the switch on
  gives existing write grants the tools on their next request although their
  consent said "proposals only". This is accepted; the runbook says to enable
  the switch before or together with production enablement, or to tell users.
- **Deferred: server-side confirmation.** MCP elicitation (in `mcp` 2.3.0 the
  stateless `InputRequiredResult` flow) would let Schatten itself ask the
  human to confirm, with a text the AI cannot change. It is not used, because
  support in the real clients is unknown and requiring it could make the tools
  unusable. TASK-069P recorded that Claude Code 2.1.309 and 2.1.314 ship
  elicitation support. Support in Claude Desktop and claude.ai is not
  observable from Schatten, which logs no client capabilities, and is still
  to be recorded for a later decision.

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
- MCP prompts (`model_building`, `timeseries_generation`) of the MCP
  service, which any MCP client can use (until the 2026-11-03 amendment, of
  the read server).

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
  - `mcp_rate_limiter` for `/api/mcp`, one bucket per grant that covers reads
    and writes together. Until the 2026-11-03 amendment a user held one grant
    per server, so reads and writes had separate buckets. The default of
    `MCP_RATE_LIMIT_PER_MINUTE` (120) is kept.

  TASK-069P verified the defaults with local clients, and the claude.ai and
  Claude Desktop connectors connected to the read server in production
  (2026-11-03 and 2026-11-04) without a reported problem; the fit with real multi-user
  vendor-cloud traffic is still to be observed. Both limiters assume one backend replica, as in ADR-004.
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
      immediate operator remedy, documented in the TASK-069P runbook, is to
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
  responses that report truncation. `list_timeseries` reads no values by
  default and `get_timeserie` reads one page of values. Accepted trade-off:
  `list_timeseries` with `include_values=true` still reads every value of the
  scenario before cutting the response to 2,000 values; and
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
- a role, not the user, limits access to read (2026-11-03 amendment): a role
  limited in `ROLE_SCOPES` gets read-only grants and sees only the read tools
  and prompts, and a client may itself ask only for `schatten.read`. Both
  current roles have read and write. Until the amendment a user could grant
  read without write by connecting only the read service;
- a user can revoke any grant at any time, and the connections list shows
  each grant's effective scopes;
- operators can disable the feature with `MCP_ENABLED=false`; and
- users are expected to use AI subscriptions their organisation approves.

Business text returned by read tools is untrusted input to the AI and may try
to steer it (prompt injection). With `MCP_CHANGE_SET_REVIEW_ENABLED=false` no
MCP tool can apply changes, so the worst outcome is a staged change set that a
human must still review. With it on, a steered AI can also call
`apply_change_set` or `reject_change_set` on any submitted change set of the
organisation, including another User's. The call still needs the human's
approval in the client, the current review fingerprint and a change set that
passes re-validation, and the review channel and client are recorded. A human
who approves the call without reading it applies the change set; this is an
accepted risk of the amendment.
Tokens, codes, request ids and tool arguments are never logged; see
[Pending Request Id Handling](#pending-request-id-handling) for the Caddy and
backend log filters.

## Routing And Deployment

No Compose service, container, public port, domain or Entra change is added.

- Caddy remains the only public ingress. Its API matcher becomes
  `@api path /api /api/* /.well-known/oauth-authorization-server* /.well-known/oauth-protected-resource*`
  in both `frontend/Caddyfile` and `local/Caddyfile`. This extends ADR-013's
  `/api` and `/api/*` routing without changing anything else in it.
- Production MCP URL: `https://schatten.lupaus.eu/api/mcp` (until the
  2026-11-03 amendment `https://schatten.lupaus.eu/api/mcp/read` and
  `https://schatten.lupaus.eu/api/mcp/write`). The amendment changes no Caddy
  route: `/api/*` and `/.well-known/oauth-protected-resource*` are prefix
  routes.
- Production reads `MCP_ENABLED`, `MCP_CHANGE_SET_REVIEW_ENABLED` and
  `MCP_OAUTH_MAX_CLIENTS` from the protected env file, defaulting to off and
  10,000 (developer decision of 2026-10-30, TASK-069P). An operator applies
  them by deploying the current release again, so the incident procedure and
  the client cap remedy need no new release once the current release includes
  TASK-069P; releases built before it, such as `v0.1.0`, pin MCP off, so the
  first enablement deploys a newly built release. `deploy-release` refuses to turn
  MCP or its change-set review on without a separate `--mcp-approval`
  reference and records the values and that reference; turning them off needs
  only the release approval. All other MCP settings stay fixed in Compose.
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
- [reviewInChatFlow](../diagrams/generated/likec4-reviewInChatFlow.png)
  (dynamic, the 2026-10-29 amendment)

Since the 2026-11-03 amendment the backend has one `mcpService` component in
place of the read and write service components.

---

# Options Considered

- **In-app LLM chat calling a vendor API:** rejected. It needs stored API keys,
  vendor coupling and billing, and the users already have AI subscriptions and
  MCP-capable clients.
- **One MCP service with mixed scopes:** rejected on 2026-10-21, because
  separate read and write services let users connect read-only clients and
  make the write surface explicit. **Accepted by the 2026-11-03 amendment**:
  one connector and one consent per user instead of two connectors, two
  consents and two grants. The per-tool scope check keeps the write surface
  explicit, and `ROLE_SCOPES` can still limit a role to read on the same URL.
- **Keep the old URLs for a transition (amendment of 2026-11-03):** not
  chosen. The developer chose a clean switch: `/api/mcp/read` and
  `/api/mcp/write` answer 404 without a redirect, migration 020 deletes their
  grants as lazy cleanup would, and each user replaces the two connectors with
  the new one once.
- **A read-only choice on the consent page (amendment of 2026-11-03):** not
  chosen. Read-only is decided by the role; a client may still ask only for
  `schatten.read`.
- **An MCP apply tool, with or without confirmation:** rejected on
  2026-10-21, because AI clients may act on untrusted text. **Accepted by the
  2026-10-29 amendment** with the constraints in
  [MCP Change-Set Review](#mcp-change-set-review): an operator switch, the
  client's tool approval, the review fingerprint and the review audit.
- **A separate MCP review server and scope (amendment):** not chosen. It would
  let each user opt in per connection, but needs a third OAuth resource, its
  discovery, consent and plugin configuration, and a third connector per user.
  The operator switch and per-tool client permissions cover the need.
- **MCP review limited to the caller's own change sets (amendment):** not
  chosen. The developer kept the Metrics tab rule that any reviewer may
  decide any submitted change set.
- **Server-side confirmation through MCP elicitation (amendment):** deferred
  until real client support is known (TASK-069P).
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
- Business data changes only through a reviewed, atomic, audited apply that a
  human decides, in the Metrics tab or by approving the MCP client's call, and
  that uses the same domain services as REST.
- With the switch on, users can review, apply and reject in the same chat
  that staged the change set.
- Since the 2026-11-03 amendment a user adds one MCP URL and consents once
  for read and write, and a role can later be limited to read without a
  token, URL or client change.
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
- With `MCP_CHANGE_SET_REVIEW_ENABLED=true` the human gate for an MCP apply is
  the client's tool approval, which a user can set to always allow. A
  prompt-injected AI and a human who approves without reading can apply a
  submitted change set, including another User's. The fingerprint,
  re-validation, audit channel and switch are the mitigations.
- Turning the switch on widens existing write grants without new consent (see
  [MCP Change-Set Review](#mcp-change-set-review)).
- The 2026-11-03 amendment is a clean switch: after its release every user
  removes the two old connectors and adds the new one, and users who uploaded
  the skill zips download and replace them. Users can no longer choose
  read-only access themselves, except through a client that asks only for
  `schatten.read`, and one per-grant rate-limit bucket now covers reads and
  writes together.
- One new backend dependency (`fastmcp` or the fallback `mcp`).
- A second diagram tool (LikeC4) is used for this feature.

---

# Implementation Rules

- Follow the task order in [Scope And Status](#scope-and-status). Each task
  implements only its own scope; dependencies other than those approved here
  need separate approval.
- Only `apply_change_set` may apply a change set through MCP, only through
  the engine's `apply_change_set` with the review fingerprint, and only while
  `MCP_CHANGE_SET_REVIEW_ENABLED` is on. Never add any other MCP tool, prompt
  or resource that applies or rejects a change set or writes business tables.
- Keep `MCP_CHANGE_SET_REVIEW_ENABLED=false` by default. Every apply and
  reject records its review channel.
- Never store plaintext tokens, codes or request ids in the `mcp_oauth_*`
  tables, and never log them or tool arguments.
- Never accept the session cookie on `/api/mcp` or an MCP token on
  `/api/v1`.
- Register every MCP tool and prompt with its scope check: read tools and
  prompts `requires_scope(READ_SCOPE)`, write tools
  `requires_scope(WRITE_SCOPE)`. Limit a role only through `ROLE_SCOPES`.
- Change sets use other domains' `*_in_transaction` cores only.
- Keep `MCP_ENABLED=false` by default. Production enablement needs separate
  human approval under TASK-069P, which `deploy-release --mcp-approval`
  enforces.
- If the implementation differs from the LikeC4 model, update the model and
  its PNG exports in the same task.

---

# Follow-Up

- TASK-069B through TASK-069P implement this design and its 2026-10-29
  amendment; TASK-074 implements the 2026-11-03 amendment, whose production
  deployment needs a separate approval.
- Client ID Metadata Documents, more operation types (for example edge and
  event patches) and further roles are separate future decisions.
- A server-side confirmation of MCP apply and reject through elicitation is a
  separate future decision, after TASK-069P has recorded client support.
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
- `tasks/TASK-069O-mcp-change-set-review.md`
- `tasks/TASK-074-single-mcp-connector.md`
