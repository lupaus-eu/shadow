"""MCP write service `/api/mcp/write`, scope `schatten.write` (ADR-015).

The write service will only stage draft change sets; no tool may apply one.
This is the scaffold: TASK-069J adds the change-set staging tools.
"""

from fastmcp import FastMCP

INSTRUCTIONS = """\
Stages draft Schatten change sets for human review. No tool can apply a change
set; a person applies or rejects each one in Schatten.
"""


def build_write_server() -> FastMCP:
    return FastMCP("Schatten write", instructions=INSTRUCTIONS, mask_error_details=True)
