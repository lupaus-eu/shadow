---
status: accepted
---

# Expose model tools through MCP by calling the REST endpoints

## Context

MCP offered only organization tools. Agents should read and run models, versions, metrics, simulations, and analysis, under the same rules as the web application (ADR-0037).

## Decision

- `mcp_server/model_tools.py` maps each router's route names to their endpoint functions and calls them with the signed-in user and a stub request. Roles, the read-only state, `expected_version`, limits, and audit (`source: "mcp"`) are therefore the REST rules, not copies of them.
- Reads and writes are separate tools with MCP annotations; the deleting tools are marked destructive. Validation errors come back as readable tool errors.
- Agents get no metamodel editing and no import or export. The only deleting tools are `delete_event` (a correction of a recorded history, refused when the chain would break) and `adopt_scenario` (it can delete the adopted Scenario); both are marked destructive (ADR-0048, ADR-0050). (ADR-0047 adds `set_analysis_summary` and `add_proposal`, so agents write their own analysis.)

## Consequences

- A change to an endpoint signature or dependency can break the matching tool; `tests/test_mcp.py` covers the main path.
- Extending the agent surface means adding a tool, not new business logic.
