---
status: accepted
---

# Make no LLM calls from the system

## Context

ADR-0044 let Shadow call the Anthropic API itself for an "Analyse with AI" button. That put an API key, a bill, a sub-processor and a consent question inside the product, and it sent Organization data to a model provider on Shadow's own initiative. The product owner decided that all agent and LLM use belongs to the user's own harness and subscription.

## Decision

- Shadow never calls a large language model. No LLM SDK, provider host or key setting exists in the backend; `backend/tests/test_no_llm_calls.py` fails if one appears. Prophet and the other forecast methods are statistics, not LLMs, and stay.
- The server-side AI analysis is removed: the `/analysis/ai` route, `app/ai.py`, `ANTHROPIC_API_KEY`, `SHADOW_AI_MODEL`, the button and its texts. Migration 0058 deletes the old `ai` proposals and renames the summary columns.
- Agents do the analysis. The MCP interface offers read tools and write tools, including `set_analysis_summary` and `add_proposal`, so an agent can write its own summary and proposals back. They are stored with the author (`agent:<client>`) and source `agent`, and shown labelled "Agent".
- An agent has no identity of its own: it acts as the person who connected it, with that person's role. The agent program, its provider, its token cost and what it does with the data it reads are that person's responsibility, and the connect page says so.
- Every MCP tool call, read or write, is recorded without its arguments or result in `mcp_calls` (migration 0059), with the person and the agent program. Only Owners and Admins can read the record, in Activity under "Agent calls". Writes also keep their normal Audit Event with `source: "mcp"`. A write, a refusal or a failure fails when its record cannot be written; a successful read does not. Successful reads are deleted after 90 days (`MCP_READ_LOG_RETENTION_DAYS`).
- The record is a separate table, not `audit_events`, because Audit Events are append-only by trigger and privilege and the read-call retention needs a narrow DELETE.
- The terms of service are not changed.

## Consequences

- No sub-processor is added and no consent switch is needed; the privacy notice already says an agent the person connects is their own choice.
- Anyone who wants an AI summary needs their own agent and connector. The web interface alone shows rule-based findings and any agent-written text.
- The privacy notice does not yet say that Shadow records agent calls per person; counsel decides whether it should.
- The read log grows with agent activity. Retention bounds it; a per-client rate limit is not part of this decision.

Supersedes ADR-0044.
