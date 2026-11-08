# Ticket 03: documents and vocabulary sweep

Status: implemented

## Goal

Update the glossary, guides, ADR cross references, PRDs and runbooks to the Change and Edit vocabulary.

## Implementation

- `CONTEXT.md`: Change, Edit, State, Start, change list, planned change; retire "Event" in this sense and note that Audit Event is a different thing; user and admin guides, design docs, architecture docs, `docs/runbooks/mcp-interface.md` (tool names), operations and gdpr pages.
- The PRDs, domain model and technical designs of `model-timeline` and `structure-canvas` get the vocabulary; completion records of finished tickets stay as written, with one note at the top of each ticket file folder's PRD that records the rename.
- Add the Start row to the user guide and the design guidance.

## Acceptance criteria

- [x] `grep -ri "event"` over `docs/`, `CONTEXT.md`, `.scratch/model-timeline` and `.scratch/structure-canvas` shows only allowed uses (Audit Event, Stripe, history, completion records, ADR bodies with their closing lines).
- [x] `make models` passes; the portfolio is regenerated.

## Testing

- [ ] Backend/API test — not applicable
- [ ] Frontend/UI test — not applicable
- [ ] Browser/E2E validation — not applicable
- [x] Migration/integration/architecture validation — `make models`, `python3 scripts/scratch-status.py`

## Ajetut tarkistukset

- [x] `make models` — passed (LikeC4 validate of `docs/architecture/c4` and the DBML to SQL check; the first run failed on an apostrophe in a view label, fixed).
- [x] `python3 scripts/check-compose-ports.py` — passed (Compose ports OK).
- [x] `python3 scripts/scratch-status.py > .scratch/_PORTFOLIO.md` — run, portfolio regenerated.
- [x] `grep -rniE "\bevents?\b" docs CONTEXT.md .scratch/model-timeline .scratch/structure-canvas`, then read by section — remaining hits are only the allowed leftovers listed in the completion record.

## AI review

- [x] Self-review of the diff (no review tool run) — findings: (1) the mechanical rename left collisions where the old step "change" met the new "Change" (domain model table, "An change", "Change, Change" lists, "edits edits"); fixed by hand and re-read per file. (2) A possessive apostrophe in a LikeC4 label broke `make models`; reworded. (3) `LIMIT_EVENTS_PER_LINE` had been protected as a legacy variable by the script; replaced everywhere it names the timeline limit. (4) Yearclock Events (the organisation's own events) were left alone by editing only the timeline sections of the shared guides.

## Documentation effects

- [x] Update `docs/user/`
- [x] Update `docs/admin/`
- [x] Update architecture or ADR
- [x] Update `docs/design/`
- [x] Update `CONTEXT.md`

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 01
- 02

## Completion record

- Done: `CONTEXT.md` (Change, Edit, Change list, Start, Planned change; Event now reserved for the organisation's own happenings with a note on Audit Event, Stripe and DOM events; State, Branch point, Chain, Adopt, Line and the rest reworded; "Change list" marked as a retired meaning), `docs/user/README.md` (timeline section, Finnish terms muutos, muokkaus, suunniteltu muutos, muutoslista, Start row kept), `docs/admin/README.md`, `docs/design/README.md` (change list, change editor, new Start row guidance) and `ui-foundation.md`, `docs/architecture/api.md` (routes, fields, `changes_per_line`, hint codes, Start row via `?change_id=`, MCP), `database.md` (entry 0065; 0060-0064 keep their historical names and say so), `audit.md` and `docs/gdpr/README.md` (`change.*` and the legacy `event.*` rows), `operational-limits.md`, `operations/README.md`, `architecture/README.md`, `project-layout.md`, `frontend.md`, the C4 model (`model.c4`, `views.c4` with the view renamed `changeWrite`, `README.md`), `docs/runbooks/mcp-interface.md` (tool names and arguments); PRDs, domain model, technical designs and ticket bodies of `.scratch/model-timeline` and `.scratch/structure-canvas`, with the dated vocabulary note at the top of both PRDs. Completion records, Ajetut tarkistukset and AI review sections of finished tickets and ADR bodies were not touched. The previously untracked `domain-model.md` and `issues/01-...` of model-timeline are committed with their vocabulary update.
- Allowed leftovers of "event": Yearclock Events (the organisation's own events) throughout the shared guides and `docs/architecture/events.md`; Audit Events and `event.*` legacy audit actions; Stripe webhook events; DOM/pointer events in canvas notes; migrations 0060-0064 descriptions in `database.md`; completion records, Ajetut tarkistukset and AI review of finished tickets; ADR bodies; the eTWIN integration spec and `docs/integration/` (a separate Yearclock/eTWIN concept); `docs/end-user-tutorial/` and older runbooks (Yearclock). The Finnish guides are not separate files; Finnish terms are given in the user guide.
- Documentation effects recorded: all files above. `make models` and the Compose port check pass; the portfolio is regenerated.

## Comments

- Design: `../technical-design.md`; decision: ADR-0052.
