# TASK-069H MCP Read Tools And Generator Preview

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Schatten
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

## Goal

Complete the read service so that an AI client can inspect everything it needs
before proposing changes. That covers the metamodel, graph, timeseries and
events, plus a preview of generated series.

## Requirements

- Add these tools to `backend/app/mcp/read_server.py`. Each has the same
  annotations and scope as in TASK-069G.
  - `get_type_catalog(organisation_key, scenario_key)` returns node and edge
    types, attributes, allowed connections, and the timeserie defaults and
    `timeserie_id_rule`.
  - `get_graph(organisation_key, scenario_key, org_state_key)` returns the
    graph as visible at the org state's target date.
  - `list_timeseries(organisation_key, scenario_key, include_values=False)`
    returns definitions, short names, units and derived formulas.
  - `get_timeserie(organisation_key, scenario_key, timeserie_key, from_date=None, to_date=None)`
  - `list_events(organisation_key, scenario_key)`
  - `preview_generated_timeserie(spec: TimeserieGenerationSpec)` returns the
    point count, min, max and mean, and a sample of the first and last points.
    It persists nothing.
- Tool docstrings must be precise. They are the LLM-facing contract: what each
  argument means, the date alignment rules, and the limits.
- Cap response sizes. Value lists are bounded by a date range or a maximum
  number of points, and the tool says when output is truncated.
- Reuse the existing service functions and response schemas. Do not duplicate
  query logic.

## Acceptance Criteria

- [ ] In-memory `fastmcp.Client` tests cover each tool against seeded data,
      including not-found errors and the truncation flag.
- [ ] The preview gives deterministic output for a fixed seed and returns
      validation errors for an invalid spec.
- [ ] Tool listing shows `readOnlyHint=true` for every read tool.

## Out Of Scope

- Change-set tools (TASK-069J and TASK-069K), prediction tools, and MCP
  prompts (TASK-069N).

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/decisions/ADR-015-ai-via-mcp.md
docs/domains/ORG_STATES.md
docs/domains/ORG_TWIN_STRUCTURE.md
docs/concepts/METAMODEL.md
docs/concepts/SCENARIO.md
docs/concepts/ORGANISATION_STATE.md
docs/TESTING.md
tasks/TASK-069C-timeseries-generator.md
tasks/TASK-069G-mcp-read-server-foundation.md
```

## Testing

Required:

- [ ] Backend tests (`backend/tests/test_mcp_tools.py`)
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

Update `docs/domains/AI.md` with the read tool catalogue.

## Notes For AI Agent

- Branch: `feature/TASK-069H-mcp-read-tools`.
- Do not start until TASK-069G and TASK-069C are merged.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069H/`.
- Report all changed files and every verification command run.
