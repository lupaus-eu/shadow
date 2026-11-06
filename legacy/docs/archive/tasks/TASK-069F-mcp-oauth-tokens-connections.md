# TASK-069F MCP OAuth Tokens, Revocation And Connections API

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Shadow
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

## Goal

Exchange approved authorization codes for opaque access and refresh tokens.
Rotate refresh tokens, support revocation, and provide the token verification
that the MCP servers will use. Let users list and revoke their connected
clients (grants).

## Requirements

- `POST /api/oauth/token`, public, rate-limited through the `token` bucket of
  TASK-069E's `oauth_rate_limiter`, `Cache-Control: no-store`:
  - `authorization_code`:
    - checks the PKCE S256 verifier, the redirect URI, the client and single
      use within 60 seconds;
    - requires `resource`, equal to the authorization request's canonical
      resource.
    - A second redemption of a code fails with `invalid_grant` and revokes the
      grant recorded on the request and all its tokens.
    - Grant handling: it reuses the user's grant for the same client and
      resource (and therefore the same single scope) only when that grant is
      active, that is not revoked and not past its `expires_time`. A reused
      grant keeps its original `expires_time`, and all its earlier access and
      refresh tokens are revoked before the new pair is issued. Without an
      active grant it creates one with `expires_time = now + 30 days`.
    - It issues an access token and a refresh token.
  - `refresh_token` requires `resource` to match the grant. It checks in
    ADR-015's order, and the first match decides:
    1. the grant is revoked or past its `expires_time`: `invalid_grant`, no
       further effect;
    2. the token's `revoked_time` is set: `invalid_grant`, no further effect;
    3. the token has `replaced_by_hash`: reuse detected. Revoke the grant and
       all its tokens, then return `invalid_grant`. This applies whatever the
       token's own idle expiry;
    4. the token is past its own idle expiry: `invalid_grant`;
    5. otherwise rotate.

    Rotation sets only the old row's `replaced_by_hash`. It never sets the
    old row's `revoked_time`.
  - Lifetimes, from ADR-015 and configurable:
    - access tokens 1 hour;
    - refresh tokens rotate and expire after 7 days without use;
    - a grant has a 30-day absolute `expires_time`;
    - no token's expiry exceeds its grant's.
- `POST /api/oauth/revoke` follows RFC 7009 and uses the `revoke` bucket.
- Provide `verify_access_token(session, token, required_resource,
  required_scope)`. It returns a principal: user, role, grant, client name and
  effective scopes.
  - It rejects:
    - unknown, expired or revoked tokens;
    - revoked or expired grants;
    - a grant whose resource is not `required_resource` (`invalid_token`);
    - deleted users.
  - Effective scopes are `grant.scopes ∩ allowed_scopes_for_role(user.role)`;
    a missing `required_scope` is `insufficient_scope`.
  - It updates `last_used_time` at most every 5 minutes.
- Token issuance (code exchange and refresh) updates the client's
  `last_used_time`, at most every 5 minutes. That update conflicts with an
  in-flight authorize's client row lock (TASK-069E) and can wait briefly until
  that authorize commits; the grant insert itself never waits.
- Clean up lazily during token operations, with no scheduler or worker. It
  deletes:
  - expired authorization requests;
  - expired access tokens;
  - revoked or expired grants. Their tokens cascade, and an authorization
    request's `grant_id` is set to null. TASK-069I adds
    `ai_change_sets.grant_id` with `ON DELETE SET NULL`, so this cleanup also
    never fails on, or deletes, change-set history.

  It never deletes replaced refresh tokens of an active grant, because reuse
  detection depends on them. It also runs TASK-069E's client cleanup: soft
  delete of stale clients, then hard delete once no authorization request or
  grant references them.
- Every grant revocation (user revoke, admin per-user revoke, reuse detection,
  code double redemption, and token revocation on re-authorization) writes an
  application log entry with the actor, target User id, grant key,
  `client_id`, sanitised client name, reason and revoked count, and never a
  token. These are the same fields as ADR-015. The revocation audit therefore
  survives the grant row's later deletion.
- Cookie-session connections API. It stays registered when
  `MCP_ENABLED=false`, so grants can be revoked while MCP is disabled.
  - `GET /api/v1/ai/connections` lists the current user's active grants. The
    JSON keys are camelCase like the rest of `/api/v1`: `grantKey`,
    `clientId`, `clientName` (self-declared), `scope`, `resource`,
    `createdTime`, `lastUsedTime` and `expiresTime`. The database columns and
    the `{grant_key}` path parameter keep their snake_case names.
  - `DELETE /api/v1/ai/connections/{grant_key}` revokes a grant and all its
    tokens. It uses `UnsafeRequestDependency`. Users may revoke only their own
    grants.
  - `POST /api/v1/ai/users/{user_id}/connections/revoke` is `admin`-only and
    uses `UnsafeRequestDependency`. It revokes every active grant of that User
    and all their tokens, records `revoked_by`, and returns the number
    revoked. It supports ADR-015's offboarding rule and incident procedure.
- With `MCP_ENABLED=false` the token and revoke endpoints are not registered
  and return 404.

## Acceptance Criteria

- [ ] Tests cover:
      - code exchange, including a wrong verifier, a reused code (which
        revokes the grant and its tokens), an expired code, and a missing or
        mismatched `resource`;
      - grant reuse: an active grant is reused without extending
        `expires_time` and its earlier tokens are revoked; a revoked or
        expired grant is not reused;
      - refresh rotation, the 7-day idle expiry, the grant's absolute expiry,
        and grant revocation on refresh-token reuse;
      - the check order: a rotated, non-revoked token triggers grant
        revocation even after its own idle expiry, a revoked token (for
        example after re-authorization) fails without revoking the grant, and
        rotation leaves the old row's `revoked_time` unset;
      - cleanup deleting a revoked grant while an authorization request still
        references it: the request's `grant_id` becomes null and the token
        request still succeeds. This test runs on PostgreSQL, or on SQLite
        with `PRAGMA foreign_keys=ON` as in `test_customer_models.py`, so the
        database's `ON DELETE` rules are exercised rather than code that sets
        the column to null;
      - client hard deletion after the last referencing authorization request
        and grant are gone;
      - the revocation log entry, which contains no token;
      - code exchange and refresh updating the client's `last_used_time`,
        and a second issuance within 5 minutes not writing it again;
      - in TASK-069E's PostgreSQL integration module
        `backend/tests/test_mcp_oauth_postgresql_integration.py`: the
        throttled token-time client `last_used_time` update waits behind an
        in-flight authorize and completes after it commits, while the code
        exchange's grant insert does not wait;
      - reuse detection still working after a lazy cleanup pass, by replaying
        a rotated refresh token after cleanup;
      - revoke;
      - `verify_access_token` for every rejection path, including a token
        for the other resource, and the role change taking effect immediately;
      - the connections list returning `grantKey`, `clientId` and the other
        listed fields, and revoke, including that another user's grant
        cannot be revoked;
      - the admin per-user revocation, including rejection for `consultant`
        and CSRF/Origin rejection;
      - the connections routes still working with `MCP_ENABLED=false`, while
        token and revoke return 404.
- [ ] Tokens are random, at least 256 bits, and stored only as SHA-256 hashes.
- [ ] The authorization sweep covers the new `/api/v1/ai/connections` and
      `/api/v1/ai/users/{user_id}/connections/revoke` routes.
- [ ] Token values never appear in logs.

## Out Of Scope

- MCP servers (TASK-069G) and UI (TASK-069L).
- Client ID Metadata Documents.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/adr/0004-authentication.md
docs/adr/0015-ai-via-mcp.md
docs/architecture/domains/AI.md
docs/operations/testing.md
backend/app/api/v1/auth/service.py   # session hashing pattern
docs/archive/tasks/TASK-069E-mcp-oauth-authorize-consent.md
```

## Testing

Required:

- [ ] Backend tests (`backend/tests/test_mcp_oauth_tokens.py`)
- [ ] PostgreSQL integration case added to TASK-069E's
      `backend/tests/test_mcp_oauth_postgresql_integration.py` (skipped
      without `MIGRATION_TEST_DATABASE_URL`, always run in CI)
- [ ] Lint
- [ ] Typecheck

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
MIGRATION_TEST_DATABASE_URL=postgresql://shadow:shadow_dev_password@localhost:5432/shadow \
  uv run pytest tests/test_mcp_oauth_postgresql_integration.py -v
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Update `docs/architecture/domains/AI.md`, and `docs/architecture/diagrams/sequence-oidc-login.puml` or a
new MCP OAuth sequence if useful (with its SVG). Update the LikeC4
`connectFlow` view if it changes.

## Notes For AI Agent

- Branch: `feature/TASK-069F-mcp-oauth-tokens-connections`.
- Do not start until TASK-069E is merged.
- Do not add dependencies.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069F/`.
- Report all changed files and every verification command run.
