# TASK-069G MCP Runtime Foundation And Read Server

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Schatten
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

## Goal

Add FastMCP to the backend. Mount the read and write MCP endpoints with bearer
authentication and resource protection. Ship the read server with its first
tools.

## Requirements

- Add the `fastmcp` dependency, pinned to a compatible major version. ADR-015
  records the developer's approval (confirmed 2026-10-22). First verify it is
  compatible with the locked FastAPI and Starlette versions. If it is not, use
  the fallback ADR-015 records: the official `mcp` SDK's bundled FastMCP.
- Spike-check the routing first and record the result in the PR.
- In `create_app()` (`backend/app/main.py`):
  - Build both FastMCP servers inside the factory, not at module level. Use
    `stateless_http=True` and `json_response=True`.
  - Register exact routes `/api/mcp/read` and `/api/mcp/write` (GET, POST and
    DELETE), each wrapping the server's HTTP app in `McpBearerAuth`. Do not use
    `app.mount`, which causes a 307 trailing-slash redirect.
  - Run a combined lifespan for both session managers. The OIDC provider
    initialisation stays gated on `app_environment != "test"`. Today the test
    environment builds the app with no lifespan, so this has to change.
  - When `MCP_ENABLED=false`, register no MCP routes.
- `backend/app/mcp/auth.py`, `McpBearerAuth` (ASGI):
  - Read `Authorization: Bearer` and call `verify_access_token` with the
    server's canonical resource (`<PUBLIC_ORIGIN>/api/mcp/<server>`) and its
    scope. Audience binding is mandatory: a token issued for the other
    resource is rejected.
  - Return 401 with
    `WWW-Authenticate: Bearer resource_metadata="<origin>/.well-known/oauth-protected-resource/api/mcp/<server>"`,
    adding `error="invalid_token"` when a token was presented but rejected,
    including the resource mismatch.
  - Return 403 with
    `WWW-Authenticate: Bearer error="insufficient_scope", scope="<scope>", resource_metadata="..."`
    when the token's effective scopes, after the role mapping, lack the
    server's scope.
  - Set the principal in a contextvar.
- Resource protection:
  - Tools run their DB work through `anyio.to_thread.run_sync` with their own
    session and a shared `anyio.CapacityLimiter`, configurable with a default
    of 4.
  - Rate-limit per grant on `/api/mcp/*` with a new, separate
    `mcp_rate_limiter` (another `FixedWindowRateLimiter` instance), never
    `auth_rate_limiter` or `oauth_rate_limiter`.
  - Never log tool arguments or tokens.
- Read server `backend/app/mcp/read_server.py`, scope `schatten.read`. Tool
  annotations: `readOnlyHint`, `idempotentHint`, `openWorldHint=False`.
  - Tools: `whoami`, `list_organisations`, `list_scenarios(organisation_key)`
    and `list_org_states(organisation_key, scenario_key)`.
  - Tools call existing service functions and return the existing response
    schemas.
- Write server `backend/app/mcp/write_server.py`, scope `schatten.write`: only
  the scaffold here, with no tools yet (TASK-069J).

## Acceptance Criteria

- [ ] `backend/tests/test_mcp_auth.py` (using `with TestClient(app)` so the
      lifespan runs) covers:
      - no token returns 401 with `WWW-Authenticate`;
      - a token issued for the read resource returns 401 `invalid_token` on
        `/api/mcp/write`, and vice versa;
      - a token whose effective scopes lack the server's scope (stubbed role
        mapping) returns 403 `insufficient_scope` with the scope in
        `WWW-Authenticate`;
      - per-grant limiting uses `mcp_rate_limiter` only;
      - expired and revoked tokens, a revoked grant and a deleted user;
      - a role change taking effect on the next call;
      - `MCP_ENABLED=false` gives 404.
- [ ] `backend/tests/test_mcp_tools.py` exercises the read tools through the
      `fastmcp.Client` in-memory transport with a stubbed principal.
- [ ] The existing test suite, including `test_api_authorization.py`, passes.
- [ ] The production image builds, and the backend starts with the MCP routes
      reachable through local Caddy.

## Out Of Scope

- The remaining read tools (TASK-069H) and the write tools (TASK-069J).
- Skills and MCP prompts (TASK-069N).

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-012-background-prediction-requests.md
docs/decisions/ADR-013-shared-entra-local-https-deployment.md
docs/decisions/ADR-015-ai-via-mcp.md
docs/domains/AI.md
docs/TESTING.md
backend/app/main.py
tasks/TASK-069F-mcp-oauth-tokens-connections.md
```

The host is resource-limited. Do not add a worker, background task, SSE
keep-alive stream or per-session server state.

## Testing

Required:

- [ ] Backend tests
- [ ] Manual verification: run
      `claude mcp add --transport http schatten-read https://app.localhost/api/mcp/read`
      locally, complete the OAuth flow and call `whoami`
- [ ] Lint
- [ ] Typecheck
- [ ] Build (backend image)

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Update `ARCHITECTURE.md`, `AGENTS.md` (tech stack: fastmcp), `docs/domains/AI.md`
and `docs/LOCAL-DEVELOPMENT.md` (how to connect Claude Code locally with
`NODE_EXTRA_CA_CERTS`). Update the LikeC4 model if it changes.

## Notes For AI Agent

- Branch: `feature/TASK-069G-mcp-read-server-foundation`.
- Do not start until TASK-069F is merged. The `fastmcp` dependency (or the
  `mcp` fallback) is already approved in ADR-015; no other dependency is.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069G/`.
- Report all changed files and every verification command run.
