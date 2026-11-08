# Ticket 05: Drawing (new nodes, connecting, deleting, multi-select, undo and redo)

Status: implemented

## Goal

Drawing is direct: nodes appear where the person looks, connections are made by dragging or two clicks with only allowed types offered, several elements can be handled at once, and a person can undo and redo their own edits in the session.

## Implementation

- New node at the viewport centre with inline naming (direct editing on the node: Enter saves, Esc cancels); replaces the grid placement of the add-node form.
- Connect: the `connect` module with the context pad, or press `C` / the Connect button and click two nodes; `GraphRules` offers only the types the metamodel allows for the two node types; self-connection, duplicate and refused connections show a readable reason.
- Delete with confirmation (`Delete`/`Backspace`), including a set; the confirmation names touching connections.
- Multi-select by shift-click and the lasso tool; selected nodes move together as one command (one position write each); delete works on the set.
- Undo and redo: the diagram-js command stack is the session history; each entry has a server counterpart (inverse write after a fresh row read with `expected_version`, see the technical design). `Ctrl/Cmd+Z`, `Shift+Ctrl/Cmd+Z` and toolbar buttons with enabled state; a rejected undo (409 or 422) drops the entry and shows a readable notice; the stack clears when the version, line or event changes and on reload. A multi-node move or delete is one undo step.
- Every edit goes through `applyEdit` (optimistic command, server write, revert on refusal).
- Not done: align and snap, events, undo that survives a reload.

## Acceptance criteria

- [x] A new node appears at the viewport centre at any zoom and pan and opens for naming.
- [x] Both connect gestures create the same connection; the picker never offers a disallowed type; the three refusal causes show distinct readable messages (no raw server text).
- [x] Delete asks for confirmation and names what will be removed, including touching connections.
- [x] Shift-click and the lasso select several nodes; dragging moves them together; a stale `expected_version` gives the existing notice, reverts the move and reloads.
- [x] Undo and redo restore create, delete (same name, type, position), rename, re-route, connect and move; a multi-node move or delete is one step.
- [x] If another person changed the element meanwhile, undo is refused with a readable notice and the stack stays consistent.
- [x] Undo and redo buttons are disabled when there is nothing to undo or redo; shortcuts are ignored in text fields.
- [x] All write controls are hidden for a read-only Organization.

## Testing

- [x] Backend/API test — not applicable (frontend only; existing 409/422 paths are covered by `backend/tests/test_models_graph.py`).
- [x] Frontend/UI test — vitest for viewport-centre placement, `GraphRules` (allowed types, self-connection, duplicates), refusal message mapping, multi-select move, and the `applyEdit` seam (accepted keeps, refused reverts, inverse write on undo, drop on 409, clear on source change).
- [x] Browser/E2E validation — Playwright: add by "+", connect by drag and by clicks, refused connection message, delete with confirm, lasso move, add/rename/delete then undo three times and redo once, conflict case with a second session.
- [x] Migration/integration/architecture validation — typecheck and build.

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build` — passed (tsc clean; vite build ok).
- [x] `npm --prefix frontend run test:unit` — passed: Vitest 15 files, 164 tests (new: `history.test.ts`, `draw.test.ts`, the history tests on `applyEdit` in the same file; `modeling.test.ts` updated); the Node-runner tests passed too.
- [x] `cd frontend && npx playwright test structure-canvas` — 59 passed (17 new in `structure-canvas-drawing.spec.ts`, mocked API with `expected_version` checks, Chromium only); `npx playwright test` (whole suite) also 59 passed. Backend suite not run: no backend change.

## AI review

- [x] Self-review of the diff (no separate review tool run). Findings and decisions: (1) the diagram-js command stack cannot be the history (see Completion record), so a journal was built and tested with an in-memory server; (2) partial failure of a multi-write step (a set delete or an undo of a delete) leaves the server partly changed: the entry is dropped and the next load shows the truth; accepted and documented; (3) the set delete sends deletes one after the other with the event version counted up locally because a delete answers 204 without a version; a drift gives a stale notice, never a silent overwrite; (4) names are normalised like the server (whitespace collapsed) so the history's expectations match the stored name.

## Documentation effects

- [ ] No documentation effect
- [ ] Update `docs/user/`
- [ ] Update `docs/admin/`
- [ ] Update `docs/operations/` or `docs/runbooks/`
- [ ] Update `docs/gdpr/` or `docs/legal/`
- [x] Update architecture or ADR
- [x] Update `docs/design/`
- [ ] Update `CONTEXT.md`
- [ ] Update `.env.example`

Record exact updated file paths and explain every “No documentation effect” choice.

## Blocked by

- 03
- 04

## Completion record

- Updated: `docs/design/ui-foundation.md` (drawing rules, toolbar, keyboard map), `docs/architecture/frontend.md`, ADR-0051 findings 11-14 (`docs/adr/0051-draw-the-structure-canvas-with-diagram-js.md`), `.scratch/structure-canvas/technical-design.md`. No user, admin, operations, GDPR or `.env.example` effect (no new storage key, variable or service; user docs come in ticket 09).
- Done: all criteria met. New node at the view centre with naming in place (draft node, Enter/blur saves, Esc cancels); context pad (Connect, Delete) and library connect gesture plus `C`/toolbar two clicks end in one `planConnection` (picker for several types, three distinct refusals); delete with a confirmation naming touching connections for a node, a set and a connection; shift-click and a lasso toggle (`L`); multi-node move is one positions write and one undo step; undo/redo (Ctrl/Cmd+Z, Shift+Ctrl/Cmd+Z, Ctrl/Cmd+Y, toolbar buttons with enabled state, live region) for create, delete (name, description, type, place, connections), rename, connect, re-route and move; the move undo now saves the old position (the known gap). Finnish and English texts.
- Differences from the ticket text: (1) the session history is a journal of plain steps (`canvas/history.ts`), not the diagram-js command stack (loads clear that stack and ids change when an element is re-created; the stack still draws the optimistic edit). (2) A stale `expected_version` applies to event edits; a move is a positions write with no version, so the move criterion is covered by a refused positions write reverting the nodes (unit test) and a stale connection edit reverting (Playwright). (3) Re-route has no drag gesture: it is the From/To selects in the connection's details (undo and redo covered); dragging connection ends (bendpoints) is not built. (4) "One position write each" is one positions request with one item per node. (5) The "+" and Add no longer name nodes "<Type> <n>".
- Not verified: nothing was run in a real browser against the real backend or signed in; Playwright is Chromium with a mocked API; touch, Safari, Firefox, screen readers and a real second session were not exercised (the second session is simulated by changing the mock). The drag from the context pad was exercised with Playwright mouse events only. `backend/tests/test_browser_storage.py` not run (no storage change).
- For the next canvas tickets: sender edits are `GraphEdit` (`elements.delete` is compound); `send` in `ModelCanvas.tsx` returns `{ id }` for creates and must keep doing so (history refs). Ticket 08 must keep the history clear on event change (`ModelCanvas` effect on `event.id`). Key chords with Ctrl/Cmd go on the library keyboard (see `GraphKeys`); single keys through `keyBindings`. The toolbar has an edit group (`CanvasToolbar` `edit` and `editActions`). Hover popovers (06) must ignore the draft node (`businessObject.draft`) and the `.shadow-editor` overlay. Align/auto layout (07) should make their moves through `modeling.moveElements` so the move hook records them as one history entry.

## Comments

- Keep every edit behind one function (`applyEdit`) so ticket 08 can redirect writes into the selected event.
- Each undo is an audited write like any edit; the audit log, not the stack, is the durable history.
- This ticket absorbs the former undo/redo ticket: the command stack of diagram-js makes it part of drawing.
