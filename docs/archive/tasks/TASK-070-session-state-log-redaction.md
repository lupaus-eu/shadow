# TASK-070 Session State Log Redaction

## Source Plan

Found during TASK-069P (AI via MCP end-to-end QA) and approved as a separate
small fix (2026-10-30). On the local stack, Caddy logged the direct-Entra
login callback as
`/api/v1/auth/callback?code=REDACTED&session_state=<uuid>&state=REDACTED`:
`code` and `state` are redacted, but Entra's `session_state` is not.

ADR-004 and ADR-015 require that Caddy and backend logs never carry login
callback values. `session_state` is an Entra session identifier, not a
credential, so this is low-severity hardening of the existing login logging.

## Goal

Caddy access logs, in development and production, and the backend access-log
filter replace every `session_state` query value with `REDACTED`, like the
other callback values. Regression checks cover the new key.

## Requirements

- Add `replace session_state REDACTED` to the `request>uri query` log filter
  in `local/Caddyfile` and `frontend/Caddyfile`.
- Add `session_state` to the backend's sensitive query keys in
  `backend/app/api/v1/auth/logging.py`. The backend already drops the whole
  callback query, so this covers `session_state` on any other path.
- Extend the existing log-redaction regression coverage:
  - backend `SensitiveQueryFilter` tests: the callback query with
    `session_state` is dropped, and `session_state` on another path is
    redacted while unrelated keys stay;
  - the production frontend image check
    (`.github/scripts/verify-production-frontend-client.py` and
    `verify-production-frontend.sh`): a `session_state` value never appears
    in the Caddy log and `session_state=REDACTED` does;
  - the local Caddy configuration check
    (`scripts/verify-local-direct-entra-config.sh`) requires the new local
    Caddyfile rule.
- Update the documentation that lists the redacted query keys.

## Acceptance Criteria

- [x] Both Caddyfiles redact `session_state` query values.
- [x] The backend access-log filter redacts `session_state` query values.
- [x] Backend tests cover `session_state` on the callback and on another path.
- [x] The production frontend image check fails if `session_state` leaks.
- [x] The local Caddy configuration check requires the new rule.
- [x] After a local Caddy reload, a probe request with a dummy
      `session_state` value is logged as `session_state=REDACTED`.
- [x] ADR-004, `docs/architecture/deployment.md`, `docs/operations/local-development.md`,
      `docs/operations/testing.md` and the OIDC login sequence diagram list
      `session_state`.

## Out Of Scope

- Other Entra or OIDC parameters, log formats or log retention.
- Changes to the login flow, the Entra registration or the MCP OAuth server.
- `docs/operations/qa/AI-MCP-QA-CHECKLIST.md`: it exists only on the TASK-069P branch,
  which records the finding's resolution when it rebases onto this fix.

## Implementation Notes

- Caddy's `query` filter matches parameter names exactly, so `replace state`
  does not cover `session_state`; the backend regex anchors keys after `?` or
  `&`, so `state=` does not match inside `session_state=` either.
- No new dependency, schema or architecture change. ADR-004's logging
  paragraph gets `session_state` added to its key list as a clarification of
  the existing policy.

## Testing

Required:

- [x] Backend tests
- [x] Lint
- [x] Typecheck
- [x] Manual verification (local Caddy reload and probe)

Not applicable:

- [x] Frontend tests, format check and build: no frontend source changes; the
      frontend Caddyfile is covered by the production frontend image check,
      which runs in CI.

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest tests/test_auth_api.py
uv run pytest
uv run pyright

bash scripts/verify-local-direct-entra-config.sh
FRONTEND_IMAGE=<built image> bash .github/scripts/verify-production-frontend.sh
```

## Documentation

- `docs/adr/0004-authentication.md`
- `docs/architecture/deployment.md`
- `docs/operations/local-development.md`
- `docs/operations/testing.md`
- `docs/architecture/diagrams/sequence-oidc-login.puml`
- `docs/architecture/diagrams/generated/sequence-oidc-login.svg`
