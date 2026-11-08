# Ticket 06: Hover popovers, label shortening and node metrics

Status: implemented

## Goal

A person can read a node's name, type and description by hovering, long names stay tidy, and a selected node shows its attached metrics.

## Implementation

- Hover popover (name, type, description) placed with the diagram-js `overlays` module so it follows pan and zoom and stays inside the canvas; also on keyboard focus.
- Labels over 60 code points are shortened with an ellipsis on canvas, in the list and in popovers; the full name shows in the popover and the details panel.
- Details panel for a selected node lists its attached metrics (name, latest value with unit) with a link to the Metrics tab; empty state when none.
- Parallel-connection offset (listed under `GraphRenderer` in the technical design as ticket 06 work, and a PRD criterion): connections between the same two nodes are offset so they do not overlap.
- Not done: editing metrics on the canvas.

## Acceptance criteria

- [x] Popover appears on hover and focus, stays within the canvas, disappears on leave and on pan.
- [x] A 80-character name shows as 59 characters plus an ellipsis on canvas and in full in the popover.
- [x] The selected node's metrics show latest value and unit; the link opens the Metrics tab for the same version.
- [x] A node without metrics shows a clear empty message.

## Testing

- [x] Backend/API test — not applicable (uses the existing metrics read).
- [x] Frontend/UI test — vitest for label shortening (code points, emoji), popover placement helper, latest-value selection.
- [x] Browser/E2E validation — Playwright: hover shows popover, long name, metrics link.
- [x] Migration/integration/architecture validation — typecheck and build.

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build` — passed (tsc no errors; vite build ok, only the existing chunk-size warning).
- [x] `npm --prefix frontend run test:unit` — passed: node tests 27/27 and vitest 210/210 in 20 files (new: `popover.test.ts` 7, `node-metrics.test.ts` 8, `graphpopover.test.ts` 12, `parallel.test.ts` 5, `useNodeMetrics.test.tsx` 7, `shapes.test.ts` extended).
- [x] `cd frontend && npx playwright test structure-canvas` (popover path; all Structure canvas specs) — passed 71/71 in Chromium against a mocked API (`tests/browser/structure-canvas-popover.spec.ts`, 12 tests, including an axe check of the details panel).
- Not run: `backend/tests/test_browser_storage.py` (no storage key added) and the full `npm --prefix frontend run test:browser` (only the `structure-canvas` specs were run).

## AI review

- [x] Review run on the ticket's diff — self-review by the implementing agent (no separate review tool or reviewer run). Findings: (1) the popover cannot be hovered (no pointer events), so WCAG 1.4.13 "hoverable" is not met by the popover itself; accepted because it shows nothing the details panel and node list do not, and it is dismissible with Esc (recorded as ADR-0051 finding 18). (2) A mouse click focuses a node, so the popover can also appear from the click and stays until focus leaves or the pointer leaves; accepted. (3) `shortenName` used to keep 60 plus an ellipsis (61), contradicting the criterion; changed to 59 plus an ellipsis and its tests updated; labels now have three lines of 22 so a 60-code-point name shows whole in the node. (4) The metrics hook first lived in `canvas/`, which the boundary test forbids (server calls); moved to `models/useNodeMetrics.ts`. (5) A name made of long words can still lose its tail to the line wrapper's own ellipsis in a node (three lines of 22); the popover shows it whole; accepted.

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

- `docs/design/ui-foundation.md` (new "Reading" bullet: popover, shortened labels, parallel connections, node metrics), `docs/architecture/frontend.md`, `docs/adr/0051-draw-the-structure-canvas-with-diagram-js.md` (findings 15-18), `.scratch/structure-canvas/technical-design.md`.
- No effect on `docs/user/` (ticket 09), admin, operations, GDPR/legal (no new storage key, cookie or data), `CONTEXT.md` (no new term; ticket 09), `.env.example` (no variable).

## Blocked by

- 02

## Completion record

- Done: all four criteria and all four testing items. Hover popover (name, type, description) as an `overlays` overlay (`diagram/GraphPopover.ts`, `canvas/popover.ts`): opens after 250 ms of hover and at once on keyboard focus (`aria-describedby`), placed on the side with room and clamped into the canvas, follows zoom, closes on leave, focus loss, Esc, pan, drag and node change, ignores the draft node, the naming input and hidden types; fade only without reduced motion. Labels over 60 code points show 59 plus an ellipsis on the canvas, in the type list and in popovers (full name in the popover, `title`, accessible name and the details panel's name field). Details panel: a Metrics section (name, latest value with unit and month, "No values yet", empty state, loading, error with Try again, link to `.../metrics?line=<id>`), read lazily on selection and cached per line (`models/useNodeMetrics.ts`, `canvas/node-metrics.ts`). Parallel-connection offset done here (it was listed for this ticket in the technical design). Finnish and English texts. Docs recorded above.
- Differences from the ticket text: the metrics link always carries `?line=<id>` (the tabs omit it for the Base line; both mean the same line). "Version" in the criterion is the line. The popover is not hoverable (see AI review). A mouse click on a node also opens the popover through its focus.
- Not verified: nothing was run in a real browser by hand, against the real backend, or signed in; Playwright is Chromium with a mocked API. Touch, Safari, Firefox and screen readers were not exercised; reduced motion was checked only through Playwright's media emulation (`animation-name` is `none`). The metrics read was not run against real metric data (the mock mirrors `GET .../metrics` and `.../series`).
- For the next canvas tickets: new `graphPopover` service listens to `drag.init`/`drag.cleanup`, so an align/auto-layout move done through `modeling.moveElements` needs no change; call `graphPopover.hide()` if a tool opens an overlay of its own over a node. Nodes now have up to three label lines (`NAME_LINES`), so export must not assume two. `GraphLayouter` offsets parallel connections only when no hints are given (layout of a connection being drawn by hand stays straight); auto layout (07) that re-lays connections out gets the offset for free. The metrics cache lives in `ModelCanvas` (a ref in `useNodeMetrics`); ticket 08 (time control) must pass a different `source` or extend the cache key if metric values ever depend on the event.

## Comments

- None.
