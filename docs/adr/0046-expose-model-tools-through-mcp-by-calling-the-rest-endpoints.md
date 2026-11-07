---
status: accepted
---

# Expose model tools through MCP by calling the REST endpoints

## Context

MCP offered only organization tools. Agents should read and run models, versions, metrics, simulations, and analysis, under the same rules as the web application (ADR-0037).

## Decision

- `mcp_server/model_tools.py` maps each router's route names to their endpoint functions and calls them with the signed-in user and a stub request. Roles, the read-only state, `expected_version`, limits, and audit (`source: "mcp"`) are therefore the REST rules, not copies of them.
- Reads and writes are separate tools with MCP annotations; `merge_version` is marked destructive. Validation errors come back as readable tool errors.
- No delete tools, no metamodel editing, no import or export, and no AI analysis are offered to agents.

## Consequences

- A change to an endpoint signature or dependency can break the matching tool; `tests/test_mcp.py` covers the main path.
- Extending the agent surface means adding a tool, not new business logic.
