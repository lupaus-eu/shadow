---
status: accepted
---

# Use the official Python MCP SDK for the MCP interface

## Context

Yearclock will offer a Model Context Protocol (MCP) interface so that a user's own
agents can read and change their Yearclocks. The backend is Python 3.12
with FastAPI. The MCP authorization specification (currently a draft) makes an MCP
server an OAuth 2.1 resource server: it publishes Protected Resource Metadata
(RFC 9728), validates the access token's audience, and never passes the token on to
another service. Authentik is the authorization server (ADR-0010, ADR-0036) and
establishes who the user is; Yearclock decides what they may do
(`docs/architecture/authentication.md`).

Options considered: the official `mcp` SDK; the standalone `fastmcp` package; tools
generated from the OpenAPI schema (fastapi-mcp, `from_fastapi`); a hand-written
implementation.

## Decision

- Use the **official `mcp` Python SDK** (PyPI `mcp`, high-level `FastMCP` API). At the
  time of this decision the latest release is 2.3.0 (2026-10-02). Pin an exact version
  in `backend/requirements.txt` and read the SDK's current authorization API before
  implementation, because the 2.x line may differ from earlier ones.
- The MCP layer is a **thin adapter** over the existing application services. Tools
  call the same service functions as the REST routes; they hold no business rules and
  make no direct database queries.
- **Authorization stays in Yearclock.** The access token identifies the user by
  issuer and subject. Every tool call resolves the User Account and checks the
  Organization membership and role with the same code as the REST API, fails closed,
  and writes to the Audit Log with the agent's client identity. Authentik groups and
  claims grant nothing.
- **Do not generate tools from the OpenAPI schema.** REST endpoints are too many and
  too fine-grained for agents, and they assume cookie sessions. Tools are designed per
  task, with descriptions written for agents, and take the Organization explicitly.
- **Transport** is Streamable HTTP, stateless, so the server holds no MCP session
  across requests or restarts.
- **Yearclock offers the capability and is no stricter a gatekeeper than its own UI.**
  Which agent a person uses, which tools it may call, and whether it asks before it
  acts are the user's and the MCP client's decisions, not Yearclock's. Yearclock has no
  agent interface of its own (no agent tab, chat, or assistant): responsibility for
  what an agent does stays with the person who connected it.
- **Writes are direct, with no approval step in Yearclock.** A user who connects an
  agent trusts it; a change made through MCP is saved like any other, under the same
  rules as the REST API (role, `expected_version`, limits, subscription access). It
  records an Event Revision and an Audit Log entry that names the source (MCP), the
  client, and the user whose sign-in it used. Confirmation before a write belongs to
  the MCP client (the harness): write and delete tools carry the MCP tool annotations
  (`readOnlyHint`, `destructiveHint`) so a client can ask the user first. There are no
  separate read and write scopes; a user who wants a read-only agent turns the write
  tools off in the client. The first release ships read only. Consistent with ADR-0027, nothing here adds assignment,
  completion, or other state to an Event.
- The token verifier validates signature, issuer, expiry, and an **audience equal to
  this MCP server's resource URI**. Dynamic client registration versus pre-registered
  clients, and how Authentik binds the audience (RFC 8707 is unconfirmed in its
  documentation), are decided in a separate ADR after testing against Authentik 2026.8.
- Where it runs (the backend process or its own container) is decided in the
  technical design. A separate container needs a port in 8100-8199 recorded in
  `docs/architecture/docker.md`.

## Consequences

- One dependency that tracks the protocol first-hand; the draft authorization
  specification may change, so the verifier and metadata code is isolated in one module.
- MCP and REST share services, so a rule changed in one applies to both; tests cover
  that a tool and its REST equivalent reject the same callers.
- The SDK's own client and in-memory transport are used in tests; browser checks do
  not apply.
- Agents become a new actor type: the Audit Log, an Organization setting (a kill
  switch that stops all MCP traffic for that Organization), and prompt-injection handling for content
  returned to agents need their own tickets. Because writes are direct, the safeguards
  are the audit trail, Event Revisions (a change can be reverted), the Organization-level
  kill switch, and the client's confirmation prompts.
- Refines ADR-0010 and ADR-0036. Does not change ADR-0027.
