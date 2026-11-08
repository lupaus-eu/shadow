# Ticket 02: Adopt diagram-js with the graph domain layer and useGraphState

Status: implemented

## Goal

The canvas is drawn by diagram-js through a small Shadow domain layer and a `useGraphState` hook, with the same behaviour as today plus shapes, colours and connection styles from the metamodel, after a check that diagram-js has the modules we expect.

## Implementation

- **First, verify the modules.** Install `diagram-js` and the small packages it needs and record in this ticket's completion record: the installed versions, and the verified list of the modules the design expects (`selection`, `move`, `moveCanvas`, `zoomScroll`, `lasso-tool`, `create`, `connect`, `context-pad`, `palette`, `rules`, `modeling`, `align-elements`, `distribute-elements`, `grid-snapping`, `keyboard`, `editor-actions`, `overlays`, command stack) and the package name for the minimap; for each one missing, who writes it instead and which later ticket grows. Performance is not measured or gated (the product owner decided it needs no confirmation).
- Add `diagram-js` (and the verified small packages) with types or a local declaration file; update ADR-0051 if the verification changes anything; list the dependencies in `docs/architecture/stack.md` and `project-layout.md`.
- Create `frontend/src/models/canvas/`: `useGraphState.ts` (source `{kind:"version", versionId}`; returns plain graph data, change markers, status, `reload`), `diagram/` (`GraphImporter`, `GraphRenderer`, `GraphRules`, `GraphModeling` with the `applyEdit` seam, module `index.ts`), `ShadowCanvas.tsx` (one `Diagram`, diffed updates, imperative handle).
- Parity: select node/connection, clear on background click, drag with `updateNode` and `expected_version` (debounced 400 ms), connect-from through the existing panel, delete, change list, read-only mode. A refused write reverts the optimistic change with `commandStack.undo()` and shows the existing readable notice.
- Shapes from `node_types.shape`, colours from the type, connection `style` (solid, dashed), `source_end`/`target_end` arrows, connection labels.
- Not done: zoom controls, new panels, new editing features (create/connect gestures, lasso, undo buttons come in tickets 03 and 05).

## Acceptance criteria

- [x] The verified module list is in the completion record, with a plan for every module that is missing.
- [x] Every action possible on the old SVG canvas still works, including stale-version notice and read-only mode.
- [x] Node shape and colour follow the node type; connection style and arrowheads follow the connection type; unknown shape falls back to a rounded rectangle.
- [x] `canvas/` imports no version-specific types; it receives data only from `useGraphState`.
- [x] Changing a node updates the diagram in place; the diagram is not recreated on each render.
- [x] A write the server refuses is reverted on the canvas and explained.
- [x] ADR-0051 matches what was verified; `stack.md` lists the new dependencies.

## Testing

- [x] Backend/API test — not applicable (frontend only).
- [x] Frontend/UI test (Vitest with jsdom; the repo had no Vitest, it was added for the canvas) — Vitest for `GraphImporter` diffing, `GraphRenderer` shape and style mapping (headless diagram-js instance) and `useGraphState` with a mocked client.
- [x] Browser/E2E validation — Playwright against a mocked API: open a model, select, drag and reload (position kept), connect, delete, refused write, stale version, read-only, axe scan.
- [x] Migration/integration/architecture validation — typecheck, build and bundle size noted in the completion record.

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build` — typecheck clean; build ok (`tsc -b && vite build`, one stylesheet, `theme.css` published). Bundle: `index-*.js` 727.76 kB (gzip 220.94 kB) before, 843.29 kB (gzip 259.73 kB) after, +115.5 kB raw / +38.8 kB gzip; `index-*.css` 33.15 kB (gzip 7.43 kB) before, 59.05 kB (gzip 12.04 kB) after, +25.9 kB raw / +4.6 kB gzip (diagram-js.css plus the canvas rules). The "chunks larger than 500 kB" warning was there before.
- [x] `npm --prefix frontend run test:unit` — now `node --test tests/unit/*.test.ts && vitest run`: Node runner 27 tests, 27 pass; Vitest 8 files, 89 tests, 89 pass (importer 8, renderer 18, rules 9, modeling 13, shapes 11, useGraphState 7, module verification 22, boundary 1).
- [x] `cd frontend && npx playwright test structure-canvas` — 18 passed (4 layout tests of ticket 01; its fifth, the drag test that read the old SVG's transform, was replaced by drag tests in the new spec; 14 in `structure-canvas.spec.ts`), Chromium, mocked API. This is the structure path of `npm --prefix frontend run test:browser`; the other specs were not run.
- [x] `python3 scripts/check-compose-ports.py` — OK (no Compose change).
- [x] `docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T frontend npm install` — ran; `diagram-js`, `tiny-svg`, `jsdom` and `vitest` are present in the running container's `node_modules` volume (container Node 22.23.4).
- Not run: a manual check in a real browser against the real backend (the product owner tests by hand); Firefox and Safari; backend tests (no backend change).

## AI review

- [x] Review run on the ticket's diff — a read-through by the implementing agent after the tests passed (no separate reviewer tool or skill was run). Findings: (1) `canvas.removeConnection` left connections in the shapes' `incoming`/`outgoing`: fixed with `detach` in the importer, covered by a test. (2) The library reparents a dragged shape into the shape under the pointer: fixed with `GraphMoveTarget`. (3) Clicking the selected element toggled the selection off, unlike the old canvas: fixed in `ShadowCanvas`, covered by the delete test. (4) A second edit could carry a stale event version: edits are queued and the event is reloaded after each. (5) A refusal could undo a later gesture: rollback only runs when the command stack is unchanged since the edit (tested); otherwise the next load restores the server's state. (6) Accepted: the drag preview clones the node's `role` and `aria-label`, so a screen reader sees the node twice while dragging; connection arrowheads are polygons, not SVG markers.

## Documentation effects

- [ ] No documentation effect
- [ ] Update `docs/user/`
- [ ] Update `docs/admin/`
- [ ] Update `docs/operations/` or `docs/runbooks/`
- [ ] Update `docs/gdpr/` or `docs/legal/`
- [x] Update architecture or ADR — `docs/adr/0051-draw-the-structure-canvas-with-diagram-js.md` (new Verification section), `docs/architecture/stack.md`, `docs/architecture/project-layout.md`, `docs/architecture/frontend.md` (Structure canvas section), `.scratch/structure-canvas/technical-design.md`
- [x] Update `docs/design/` — `docs/design/ui-foundation.md` (canvas theming through the tokens, selection and change marks, click on the selected element, no fixed viewBox); also `docs/agents/testing.md` (Vitest row)
- [ ] Update `CONTEXT.md`
- [ ] Update `.env.example`

Record exact updated file paths and explain every “No documentation effect” choice.

Not updated, with reasons: `docs/user/` (no change a person sees beyond shapes and colours; the user guide is ticket 09), `docs/admin/`, `docs/operations/`, `docs/gdpr/`, `docs/legal/` (no storage key added; `shadow.canvas.panels` is unchanged, so `backend/legal/browser-storage.json` needs nothing), `CONTEXT.md` (Canvas and View are ticket 09), `.env.example` (no variable). C4 and DBML unaffected (no service, data or integration change).

## Blocked by

- 01

## Completion record

Finished: the Structure canvas is drawn by diagram-js through the Shadow domain layer, with the behaviour of the old SVG canvas and shapes, colours, line styles, arrowheads and labels from the metamodel. All acceptance criteria are met.

**Module verification (installed `diagram-js` 15.28.1, MIT; dependencies `didi` 11.0.1, `min-dom` 5.3.0, `min-dash`, `tiny-svg` 4.1.4, `inherits-browser`, `object-refs`, `path-intersection`; types ship with the package, so no local declaration file; `diagram-js.css` at `assets/`).** Every module the design expects exists and loads (test `frontend/tests/canvas/modules.test.ts`, each module and all together): `selection`, `move`, `lasso-tool`, `create`, `connect`, `context-pad`, `palette`, `rules`, `modeling`, `align-elements`, `distribute-elements`, `grid-snapping`, `snapping`, `keyboard`, `editor-actions`, `overlays`, `outline`, `hand-tool` (under `lib/features/`), the command stack (`lib/command`), and `movecanvas` and `zoomscroll` (under `lib/navigation/`, not `features`). Extra: `keyboard-move`, `search`, `hover-tooltip`, `auto-place`, `space-tool`. Minimap: package `diagram-js-minimap` 5.6.0 (MIT), not installed yet (ticket 07). Missing and who builds it: auto layout (`elkjs`, ticket 07), PNG/SVG export (ticket 07), the React panels and type list (04), node list and live region (09), hover popover content (06, on `overlays`), undo/redo UI and server-synchronised inverse writes (05). Surprises recorded in ADR-0051: `modeling` must be included by users of `distribute-elements` and `grid-snapping`; `keyboard` binds to the diagram's own `<svg>` (`bindTo` removed); no module registers `connectionDocking` or a layouter, Shadow supplies them. The decision stands.

**What was built.** `frontend/src/models/canvas/`: `useGraphState.ts`, `graph-types.ts`, `ShadowCanvas.tsx` (one `Diagram`, `ResizeObserver`, imperative handle with `applyEdit`), `diagram/` with `GraphImporter` (diffed in-place updates), `GraphRenderer`, `GraphLayouter` (straight lines cropped at the shape outline), `GraphRules`, `GraphModeling` (`applyEdit`, `EditRefused`, 400 ms move batching), `shapes.ts` and `index.ts` (module `shadowGraphModule`). `ModelCanvas.tsx` lost the hand-written SVG and keeps the panels, layout, notices and connect flow of ticket 01; its edits go through `canvas.applyEdit`, whose sender writes through the existing client functions. `client.ts` gained `loadLineState` (state route with `?event_id=`, plus the `added`/`updated`/`removed` ids); `loadGraph` uses it. `theme.css` imports diagram-js.css into the `components` layer and maps its `--bio-*` variables to Shadow's tokens.

**Differences from the ticket text.** (1) The ticket's source `{kind:"version", versionId}` is obsolete since versions were retired; the source is `{organizationId, modelId, lineId, eventId?}` (state route and `?event_id=`), and the hook also returns the event, which edits need. (2) Create, move, delete and connect use diagram-js's own commands; only `shadow.node.update` is ours. (3) The test runner: the repo had Node's test runner only, so Vitest and jsdom were added as dev dependencies for the DOM-bound canvas tests (`tests/canvas/`, part of `test:unit`). (4) Parallel-connection offset is not done (ticket 06).

**Not verified.** Nothing was run in a real browser against the real backend; the Playwright specs use a mocked API and only Chromium. Default diagram-js zoom and scroll (wheel and background drag) are present but were not checked and are not part of the acceptance. No dark theme exists yet, so the token mapping was not seen in one. The PNG/SVG, minimap and layout items are later tickets.

**For tickets 03 to 08.** Add library modules in `diagram/index.ts` `__depends__` (include `modeling`); call `diagram.get("canvas")` through the handle you add to `ShadowCanvasHandle` (only `applyEdit` exists). Every edit must go through `GraphModeling.applyEdit` (extend `GraphEdit` in `graph-types.ts` and the sender switch in `ModelCanvas.tsx`; ticket 08 swaps only the sender's target). The command stack is cleared after every graph load, so undo (05) must live with that or change it, and mouse moves are not undoable-aware yet (the `elements.move` hook in `GraphModeling` collects them; `revert` of a move does not save). A node needs `role="button"`, `tabindex` and `aria-label` on its group (done in the renderer). Rules refuse everything when read-only. The renderer reads `businessObject` (`NodeObject`, `ConnectionObject`); new visual states go there, never colour alone.

## Comments

- The hook is the seam to the timeline: `.scratch/model-timeline/` swaps its source to a state after an event.
- This ticket brings in the library (ADR-0051); tickets 03 to 09 build on it and wait for it.
