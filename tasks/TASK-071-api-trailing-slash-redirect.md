# TASK-071 API Trailing-Slash Redirect

## Source Plan

Finding 1 of TASK-069P (AI via MCP end-to-end QA), kept out of that docs-only
task because it affects the whole API. Developer-approved fix (2026-10-30):
disable FastAPI's trailing-slash redirect instead of trusting forwarded scheme
headers in FastAPI.

Observed on the local stack (`https://app.localhost`, 2026-10-30):

```text
GET https://app.localhost/api/mcp/read/
HTTP/2 307
location: http://app.localhost/api/mcp/read
```

`POST` answers the same, and so does every FastAPI route reached with a
trailing slash, for example `/api/v1/auth/session/`.

### Cause

Starlette's `redirect_slashes`, on by default in FastAPI, answers a request
whose path differs from a route only by a trailing slash with a `307` to the
other spelling. It builds `Location` from the request's scheme and `Host`.
Both Caddyfiles send `X-Forwarded-Proto https`, but `fastapi run` and
`fastapi dev` start uvicorn with proxy headers trusted only from `127.0.0.1`.
Caddy is not on loopback, so FastAPI sees `http` and the redirect downgrades
the scheme. Production (`backend/Dockerfile` runs
`fastapi run app/main.py --host 0.0.0.0 --port 8000`) behaves the same.

### Risk

An MCP client configured with `/api/mcp/<server>/` could repeat its request,
with its bearer token, over plain HTTP if it does not drop `Authorization` on
a cross-origin redirect. A browser would do the same for an API call with a
trailing slash. MCP is disabled in production until TASK-069P's separately
approved enablement, so this is not an active production exposure for MCP
tokens, but it must be fixed before that enablement.

The redirect also contradicts ADR-004: redirects are built only from the fixed
configured public origin, never from `Host` or forwarded headers.

## Goal

FastAPI answers no request with a trailing-slash redirect. A path that differs
from a route only by a trailing slash answers `404` without `Location`, so no
request-derived redirect can downgrade the scheme or leave the public origin.

## Requirements

- Create the FastAPI app in `create_app()` with `redirect_slashes=False`, with
  a short comment on why.
- Do not change the proxy trust boundary: FastAPI still trusts no forwarded
  scheme, host or `X-Forwarded-For` data, and uvicorn's command lines and
  Caddyfiles stay unchanged.
- Add regression tests:
  - `/health/` and an `/api/v1` route with a trailing slash answer `404`
    without `Location` for `GET` and `POST`.
  - With `MCP_ENABLED=true`, `/api/mcp/read/` and `/api/mcp/write/` answer
    `404` without `Location` for `GET` and `POST`, also with a valid bearer
    token, and keep `Cache-Control: no-store`.
- Check that no frontend call, Caddy route, health check or documented URL
  depends on a trailing-slash redirect.
- Document the behaviour where the MCP routes and the backend boundary are
  described.

## Acceptance Criteria

- [ ] `create_app()` disables `redirect_slashes`.
- [ ] The regression tests fail on the previous code (`307` to `http`) and
      pass with the fix.
- [ ] No frontend API call, Caddy route, health check or documented URL uses a
      trailing slash.
- [ ] Against the fixed backend, a request to `/api/mcp/read/` from a
      non-loopback peer with Caddy's forwarded headers answers `404` without
      `Location`.
- [ ] `uv run ruff check .`, `uv run pytest` and `uv run pyright` pass in
      `backend/`.
- [ ] No dependency, Caddyfile, Compose or Dockerfile change.

## Out Of Scope

- Trusting `X-Forwarded-Proto` or other forwarded data in FastAPI, uvicorn's
  `--forwarded-allow-ips` or any other proxy-trust change (considered and not
  chosen; it would need an ADR-004/ADR-013 amendment).
- Redirecting trailing-slash requests to the canonical path from the fixed
  public origin.
- Marking TASK-069P's QA finding resolved: `docs/qa/AI-MCP-QA-CHECKLIST.md`
  exists only on TASK-069P's branch, which records it.
- Production enablement of MCP.

## Implementation Notes

- `backend/app/main.py`: `FastAPI(..., redirect_slashes=False)`. Routers
  included with `include_router` and the exact MCP routes are served by the
  app's router, so the one flag covers all of them.
- The MCP endpoints already use exact routes because `app.mount` redirects
  `/api/mcp/<server>` to a trailing slash (TASK-069G); this closes the
  remaining redirect in the other direction.
- `authentication_boundary` still runs for the `404`, so Host validation and
  `Cache-Control: no-store` for `/api/mcp/` paths are unchanged.
- Related: [ADR-004](../docs/decisions/ADR-004-authentication.md),
  [ADR-013](../docs/decisions/ADR-013-shared-entra-local-https-deployment.md),
  [ADR-015](../docs/decisions/ADR-015-ai-via-mcp.md),
  [AI domain](../docs/domains/AI.md).

## Testing

Required:

- [ ] Backend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Typecheck

Not applicable:

- [ ] Frontend tests, format check and build. Reason: no frontend change; the
      frontend was only searched for trailing-slash API calls.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Manual verification against a backend running this branch, reached from a
non-loopback peer with the headers Caddy sends:

```text
POST /api/mcp/read/  Host: app.localhost  X-Forwarded-Proto: https
-> 404, no Location
```

## Documentation

- `ARCHITECTURE.md` (API Design, AI Via MCP)
- `docs/domains/AI.md` (MCP Servers)
- `docs/TESTING.md` (authentication backend coverage)
