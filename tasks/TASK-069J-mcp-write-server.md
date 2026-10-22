# TASK-069J MCP Write Server (Change-Set Staging)

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Schatten
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

The write service only stages change sets. There is no apply tool.

## Goal

Implement the write MCP tools so that an AI client can build, validate and
submit change sets for human review.

## Requirements

- Add tools to `backend/app/mcp/write_server.py`, scope `schatten.write`,
  `openWorldHint=False`:
  - `create_change_set(organisation_key, title, rationale)` returns the key.
    Records the grant, the copied `client_id` and client name, and the
    principal's user as
    `created_by`.
  - `add_operations(change_set_key, operations: list[ChangeSetOperation])`
    validates the schemas and appends the operations.
  - `remove_operation(change_set_key, position)` (`destructiveHint=True`).
  - `validate_change_set(change_set_key)` (`idempotentHint=True`) runs the
    dry-run and stores and returns the result for each operation: `ok`, the
    first error, then `not_run` for the rest. It also returns TASK-069I's
    `compute_replacements` output for information only. That output is not
    stored, and review and apply never use it, because they recompute it
    against current data.
  - `submit_change_set(change_set_key)` re-validates, freezes the generated
    values, sets the status to `submitted`, and returns the review URL
    `<PUBLIC_ORIGIN>/schatten/<org>/metrics?changeSet=<key>`.
  - `discard_change_set(change_set_key)` (`destructiveHint=True`).
- Only `draft` change sets can be modified, and only through grants of the
  user who created them. Other users may still read them through the read
  tools.
- Add `list_change_sets(organisation_key, status=None, scenario_key=None)`,
  filtering on the derived scenario reference, and
  `get_change_set(change_set_key)` to the read server.
- Reuse TASK-069G's capacity limiter. Enforce the limits and the statement
  timeout from TASK-069I.
- Tool docstrings must explain:
  - that the workflow is create, add, validate, fix, submit;
  - `$ref` usage: only for server-generated keys (scenarios, organisation
    states, events, derived metrics), while node, edge and timeserie keys are
    supplied by the client and referenced verbatim;
  - that dry-run stops at the first failing operation;
  - that nothing is applied until a human approves it in Schatten.

## Acceptance Criteria

- [ ] In-memory client tests cover:
      - the full staging workflow;
      - validation errors returned for each operation;
      - editing a submitted or other user's change set being rejected;
      - limits;
      - that no business table changes before a human apply.
- [ ] The write tool listing contains no apply tool.
- [ ] A read-only token cannot call the write tools (covered in
      `test_mcp_auth.py`).

## Out Of Scope

- The human apply/reject API (TASK-069K) and UI (TASK-069M).

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/decisions/ADR-015-ai-via-mcp.md
docs/domains/AI.md
docs/concepts/AI_CHANGE_SET.md
docs/TESTING.md
tasks/TASK-069G-mcp-read-server-foundation.md
tasks/TASK-069I-ai-change-set-engine.md
```

## Testing

Required:

- [ ] Backend tests (`backend/tests/test_mcp_write_tools.py`)
- [ ] Manual verification (stage and submit from Claude Code locally)
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

Update `docs/domains/AI.md` with the write tool catalogue. Update the LikeC4
`generateFlow` view if it changes.

## Notes For AI Agent

- Branch: `feature/TASK-069J-mcp-write-server`.
- Do not start until TASK-069G and TASK-069I are merged.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069J/`.
- Report all changed files and every verification command run.
