# Ticket 04: Audit every agent call

Status: resolved

## Goal

Every MCP tool call, including reads and refused calls, leaves a content-free audit entry naming the person and the agent program; only Owners and Admins can see them, behind a filter; read entries are kept 90 days.

## Implementation

- Declare each MCP tool `read` or `write` in the registry.
- In `mcp_server/runtime.py`, write one `mcp.tool_called` event per call in its own short transaction after the call finishes: `{tool, kind: read | write, outcome: ok | refused | error, reason, duration_ms, mcp_client}`, the acting person (`actor_user_account_id`) and the Organization when the tool names one. No arguments, no results. A call without an identifiable person is refused.
- Cover refusals from `gate.py` (switch off, operator block), role and read-only refusals, validation errors and unexpected errors.
- If the event cannot be written, a write call or a refusal fails with an error; a successful read call returns its result and the failure goes to the system log (fail-open for reads only).
- `audit_events.organization_id` is nullable: log `list_organizations` with no Organization, confirm against the RLS policy that no Organization's Activity shows it, and record that here.
- New daily worker job `mcp.read_log_cleanup` (scheduled like `notifications.cleanup`) deletes `mcp.tool_called` events with `kind = read` and `outcome = ok` older than `MCP_READ_LOG_RETENTION_DAYS` (default 90). Add the variable to both env examples and both Compose files.
- Activity API and `ActivityPage.tsx`: the default list leaves `mcp.tool_called` out; an "Agent calls" filter shows them (tool, outcome, person, client, time). Owners and Admins only, as for the rest of Activity. Finnish and English texts.
- Writes keep their own events and `source: "mcp"`.

## Acceptance criteria

- [ ] One `mcp.tool_called` per call for a read, a write, a refused call (each reason) and a failing call.
- [ ] Every entry has the acting person and the client id.
- [ ] The event holds no argument or result data (test with a distinctive value).
- [ ] A rolled-back or refused write still leaves its call event.
- [ ] If the audit write fails, a write call and a refused call return an error; a successful read returns its result and the failure is logged.
- [ ] The cleanup job deletes successful read entries older than the retention and leaves writes, refusals and errors.
- [ ] Owners and Admins see the entries behind the "Agent calls" filter and not in the default list; Members and Viewers see none, not even their own (existing Activity rule).

## Testing

- [ ] Backend — runtime wrapper, gate refusals, failure paths (read open, write closed), cleanup job
- [ ] Frontend — `tsc`, build, unit tests; Browser by the product owner

## Ajetut tarkistukset

- `pytest -q` (backend) — 201 passed. New in `tests/test_mcp.py`: every call recorded (read ok, write ok, invalid input, http 404, switch off, not a member) with person and client on each row and no content (distinctive model name); `list_organizations` not stored; read fails open and write fails closed when the row cannot be written; Owners and Admins read `/mcp-calls`, Members get 403; the cleanup job deletes only old successful reads and the application role cannot delete other rows.
- Migration 0059 up, down to 0058 and up again on a scratch database — OK. DBML regenerated (`mcp_calls` in the operations group).
- `npm --prefix frontend run typecheck`, `build`, `test:unit` (23 passed) — OK. Activity page by the product owner in the browser.
- `docker compose config -q` and `scripts/check-compose-ports.py` — OK.
- Decisions recorded: the record is a new table `mcp_calls`, not `audit_events`, since Audit Events are append-only (trigger and privileges) and retention needs DELETE; `list_organizations` is not stored; a refusal for a non-member Organization is stored without an Organization; calls with no Shadow account behind the sign-in are not stored (logged as a warning); the read-only subscription refusal has reason `read_only`.

## Documentation effects

- [ ] `docs/architecture/audit.md` — new event, read/write difference, retention
- [ ] `.env.example`, `.env.production.example`, Compose files — `MCP_READ_LOG_RETENTION_DAYS`
- [ ] `docs/operations/README.md` — the retention setting and the job
- [ ] `docs/architecture/api.md` — MCP audit paragraph

## Blocked by

- Ticket 01

## Completion record

(commit and notes)
