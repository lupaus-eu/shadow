# Technical design: All AI use happens in the user's own agent

Status: implemented

PRD: [PRD.md](PRD.md). Supersedes ADR-0044 (new ADR-0047).

## Approach

Remove the AI analysis end to end, keep the analysis data model for what is
still useful (a summary and proposals), and let agents fill them through MCP
tools that call the same endpoint functions as the web application (ADR-0046).
Close the audit gap on reads. Guard against the feature coming back by a test.

## Persistence

One migration, `0058_agent_analysis`:

- `DELETE FROM recommendations WHERE kind = 'ai'` (these came from the removed
  external call; the product has no production data yet).
- `simulations.ai_summary` → `analysis_summary`, `ai_generated_at` →
  `analysis_summary_at`; add `analysis_summary_author` (text, nullable: the
  display name of the person, or `agent:<client id>` for an agent call).
- `recommendations.kind` keeps its values `rule` and `agent` (the column is
  free text with a unique key `(simulation_id, kind, metric_key)`); no
  constraint change is needed. One agent proposal per metric stays the rule, so
  an agent updates its proposal instead of piling up duplicates.

Downgrade restores the column names and drops the author column. Deleted
proposals are not restored.

DBML is regenerated with `make dbml`.

## Backend

- Delete `app/ai.py`, `AIRequest`, `_parse_answer`, `SYSTEM`, `AI_KIND`, the
  `POST .../analysis/ai` route, the `ai_client` parameter of `create_app` and
  `create_analysis_router`, `ai_available` / `ai_summary` / `ai_generated_at`
  in `AnalysisResponse`, the `analysis.ai_generated` audit event and the
  Anthropic environment handling.
- `AnalysisResponse` gains `summary`, `summary_at`, `summary_author`.
- New routes (member session, blocked when read-only, `expected_version`
  not needed because each call replaces one value):
  - `PUT .../analysis/summary` with `{text}` (1–4000 characters) sets the
    summary and its author.
  - `PUT .../analysis/proposals/{metric_key}` with `{title, rationale,
    severity}` creates or replaces the `agent` proposal of that metric. The
    metric key must belong to the simulation; severity is one of `high`,
    `medium`, `low`; lengths are bounded as for rule proposals.
  - Regenerating the rule analysis leaves `agent` proposals untouched, as it did
    for `ai`.
  - Audit: `analysis.summary_set`, `analysis.proposal_set` (counts and ids, no
    text).
- `metric_io_routes.py`: the workbook's "AI summary" row becomes "Summary"
  with its author and time; the proposals' "Source" column shows `rule` or
  `agent`.

## MCP

- New write tools `set_analysis_summary` and `add_proposal` in
  `mcp_server/model_tools.py`, mapped to the two routes above.
- **Who the agent is.** An agent has no identity of its own. MCP sign-in
  (OIDC) yields the person; the call runs with that person's role in the
  Organization (ADR-0046), and the MCP client id names the agent program. Every
  call entry carries both: `actor_user_account_id` (the person) and
  `change_summary.mcp_client` (the program). Calls with no identifiable person
  are refused before they reach a tool.
- **Audit of every call.** `mcp_server/runtime.py` already wraps each call in
  `audit_source(source="mcp", mcp_client=...)`. Extend that wrapper to write
  one `mcp_calls` row per call, in its own short transaction after the
  call finishes (so it survives a rolled-back write and a refusal). Decision
  made in ticket 04: a new table, not `audit_events`, because Audit Events are
  append-only by trigger and privilege, and read-call retention needs DELETE:
  `{tool, kind: read | write, outcome: ok | refused | error, reason,
  duration_ms, mcp_client}` plus the actor and, when the tool names one, the
  Organization. No arguments and no results are stored. The event is written
  for refused calls too, including the switch-off and blocked cases in
  `gate.py`.
  - Writes keep their endpoint's own event; the call event is additional.
  - **Light read logging.** Each tool is declared `read` or `write` in the tool
    registry. For a `write` tool, and for any refusal, a failed entry write
    fails the call (an unlogged agent action is worse than a failed one). For a
    successful `read` tool the entry is best-effort: a failed write is logged to
    the system log and the read result is returned.
  - `list_organizations` names no Organization and returns only the person's
    own memberships; its successful calls are not stored (no Organization's
    retention could reach them). A refusal for an Organization the person is not
    a member of is stored with no Organization, so it never shows in another
    Organization's Activity.
  - **Retention.** A daily worker job `mcp.read_log_cleanup` (scheduled with
    the other daily jobs, like `notifications.cleanup`) deletes `mcp_calls` with
    `kind = read` and `outcome = ok` older than `MCP_READ_LOG_RETENTION_DAYS`
    (default 90). A row-level security policy allows exactly that delete, only
    in the job's worker scope. Writes, refusals and errors are not touched.
- `docs/architecture/api.md` lists the new tools.

## Frontend

- `AnalysisPage.tsx`: remove the AI button, badge, note, failure text and
  `generateAiAnalysis`; show the summary with author and time, and an "Agent"
  badge on agent proposals; keep accept and dismiss.
- A short hint on the page: "Ask your connected agent to write a summary and
  proposals" with a link to the agent page when the person may open it.
- `AgentsPage.tsx` (Owner and Admin): add the responsibility text from the PRD.
- `ActivityPage.tsx` (Owners and Admins only, as now): `mcp_calls`
  entries are hidden from the default view and shown behind a filter "Agent
  calls" (tool, outcome, person, client, time). Read calls are folded into the
  filter, not the main list. Texts in Finnish and English with the parity test.
- Remove the unused AI messages from `messages.ts`.

## Authorization

No new roles. The two new routes need a member session. MCP stays behind the
Organization switch and the operator block; refused calls are now logged.
Agent calls are visible to Owners and Admins only, the same rule as the rest of
Activity; Members and Viewers do not see them, not even their own.

## Configuration

Remove `ANTHROPIC_API_KEY` and `SHADOW_AI_MODEL` from `.env.example`,
`.env.production.example`, `docker-compose.yml`, `docker-compose.prod.yml`.
Add `MCP_READ_LOG_RETENTION_DAYS` (default 90) to both env examples and the
backend and worker services of both Compose files.
`httpx` stays (other code uses it).

## Guard test

`backend/tests/test_no_llm_calls.py` scans `backend/app` and
`requirements*.txt` and fails on an LLM SDK package (`anthropic`, `openai`,
`google-generativeai`, `cohere`, `mistralai`) or a provider host
(`api.anthropic.com`, `api.openai.com`, `generativelanguage.googleapis.com`).
A comment at the top of the test points to ADR-0047.

## Risks

- Agent-written text is shown to colleagues. It is labelled and attributed, and
  rendered as plain text (no HTML); it is not trusted as instructions either
  (the MCP results notice about stored text already says so).
- The audit volume grows because reads are logged. One small row per call,
  without content, deleted after 90 days for successful reads. Revisit if an
  agent loops (a per-client rate limit is out of scope).
- A write's call event written in a separate transaction can fail while the
  write succeeded. The call then fails with an error (an unlogged agent action
  is worse than a failed one), and the test covers it. Reads are the stated
  exception: they fail open so that an audit fault does not stop every agent.
  The cost is that a read during an audit outage may go unrecorded; the system
  log has the failure.

## Testing

- Backend: migration up and down; the removed route answers 404; the two new
  routes (success, bounds, role, read-only, wrong metric); rule regeneration
  keeps agent proposals; export content; one `mcp_calls` per call for
  ok, refused (role, switch off, blocked) and error; person and client present
  on every entry; no arguments stored; read fails open and write fails closed
  when the entry cannot be written; cleanup job deletes only old successful
  reads; guard test.
- Frontend: typecheck, build, unit tests; messages parity. The changed
  analysis and activity pages are tested by hand in the browser by the product
  owner.
- `make models` after the C4 and DBML changes.

## Documentation effects

As listed in the PRD; each ticket names the files it updates.

## Ticket order

01 remove the LLM path → 02 analysis page → 03 agent analysis tools →
04 audit of every agent call → 05 documentation and ADR. 02 and 03 can run in
either order after 01; 04 can run after 01. 05 last.
