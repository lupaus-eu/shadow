# Ticket 03: Agents write the analysis summary and proposals

Status: resolved

## Goal

An agent can write a summary and action proposals for a simulation through MCP, by the same rules as the web application.

## Implementation

- Routes (member session, blocked when read-only): `PUT .../analysis/summary` `{text}` (1–4000 characters) and `PUT .../analysis/proposals/{metric_key}` `{title, rationale, severity}`; the proposal is source `agent`, one per metric, replaced on repeat. The metric must belong to the simulation.
- The summary author is the person's display name, or `agent:<client id>` when the call comes through MCP (`audit_source`).
- Audit `analysis.summary_set` and `analysis.proposal_set` without text.
- MCP tools `set_analysis_summary` and `add_proposal` in `mcp_server/model_tools.py`, mapped to the routes (ADR-0046), with write annotations.
- `get_analysis` already returns summary and proposals after ticket 01; check it shows the source of each proposal.

## Acceptance criteria

- [ ] Both routes: success, length and severity bounds, unknown metric (404 or 422), Viewer-less roles (Member and above succeed), read-only Organization (blocked), wrong Organization (404).
- [ ] Repeating `add_proposal` for a metric replaces that proposal; rule regeneration does not remove it; accept and dismiss decisions survive.
- [ ] Through MCP the author is `agent:<client id>`; through the web it is the person.
- [ ] `get_analysis` returns the summary, its author and each proposal's source.

## Testing

- [ ] Backend — routes, MCP tools (`tests/test_mcp.py`), audit entries
- [ ] Frontend/E2E — not applicable (ticket 02 renders them)

## Ajetut tarkistukset

- `pytest -q tests/test_analysis.py tests/test_mcp.py` — all passed (new: web write routes incl. bounds, unknown metric 404, regenerate keeps decision, repeat replaces and reopens, workbook Summary and `agent` source; audit without text; MCP tools incl. author `agent:<client id>`, `get_analysis` shows author and proposal kind).
- Roles, read-only Organization and wrong Organization use the same `_editor_session` as `generate`, whose tests already cover them; no separate test added.
- Decision: a repeated `add_proposal` replaces the text and sets the proposal back to `proposed` (version +1), because new text needs a new decision.

## Documentation effects

- [ ] `docs/architecture/api.md` — routes and tools

## Blocked by

- Ticket 01

## Completion record

(commit and notes)
