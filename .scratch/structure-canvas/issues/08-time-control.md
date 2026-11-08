# Ticket 08: Time control (scenario picker, event list, edits into the selected event)

Status: implemented

## Goal

The canvas shows the state after a chosen event of a chosen line, and drawing edits that event, with refusals shown readably.

## Implementation

- `useGraphState` gets the source `{kind:"event", lineId, eventId}`; the version source is retired when the timeline replaces versions.
- Scenario picker (Base line visibly different) and the event list with dates; planned events in another colour with a "Planned" label and a "Now" divider; choosing an event redraws the state after it.
- "New event" asks for a title and a date (Base line suggests today), creates it and selects it; "New scenario from here" starts a scenario at the shown state.
- Canvas edits go through `applyEdit` (its server target changes to the selected event; the command stack and revert-on-refusal stay) into the selected event (add, remove, rename, re-type, re-route); node moves write positions only.
- A 422 `chain_broken` answer is shown as a readable message naming the event and element, with what to do first; the person's work stays on the canvas.
- Elements added, removed or re-routed by the shown event are marked on the canvas (replaces the version change list).
- Not done: the event editor and list screens themselves (`model-timeline/09`), adoption.

## Acceptance criteria

- [x] Choosing an event, planned or not, redraws the state after it; the Base line and Scenarios are clearly distinguishable.
- [x] Planned events are marked by colour and text; the "Now" divider sits between the last happened and first planned event.
- [x] An edit changes the selected event's changes in one validated write; a refused edit leaves the server and the on-screen work unchanged and shows the readable message.
- [x] Marks show what the shown event added, removed and re-routed.
- [x] Members cannot edit Base line events (controls hidden, server 403 handled); read-only Organizations cannot edit.
- [x] "New scenario from here" creates a scenario at the shown state, from the past or the present.

## Testing

- [x] Backend/API test — not applicable here (covered by `model-timeline/05`); contract check against its routes.
- [x] Frontend/UI test — vitest for the event source mapping, planned/"Now" ordering, and the `chain_broken` message mapping.
- [x] Browser/E2E validation — Playwright: pick an earlier event, draw into it, hit a refused edit, create a scenario from a past event (mocked API, `model-timeline.spec.ts` and `structure-canvas-time.spec.ts`).
- [x] Migration/integration/architecture validation — typecheck and build.

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build` — passed (build 5 s).
- [x] `npm --prefix frontend run test:unit` — node tests 0 failed; vitest 27 files, 284 tests passed.
- [x] `cd frontend && npx playwright test structure-canvas model-timeline` — 89 passed (mocked API; no real sign-in, no real backend).

## AI review

- [x] Self-review of the diff (no separate review tool run). Findings: (1) a canvas caption in the page flow shrank the drawing area after its first fit (a later size change leaves the fitted view stale), so the label is an overlay that takes no room; (2) stale and 403 answers keep their existing canvas texts, because existing tests and texts depend on them, while `chain_broken` and `branch_point` use `refusalMessage`; (3) ghosts are a separate SVG layer, not diagram elements, which is what keeps them from being selected or edited; the trade-off is that Fit and the minimap ignore them. Accepted: ghost connections are straight lines between node centres.

## Documentation effects

- [ ] No documentation effect
- [ ] Update `docs/user/`
- [ ] Update `docs/admin/`
- [ ] Update `docs/operations/` or `docs/runbooks/`
- [ ] Update `docs/gdpr/` or `docs/legal/`
- [x] Update architecture or ADR — `docs/architecture/frontend.md` (edit target, ghosts)
- [x] Update `docs/design/` — `docs/design/ui-foundation.md` (time control, marks, edit target, refusals)
- [ ] Update `CONTEXT.md`
- [ ] Update `.env.example`

Record exact updated file paths and explain every “No documentation effect” choice.

## Blocked by

- 02
- 05
- model-timeline/05 (event write routes with chain validation)
- model-timeline/09 (frontend event list and scenario picker)

## Completion record

- Canvas edits now go into the shown event whichever it is: `writable` is the subscription and `canWriteLine` only (`canvas/edit-target.ts`), the edit target is the event the state route returned, its `version` is read again after each write, and `reloadEvents` follows. Node moves still write positions only. Undo history is dropped on a change of event or line (the canvas is rebuilt when the source changes; `shouldClearHistory` is the rule the effect uses).
- Refusals: 422 `chain_broken` and 409 `branch_point` show `refusalMessage` (event, element, what to do first); stale and 403 keep their texts; the optimistic change is reverted and other work stays.
- Marks: `+` and `~` badges existed from ticket 02; added removed elements as ghosts (`canvas/ghosts.ts`, `GraphData.ghosts` from the state route's `removed` lists): dashed outline with a `-` badge in a layer that is not a diagram element, so they cannot be selected or edited; a legend/counts and a text list in the details panel. Overlay caption on the canvas says line (Base line or Scenario look different), event and Planned.
- Entry points "New event" and "New scenario from here" already exist in the model page's line bar and event list (above the canvas), so no new canvas buttons were added. Scenario start changes needed nothing on the canvas.
- Read-only Organization and Members on the Base line: `canWriteLine` and the subscription decide; covered by a Playwright test for the Member (controls hidden) and the existing read-only subscription tests.
- Existing test `model-timeline.spec.ts` for an earlier event changed from "read-only" to "edits that event".
- Not verified: real browser against the real backend, real sign-in, the 403 answer of a Member against the real server (the mocked test checks hidden controls only), phone layout of the overlay caption, visual look of ghosts (the product owner tests the UI by hand). Criterion "New scenario from here from the past" is covered by the existing `model-timeline.spec.ts` test from ticket 09.

## Comments

- Ticket numbers in `model-timeline/` are those of `.scratch/model-timeline/issues/`.
