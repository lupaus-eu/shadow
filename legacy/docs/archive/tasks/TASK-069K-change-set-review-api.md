# TASK-069K Change-Set Review API

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Shadow
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

## Goal

Provide the cookie-session REST API that the Metrics tab uses to list, inspect,
apply and reject submitted AI change sets.

## Requirements

- Router `backend/app/api/v1/ai_change_sets/router.py`. It is included in
  `api/v1/router.py` and uses router-level `require_business_request`. Routes:
  - `GET /api/v1/organisations/{organisation_key}/ai/change-sets` lists newest
    first:
    - It filters by status and by the derived `scenario_key` that TASK-069I
      computes from the operations.
    - With a `scenario_key` filter it can also include change sets without a
      scenario reference (`includeUnscoped=true`), such as change sets that
      create a scenario or touch several.
    - Each item shows its `scenario_key` (or null).
  - `GET …/ai/change-sets/{change_set_key}` returns:
    - operations in readable form;
    - frozen values, or a summary when they are large;
    - the validation result;
    - each operation's `replaces_existing` flag and summary of the data it
      replaces, recomputed against current data with TASK-069I's
      `compute_replacements` on every read (never the submit-time copy),
      under the dry-run and apply `statement_timeout`. A target deleted
      after submit is shown as missing;
    - the `reviewFingerprint` of those flags, summaries and per-target
      checksums;
    - the creator, `clientId`, `clientName` (labelled self-declared) and
      timestamps.
  - The list and detail JSON keys are camelCase like the rest of `/api/v1`,
    for example `scenarioKey`, `replacesExisting`, `reviewFingerprint`,
    `clientId` and `clientName`. The engine (TASK-069I), the database columns
    and the path parameters keep their snake_case names.
  - `POST …/{change_set_key}/apply` (`UnsafeRequestDependency`) requires
    `{"reviewFingerprint": "<value from the detail>"}` in the body. It calls
    the engine's apply and returns the applied result. It returns 409 if the
    change set is not `submitted` (terminal), `409 apply_in_progress` if
    another transaction (normally a concurrent apply) holds the lock beyond
    `lock_timeout` (retryable), and `409 review_stale` if the recomputed
    fingerprint differs. It returns a
    retryable `503` for any other error before re-validation (lock, status or
    fingerprint step), such as a statement timeout during the recomputation.
    None of these changes the status. Each error body carries a distinct
    code.
  - `POST …/{change_set_key}/reject` (`UnsafeRequestDependency`) takes an
    optional note.
- Who may review: both roles (`admin` and `consultant`), including the
  creator, as ADR-015 decides. Record the reviewer as the actor.
- These routes stay registered when `MCP_ENABLED=false`, so humans can still
  review, apply or reject already staged change sets.
- After a successful apply, the response includes the created keys so that the
  UI can navigate to them.

## Acceptance Criteria

- [ ] API tests cover list and detail (including the status and scenario
      filters, `includeUnscoped`, and `replaces_existing` summaries that
      reflect data changed after submit), apply success, apply of a
      non-submitted change set (409), apply with a missing or stale
      `reviewFingerprint` (422 or `409 review_stale`, nothing persisted),
      `409 apply_in_progress` while another apply holds the lock, the
      retryable `503` for a statement timeout during the recomputation (each
      with its distinct error code and the status unchanged), reject, and the
      resulting status transitions and audit fields. These API tests run on
      SQLite, which has no row locks or statement timeouts. They therefore
      inject the lock-timeout and query-cancelled errors at the engine's step
      boundaries (lock step and fingerprint step) and assert the HTTP mapping.
      The real lock behaviour is covered by TASK-069I's PostgreSQL
      integration module.
- [ ] `test_api_authorization.py` covers the new routes: anonymous 401, and
      403 on an Origin or CSRF mismatch.
- [ ] A PostgreSQL integration test shows concurrent apply requests apply the
      change set only once.

## Out Of Scope

- UI (TASK-069M) and MCP tools.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/adr/0004-authentication.md
docs/adr/0015-ai-via-mcp.md
docs/architecture/domains/AI.md
docs/architecture/concepts/AI_CHANGE_SET.md
docs/operations/testing.md
backend/app/api/v1/customers/router.py   # router conventions
docs/archive/tasks/TASK-069I-ai-change-set-engine.md
```

## Testing

Required:

- [ ] Backend tests (`backend/tests/test_ai_change_sets_api.py`)
- [ ] Integration tests (concurrent apply)
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

Update `docs/architecture/domains/AI.md` (API section) and `docs/architecture/overview.md`.

## Notes For AI Agent

- Branch: `feature/TASK-069K-change-set-review-api`.
- Do not start until TASK-069I is merged.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069K/`.
- Report all changed files and every verification command run.
