# TASK-069D MCP OAuth Schema

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Shadow
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

Shadow acts as its own OAuth 2.1 authorization server for MCP clients. Its
tokens are opaque, are stored only as hashes, and belong to existing Users.

## Goal

Add the persistent schema and SQLAlchemy models for MCP OAuth clients, pending
authorization requests, grants and tokens.

## Requirements

- Add paired migrations `db/migrations/017_create_mcp_oauth_schema.sql` and
  `017_create_mcp_oauth_schema.down.sql`, run by `backend/migrate.py`, with
  these tables:
  - `mcp_oauth_clients`:
    - id;
    - unique `client_id`;
    - `client_name` (`NOT NULL`, self-declared by the client, stored trimmed,
      1 to 100 characters, with a CHECK on the length; trimming and ADR-015's
      ASCII allowlist are enforced by TASK-069E);
    - `redirect_uris` (JSON), stored exactly as validated by ADR-015's
      structured matching;
    - created time and IP;
    - `last_used_time`, updated when the client is issued a grant or token (at
      most every five minutes), and by an authorization request only after it
      is fully validated and stored. The lazy cleanup uses it to soft-delete
      clients with no active grant and a `last_used_time` (or creation time)
      older than 30 days;
    - `deleted_time`. Cleanup first soft-deletes stale clients. It then
      hard-deletes soft-deleted clients that no authorization request or
      grant references, so the client foreign keys of authorization requests
      and grants never need a delete rule (`RESTRICT`).
  - `mcp_oauth_authorization_requests`:
    - `request_id_hash` (primary key);
    - client foreign key;
    - `redirect_uri`, `state`, `code_challenge`, `scopes`, `resource`;
    - `expires_time`;
    - nullable `user_id`, `code_hash`, `code_expires_time`, `consumed_time`
      and `grant_id`. `grant_id` records the grant the code was redeemed for,
      so a second redemption can revoke that grant and all its tokens. Its
      foreign key is `ON DELETE SET NULL`, so lazy cleanup of a revoked or
      expired grant never fails on it.
    - The plaintext pending request id is never stored here. Its only
      plaintext copy is the existing login transaction's `return_to`, as
      ADR-015 allows.
  - `mcp_oauth_grants`:
    - id and `grant_key`;
    - client and user foreign keys;
    - `scopes`, which holds exactly one allowed scope, and `resource`, the
      canonical MCP resource URI that the scope belongs to;
    - `expires_time` (not null). It is the 30-day absolute lifetime anchored
      at creation and is never extended, not even when a re-authorization
      reuses the grant;
    - created, last used and revoked times;
    - `revoked_by`.
  - `mcp_oauth_tokens`:
    - `token_hash` (primary key);
    - grant foreign key, `ON DELETE CASCADE`;
    - `kind` (`access|refresh`, CHECK constraint);
    - `expires_time` and `created_time`. For a refresh token,
      `expires_time` is the 7-day idle timeout, capped at the grant's
      `expires_time`;
    - `replaced_by_hash`;
    - `revoked_time`.
    - Replaced refresh-token rows are kept until their grant expires or is
      revoked, so ADR-015's reuse detection keeps working. Document this
      retention rule in `docs/architecture/data/DATABASE.md`.
- Constraints and indexes:
  - Foreign keys to `users` follow the existing audit conventions.
  - Index the token and grant lookups, and the `expires_time` columns that
    the lazy cleanup uses.
  - Use CHECK constraints for the allowed scopes and kinds, and for exactly
    one scope per grant.
- Add SQLAlchemy models in `backend/app/api/v1/mcp_oauth/models.py`. They must
  work on SQLite for tests, so use JSON rather than JSONB-only types.
- The `mcp_oauth_*` tables never store a plaintext token, code or request id.
  ADR-015 allows the pending request id only inside the existing login
  transaction's `return_to`.

## Acceptance Criteria

- [ ] Up and down migrations both run on disposable PostgreSQL 18, and the down
      migration fully reverses the up migration.
- [ ] Model tests cover the constraints: kind and scope CHECKs, one scope per
      grant, the non-null grant expiry and the uniqueness rules.
- [ ] A PostgreSQL test shows that deleting a grant cascades to its tokens and
      sets an authorization request's `grant_id` to null, and that a client
      still referenced by an authorization request or grant cannot be
      hard-deleted.
- [ ] Only hashes are stored for secrets.
- [ ] No routes or dependencies are added.

## Out Of Scope

- OAuth endpoints (TASK-069E, TASK-069F), MCP servers and UI.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/adr/0002-database-migrations.md
docs/adr/0004-authentication.md
docs/adr/0015-ai-via-mcp.md
docs/architecture/domains/AI.md
docs/architecture/data/DATA-MODEL.md
docs/architecture/data/DATABASE.md
db/migrations/README.md
backend/app/api/v1/users/models.py   # AuthSession hashing pattern
```

## Testing

Required:

- [ ] Backend tests (`backend/tests/test_mcp_oauth_models.py`)
- [ ] Integration tests (migration up and down on PostgreSQL)
- [ ] Lint
- [ ] Typecheck

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Update `docs/architecture/data/DATABASE.md`, `docs/architecture/data/DATA-MODEL.md`,
`db/migrations/README.md`, and `docs/architecture/diagrams/db-physical-schema.puml` with its
generated SVG.

## Notes For AI Agent

- Branch: `feature/TASK-069D-mcp-oauth-schema`.
- Do not start until TASK-069A and ADR-015 are accepted.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069D/`.
- Report all changed files and every verification command run.
