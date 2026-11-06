"""The MCP interface (ADR-0037, ADR-0038): a thin adapter over the application.

Agents sign in through Authentik with the dedicated MCP provider; every tool call
resolves the signed-in user and applies the same access rules as the REST API.
"""
