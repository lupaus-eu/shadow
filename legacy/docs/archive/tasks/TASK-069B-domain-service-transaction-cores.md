# TASK-069B Composable Domain Service Transaction Cores

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Shadow
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

AI change sets must run several domain operations in one transaction, both for
a dry-run that is rolled back and for an atomic apply. Today the service
functions commit inline. The session factory also uses `autoflush=False`, so a
later operation cannot see rows added by an earlier one unless they are
flushed.

## Goal

Split the domain service functions that change sets need into a core that
flushes but never commits, and the existing public wrapper that commits. REST
behaviour must not change.

## Requirements

- For each function below, add a `<name>_in_transaction(...)` core. It returns
  the ORM entity, calls `session.flush()` before returning and never commits.
  - `org_states/org_states_service.py`:
    - `create_scenario`
    - `copy_scenario`
    - `create_org_state`
    - `create_event`
    - `create_timeserie`
    - `replace_timeserie_values`
    - `create_derived_metric`
  - `org_twin_structure/org_twin_structure_service.py`:
    - `create_graph_node`
    - `patch_graph_node`
    - `create_graph_edge`
- The existing public functions keep their signatures. Each calls its core,
  then commits, refreshes and maps the response as before.
- `create_timeserie` (and any other core with an `IntegrityError` path) raises
  the same 409 `HTTPException` from a `try/except IntegrityError` around the
  flush. The public wrapper keeps its rollback behaviour.
- Cores take an explicit `actor_user_id` and keep the existing audit columns.
- Derived-metric materialisation and recalculation stay inside the same
  transaction.

## Acceptance Criteria

- [ ] All existing backend tests pass unchanged.
- [ ] A new test runs several cores in one session with a `before_commit`
      listener that raises. No commit happens, and later cores see the rows
      flushed by earlier ones: a node created on a scenario that the same
      transaction created, and an edge between two nodes created earlier in
      it.
- [ ] Rolling back that session leaves no rows behind.
- [ ] No REST route, response schema, migration or dependency changes.

## Out Of Scope

- The change-set engine (TASK-069I) and any MCP code.
- Cores for `patch_graph_edge`, `update_derived_metric` and `patch_event`.
  Add them later if they are needed.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0015-ai-via-mcp.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/operations/testing.md
backend/app/core/database.py
```

Do not use SAVEPOINTs. The SQLite in-memory test engine handles them
unreliably, and ADR-015 specifies a whole-transaction rollback for the dry-run.

## Testing

Required:

- [ ] Backend tests (new `backend/tests/test_service_transaction_cores.py`)
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

Update `docs/architecture/domains/ORG_STATES.md` and `docs/architecture/domains/ORG_TWIN_STRUCTURE.md` if
they describe service transaction boundaries.

## Notes For AI Agent

- Branch: `refactor/TASK-069B-domain-service-transaction-cores`.
- Do not start until TASK-069A and ADR-015 are accepted.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069B/`.
- Report all changed files and every verification command run.
