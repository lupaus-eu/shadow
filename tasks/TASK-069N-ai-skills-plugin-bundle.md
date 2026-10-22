# TASK-069N Schatten Skills, Plugin Bundle And MCP Prompts

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Schatten
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

Skills carry Schatten-specific modelling know-how to the user's AI client. The
same content is served as MCP prompts so that clients without skills support
can use it too (provider-neutral).

## Goal

Write and distribute the Schatten skills. Ship a Claude Code plugin and
marketplace bundle, and expose the same content through the read server's MCP
prompts.

## Requirements

- In `backend/app/mcp/plugin/`:
  - `skills/schatten-model-building/SKILL.md`:
    - always call `get_type_catalog` first;
    - respect allowed connections and edge lifetimes within node lifetimes,
      and use org-state target dates;
    - link timeseries to nodes following `timeserie_id_rule`;
    - use `$ref` only for server-generated keys (created or copied
      scenarios, organisation states, events and derived metrics). Graph
      node, graph edge and timeserie keys are chosen by the client and
      referenced verbatim, as in ADR-015 and TASK-069J;
    - follow the create → add → validate → fix → submit loop;
    - never claim that changes are applied before the user approves them in
      Schatten.
  - `skills/schatten-timeseries-generation/SKILL.md`:
    - choosing `time_unit` and units;
    - realistic generator parameters (trend, seasonality, noise and seed),
      with worked examples;
    - date alignment;
    - derived-metric formulas over short names;
    - always previewing before staging.
  - `.claude-plugin/plugin.json` and `.mcp.json`, pointing at
    `https://schatten.lupaus.eu/api/mcp/read` and `/api/mcp/write`.
- Add a repo-root `.claude-plugin/marketplace.json` that references the plugin,
  so users can install it in Claude Code from the repository.
- Add MCP prompts `model_building` and `timeseries_generation` to the read
  server. They are generated from the same `SKILL.md` files, with no
  duplicated text.
- Add the endpoint `GET /api/v1/ai/skills/{name}.zip` (business session). It
  returns the skill folder zipped with the standard library, for upload to
  claude.ai or Claude Desktop. Link it from `ConnectInstructions`. With
  `MCP_ENABLED=false` the endpoint is not registered (404), and the links are
  hidden because `features.mcp` is false.
- Extend TASK-069M's `ConnectInstructions` (`frontend/src/features/ai/`):
  - Claude Code plugin install instructions: add the repository marketplace,
    then install the plugin, with copy buttons;
  - the per-skill zip download links with short upload steps for claude.ai
    and Claude Desktop.

  Both are hidden when `features.mcp` is false.
- Skills are kept short and current with the tool contracts. Include only what
  a model cannot infer from the tool docstrings.

## Acceptance Criteria

- [ ] Each `SKILL.md` has valid frontmatter (`name`, `description`), and the
      plugin and marketplace JSON are valid.
- [ ] Tests:
      - the MCP prompts return the skill content;
      - the zip endpoint returns the expected file list;
      - the authorization sweep covers the zip route, building the app with
        `MCP_ENABLED=true` as TASK-069E's sweep does, and the route returns
        404 with MCP disabled;
      - frontend tests for `ConnectInstructions`: the plugin install
        instructions and the zip download links render when `features.mcp`
        is true and are hidden when it is false.
- [ ] Manual check: install the plugin in Claude Code, and generate a small
      model and series end to end with the skills active.
- [ ] No new dependency is added.

## Out Of Scope

- Publishing to any public marketplace, and skills for other vendors' formats
  beyond MCP prompts.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/decisions/ADR-015-ai-via-mcp.md
docs/domains/AI.md
docs/concepts/AI_CHANGE_SET.md
docs/concepts/METAMODEL.md
tasks/TASK-069H-mcp-read-tools.md
tasks/TASK-069J-mcp-write-server.md
```

## Testing

Required:

- [ ] Backend tests
- [ ] Frontend tests (plugin instructions and download links in
      `ConnectInstructions`, including hiding when `features.mcp` is false)
- [ ] Manual verification (Claude Code plugin install and end-to-end use)
- [ ] Lint
- [ ] Typecheck

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
cd ../frontend
pnpm format:check
pnpm lint
pnpm test
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Update `docs/domains/AI.md` (skills and distribution), `README.md` (how to
connect an AI client) and `docs/LOCAL-DEVELOPMENT.md`.

## Notes For AI Agent

- Branch: `feature/TASK-069N-ai-skills-plugin-bundle`.
- Do not start until TASK-069J and TASK-069M are merged. This task adds the
  skill download links and the Claude Code plugin instructions to
  TASK-069M's `ConnectInstructions`; TASK-069M does not reference this task's
  output.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069N/`.
- Report all changed files and every verification command run.
