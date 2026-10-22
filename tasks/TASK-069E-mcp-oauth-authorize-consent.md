# TASK-069E MCP OAuth Discovery, Registration, Authorization And Consent API

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Schatten
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

MCP clients must authenticate as existing Schatten Users through the existing
Entra login. Schatten acts as the OAuth 2.1 authorization server, and the
Entra registration does not change.

## Goal

Implement OAuth discovery, Dynamic Client Registration and the authorization
request. Implement the cookie-authenticated consent API that turns an approved
request into a one-time authorization code. Route the new paths through Caddy.

## Requirements

- Public endpoints. These are outside `/api/v1` and return RFC 6749 JSON errors.
  - Rate limiting uses a new, separate `oauth_rate_limiter` (another
    `FixedWindowRateLimiter` instance with its own entry bound, never the
    login `auth_rate_limiter`). It has configurable per-endpoint buckets keyed
    by client IP:
    - `register`, `token` and `revoke` (the last two used by TASK-069F) get
      higher limits, because the vendor's connector broker calls them from
      shared egress addresses for every vendor-cloud user;
    - `authorize`, which comes from the user's browser, keeps a low limit.
  - `GET /.well-known/oauth-authorization-server`:
    - the issuer is `PUBLIC_ORIGIN`;
    - supported grant types are `authorization_code` and `refresh_token`;
    - the only code challenge method is `S256`;
    - scopes are `schatten.read` and `schatten.write`;
    - the token endpoint auth method is `none`;
    - `authorization_response_iss_parameter_supported` is `true`.
  - `GET /.well-known/oauth-protected-resource/api/mcp/{read,write}`. The
    resource is the canonical `<PUBLIC_ORIGIN>/api/mcp/<server>`, with no
    trailing slash, and the metadata lists the server's single scope.
  - `POST /api/oauth/register`:
    - Public clients only. A `token_endpoint_auth_method` other than `none`
      is rejected with `invalid_client_metadata`.
    - Metadata bounds, rejected with `invalid_client_metadata`:
      - `client_name` is required (a missing name is rejected) and checked
        against ADR-015's ASCII allowlist:
        - trim leading and trailing ASCII spaces (U+0020) only;
        - the trimmed name must be 1 to 100 characters long;
        - every character must be `A-Z`, `a-z`, `0-9`, a space, or one of
          `. - _ ( ) : / +`;
        - it must contain at least one ASCII letter or digit.

        Any other character anywhere in the name is rejected. The trimmed
        name is stored, shown and logged. No Unicode tables or dependency are
        needed;
      - at most 10 redirect URIs, each at most 2,048 characters.
      - Other metadata is ignored. The consent page and logs always treat
        `client_name` as a self-declared label.
    - Each redirect URI is checked against `MCP_OAUTH_REDIRECT_URIS` by
      ADR-015's structured matching, never by prefix or glob:
      - exact entries (the claude.ai and claude.com callbacks) match by whole
        string equality;
      - loopback entries carry a literal port placeholder, such as
        `http://127.0.0.1:{port}/callback`, `http://[::1]:{port}/callback` or
        `http://localhost:{port}/callback`. They match a parsed URI only when
        the scheme `http`, the host and the path equal the entry's, the port
        is an explicit number from 1 to 65535, and there is no userinfo, query
        or fragment.
      - Other URIs are rejected with `invalid_redirect_uri`.
    - Registration first runs the lazy client cleanup, then checks a
      configurable cap on non-deleted clients (default 10,000). Beyond the
      cap, `register` answers HTTP 503 with `temporarily_unavailable` and
      writes a warning log entry.
    - The lazy client cleanup locks candidate clients with
      `FOR UPDATE SKIP LOCKED`, so
      it never waits on a client that an authorize request holds:
      - it soft-deletes (`deleted_time`) clients whose `last_used_time` (or
        creation time) is more than 30 days old and that have no active
        grant;
      - it then hard-deletes soft-deleted clients that no authorization
        request or grant references.
      - Soft-deleted clients cannot authorize.
  - `GET /api/oauth/authorize`:
    - checks the client by locking its row (`SELECT ... FOR NO KEY UPDATE`,
      which does not block grant inserts for the same client) and
      requiring that it is not soft-deleted, in the same transaction that
      later stores the pending request. Cleanup therefore cannot soft-delete
      or hard-delete it before authorize commits;
    - checks `response_type=code` and PKCE `S256`;
    - checks the redirect URI against the client's registered URIs by exact
      string equality; for a loopback URI only the port may differ;
    - requires `resource`, equal to one canonical MCP resource URI exactly;
    - requires `scope` to equal that resource's single scope, or to be
      omitted, in which case it defaults to that scope. Any other scope set
      is rejected with `invalid_scope`.
    - caps live pending requests per client (default 20) and in total
      (default 1,000), answering `temporarily_unavailable` beyond the cap;
    - stores a hashed pending request that expires after 10 minutes;
    - only then, in the same transaction and on the locked client row,
      updates the client's `last_used_time`. A client in the middle of a valid
      consent flow is never cleaned up, failing authorize calls never keep a
      client alive, and the pending-request insert never meets a deleted
      client;
    - redirects with 303 to the SPA route `/ai/authorize?request=<id>`.
    - Invalid client or redirect URI errors are never redirected.
    - Every other error is redirected to the validated redirect URI by the
      same server-side builder as approve and deny. The redirect carries
      `error`, `state` (only when the client sent one) and `iss`, and nothing
      else.
- Cookie-session consent API. The request id never appears in a URL path.
  The authorization sweep covers these routes only when it builds the app
  with `MCP_ENABLED=true` (see the acceptance criteria).
  - `GET /api/v1/ai/oauth/consent?request=<id>` returns:
    - the client name, flagged as self-declared;
    - `redirectIsLoopback`, a boolean the server sets from the allowlist entry
      the redirect URI matched (exact or loopback);
    - `redirectHost`, always returned: the redirect URI's host in URL form,
      with IPv6 in brackets (for example `[::1]`). The page shows it only
      when `redirectIsLoopback` is false;
    - the requested scope and resource;
    - the expiry.

    It uses `BusinessSessionDependency`.
  - `POST /api/v1/ai/oauth/consent/approve` and `.../deny` take
    `{"request": "<id>"}` as a JSON body and use `UnsafeRequestDependency`.
    - The server builds the redirect URL; the SPA never composes it.
    - Approve records the user and returns `{redirectUrl}`. That is the
      registered redirect URI (with the request's loopback port) plus
      `code`, `state` (omitted when the client sent none) and `iss`. The code
      expires after 60 seconds and is stored hashed.
    - Deny returns an `access_denied` redirect URL built the same way.
    - A request can be decided only once.
  - All consent responses are `Cache-Control: no-store`.
- Settings in `backend/app/core/config.py`:
  - `MCP_ENABLED`, a feature flag that is off by default;
  - `MCP_OAUTH_REDIRECT_URIS`;
  - the authorization request and code lifetimes;
  - the per-endpoint rate limits, the pending request caps and the client
    cap.
  - Add them to the example environment and Compose files without secrets.
- `MCP_ENABLED` exposure: `SessionResponse` gains `features: {mcp: bool}` so
  the SPA can hide MCP-only UI. With `MCP_ENABLED=false` the endpoints of this
  task (discovery, register, authorize, consent) are not registered and
  return 404.
- Extend the `authentication_boundary` `Cache-Control: no-store` handling to
  `/api/oauth`, `/.well-known/oauth-` and `/api/v1/ai/oauth`.
- Request-id and secret log redaction, as in ADR-015 "Pending Request Id
  Handling":
  - Caddy, in both `frontend/Caddyfile` and `local/Caddyfile`:
    - change the matcher to
      `@api path /api /api/* /.well-known/oauth-authorization-server* /.well-known/oauth-protected-resource*`;
    - in the existing `log` `format filter`, add `request` and `return_to` to
      the `request>uri query` replacements;
    - replace `resp_headers>Location`;
    - replace `request>headers>Authorization` explicitly.
  - Backend: add `request` and `return_to` to the sensitive-query access-log
    filter in `backend/app/api/v1/auth/logging.py`.
  - No application log line contains a request id, code, token or redirect
    URL with a code.

## Acceptance Criteria

- [ ] Tests cover:
      - the metadata documents, including `iss` support and the canonical
        resources;
      - registration:
        - allowlist acceptance for exact and loopback entries;
        - rejection of userinfo (`@`), fragment, query, missing port, `https`
          loopback, percent-encoded or trailing-dot hosts, and wrong paths;
        - rejection of a non-`none` auth method;
      - authorize validation:
        - PKCE missing or `plain`;
        - wrong redirect URI, and a loopback port change that is accepted;
        - unknown scope, both scopes, and a scope that does not match the
          resource;
        - missing or non-canonical `resource`;
        - the pending request cap;
      - approve and deny, an expired request, and a request decided twice;
      - the consent API's `redirectIsLoopback` flag and the always-returned
        `redirectHost`: the flag is true for `127.0.0.1`, `[::1]` and
        `localhost` redirects (with `redirectHost` `127.0.0.1`, `[::1]` and
        `localhost`) and false for an exact vendor callback (with its host);
      - the server-built redirect URL, with `code`, `state` and `iss`, and
        with `state` omitted when absent;
      - redirected authorize errors (`invalid_scope`, missing PKCE,
        `invalid_target`, `temporarily_unavailable`) carrying exactly
        `error`, `state` when sent, and `iss`;
      - soft deletion of stale clients and their inability to authorize, then
        hard deletion once no authorization request or grant references them;
      - that a valid authorize updates `last_used_time`, so a client unused
        for over 30 days that starts a consent flow is not cleaned up before
        the code exchange;
      - that a failing authorize (wrong redirect URI, scope or resource) does
        not update `last_used_time`;
      - that a client locked by an in-flight authorize is skipped by cleanup,
        that a raw grant-row insert for the same client does not wait for an
        in-flight authorize, and that authorize for an already soft-deleted
        client fails as an invalid client and leaves no pending request. The
        token-time wait is tested by TASK-069F in the same module. These lock
        tests live in the PostgreSQL integration module
        `backend/tests/test_mcp_oauth_postgresql_integration.py`, because
        SQLite has no row locks;
      - registration running cleanup before the cap check, so reclaimable
        stale clients free room, and the cap answering 503
        `temporarily_unavailable` with a warning log entry;
      - the `client_name` allowlist. These are rejected:
        - a missing or empty name, and one longer than 100 characters after
          trimming;
        - a tab, a newline or U+2028 anywhere, including at the start or end;
        - U+202E, U+200B and U+3164;
        - a look-alike non-ASCII letter, such as Cyrillic `С` in `Сlaude`;
        - a disallowed ASCII character such as `<` or `"`;
        - a name of only spaces or only punctuation.

        Names such as `Claude`, `Claude Code (CLI)` and `my-client_2` are
        accepted, and a name with surrounding spaces is stored trimmed;
      - the redirect URI bounds;
      - CSRF and Origin rejection on approve;
      - the `oauth_rate_limiter` buckets, which never consume
        `auth_rate_limiter` entries;
      - the backend access-log filter redacting `request` and `return_to`.
- [ ] `test_api_authorization.py` builds the app both with default settings
      and with `MCP_ENABLED=true` (through `create_app(settings=...)` or a
      parametrisation), so the sweep includes the MCP-gated `/api/v1/ai/*`
      routes. It passes in both configurations.
- [ ] No plaintext request id or code is persisted in `mcp_oauth_*`, and no URL
      path contains the request id.
- [ ] `caddy validate` passes for both Caddyfiles. A manual local check shows
      the request id, `return_to` and `Location` values redacted in the Caddy
      access log.
- [ ] With `MCP_ENABLED=false` all endpoints of this task return 404 and
      `features.mcp` is `false`.

## Out Of Scope

- The token, refresh and revoke endpoints and the connections API (TASK-069F).
- The SPA consent page (TASK-069L) and the MCP servers (TASK-069G).

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-004-authentication.md
docs/decisions/ADR-013-shared-entra-local-https-deployment.md
docs/decisions/ADR-015-ai-via-mcp.md
docs/domains/AI.md
docs/TESTING.md
backend/app/main.py
backend/app/api/v1/auth/{router,service,dependencies,rate_limit}.py
frontend/Caddyfile
local/Caddyfile
```

- The session cookie is `SameSite=Strict`, so the backend authorize endpoint
  cannot rely on it. The consent decision must therefore happen in the SPA
  through same-origin calls. The existing `GET /api/v1/auth/login?return_to=`
  already handles anonymous users.
- Put the code in `backend/app/api/v1/mcp_oauth/` (`service.py`, `router.py`,
  `consent_router.py`, `schemas.py`).

## Testing

Required:

- [ ] Backend tests (`backend/tests/test_mcp_oauth_authorize.py`)
- [ ] PostgreSQL integration tests for the client row lock and `SKIP LOCKED`
      cleanup (`backend/tests/test_mcp_oauth_postgresql_integration.py`,
      skipped without `MIGRATION_TEST_DATABASE_URL`, always run in CI)
- [ ] Manual verification (Caddy routing of `/.well-known/oauth-*` locally)
- [ ] Lint
- [ ] Typecheck

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
MIGRATION_TEST_DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten \
  uv run pytest tests/test_mcp_oauth_postgresql_integration.py -v
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Update `docs/domains/AI.md`, `ARCHITECTURE.md` (routing),
`docs/DEPLOYMENT.md` and `docs/LOCAL-DEVELOPMENT.md` (new settings), and the
LikeC4 model if the implementation differs from it.

## Notes For AI Agent

- Branch: `feature/TASK-069E-mcp-oauth-authorize-consent`.
- Do not start until TASK-069D is merged.
- Do not add dependencies.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069E/`.
- Report all changed files and every verification command run.
