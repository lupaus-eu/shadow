# Ticket 11: documentation and vocabulary

Status: implemented

## Goal

Update the glossary and the user and admin guides for the timeline.

## Implementation

- `CONTEXT.md`: Base line, Scenario, Line, Event, Change, Planned event, Present state, Branch point, State, Chain, Adopt; retire Version, Baseline, Change list, Merge.
- `docs/user/README.md`, `docs/admin/README.md`, `docs/architecture/` overview, C4 views; PRD checkboxes ticked after testing.

## Acceptance criteria

- [x] Every PRD documentation effect is done or justified; `make models` passes.

## Testing

- [ ] Backend/API test — not applicable
- [ ] Frontend/UI test — not applicable
- [ ] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — `make models`, `python3 scripts/scratch-status.py`

## Ajetut tarkistukset

- [x] `make models` (repo root) — passed (LikeC4 valid, 4 files; `test_dbml_model.py` 1 passed; `dbml2sql` generated the PostgreSQL dump).
- [x] `python3 scripts/scratch-status.py > .scratch/_PORTFOLIO.md` — run after the commit, which was amended to include the file.
- Not run: backend and frontend suites (documentation only; no code change in this ticket).

## AI review

- [x] Self-review of the diff: statements in the user and admin guides were checked against `docs/design/ui-foundation.md`, `docs/runbooks/mcp-interface.md`, `frontend/src/models/timeline.ts` (refusal and adoption messages) and the roles tests; the guide's Types-tab advice for the `missing_type` and `connection_not_allowed` refusals is a reasonable reading of the code, not a tested flow. The Finnish texts were not reviewed by a native speaker.

## Documentation effects

- [x] Update `docs/user/`: `docs/user/README.md` (timeline, Scenarios, planned events, correcting history, chain-broken refusals, starting a Scenario, adoption, Structure canvas)
- [x] Update `docs/admin/`: `docs/admin/README.md` (who writes the Base line, Scenarios, adoption, limits, agent tools)
- [x] Update architecture or ADR: `docs/architecture/README.md` (timeline pointers). The C4 model already holds the Model timeline component, its relationships and the `eventWrite` flows (tickets 05 and 06), so `docs/architecture/c4/` needed no change; the DBML was current from ticket 08.
- [x] Update `CONTEXT.md`: Line, Base line, Scenario, Event, Change, Planned event, State, Present state, Branch point, Chain, Adopt, Position, Canvas and View added; Version, Baseline, Change list and Merge marked retired with pointers; stale Version wording removed from Model, Node, Connection, Metric, Simulation, Import, Agent tool and Organization Admin. Also updated `.scratch/model-timeline/PRD.md` and `.scratch/structure-canvas/PRD.md`.
- `docs/legal/`: evaluated, no change. Audit entries carry ids and counts only, no element names or note text; the new tables hold the same kind of Organization content as the former model tables, so the privacy notice, processing records and storage notice remain accurate. No new cookie or storage key.

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 08
- 09

## Completion record

- Glossary, user and admin guides, architecture overview and both PRDs updated; `make models` passes. The model-timeline PRD criteria demonstrated by backend tests (lines, events, state, metrics, adoption, MCP, read-only Organization, performance) and all its documentation effects are ticked, each group with a "Verified by:" note.
- Left unticked on purpose in `.scratch/model-timeline/PRD.md`: a Scenario's start-changed notice and the visible Base line marking; planned colour/label/Now divider and "the person's input stays on the screen" (Vitest and mocked-API Playwright only); and "the only way the canvas, analysis and MCP read a graph" (design claim). In `.scratch/structure-canvas/PRD.md` every interaction, layout, accessibility and time-control criterion stays unticked because its only evidence is Playwright against a mocked API in Chromium or hand testing; only the unit-test and not-performance-gated criteria and the documentation effects are ticked.

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
