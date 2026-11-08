# Ticket 07: MCP company context (080E)

Status: wontfix

Closed with the feature: superseded by the Yearclock platform base (see the PRD note).

## Goal

MCP tools work in the person's company and no longer read `users.role`.

## Implementation

- `McpToolRuntime` sessions use the tenant hook; company resolved from memberships (one → implicit; none/several → clear tool error).
- `allowed_scopes_for_role` independent of `users.role` (customer accounts get read and write).
- `whoami` shows the company.

## Acceptance criteria

- [ ] One-company person works unchanged; two-company person gets the error; another company's key answers not found.
- [ ] Token issuing works without `users.role`.

## Testing

- Backend/API — MCP tool and token tests

## Documentation effects

- `docs/architecture/` MCP model (LikeC4) and `AI.md`, `docs/user/` MCP guide

## Blocked by

- 04
- 05
- 06

## Completion record

(filled in when implemented: executed checks, AI review, deviations)
