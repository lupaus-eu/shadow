# Ticket 03: Navigation (zoom, fit, pan, keyboard)

Status: implemented

## Goal

A person can zoom, pan and fit the canvas with the mouse, touch, toolbar and keyboard, and the view survives saves.

## Implementation

- Configure the diagram-js `moveCanvas` (background drag), `zoomScroll` (wheel and pinch around the pointer, 10 % to 400 %), `hand-tool` (space + drag) and `keyboard` modules; we write only `CanvasToolbar` (zoom in/out, percentage readout, Fit, 100 %, reading and setting `canvas.viewbox()`/`canvas.zoom()`).
- `useCanvasView`: view kept across saves and reloads of the same version; reset on leaving the tab or switching version; automatic fit after the first load only.
- `keymap.ts`: `+` `-` `0` `F`, arrows (pan or move selection), `Esc`, ignored in text fields; no other shortcuts yet.
- Reduced motion: no animated centring or zoom.
- Not done: minimap, other shortcuts (later tickets add their own keys to the map).

## Acceptance criteria

- [x] Zoom is clamped to 10–400 % and the readout matches the zoom.
- [x] Fit shows the whole graph with padding; 100 % restores scale 1 around the viewport centre.
- [x] After moving a node or saving a rename the view does not jump or reset.
- [x] Shortcuts work when the canvas has focus and not when a text field does.
- [x] With `prefers-reduced-motion` nothing animates.

## Testing

- [x] Backend/API test — not applicable (frontend only).
- [x] Frontend/UI test — vitest for `useCanvasView` (limits, keep and reset) and `keymap.ts`: `tests/canvas/view.test.ts`, `useCanvasView.test.tsx`, `keymap.test.ts`, `navigation.test.ts` (the diagram wiring in jsdom).
- [x] Browser/E2E validation — Playwright (mocked API, Chromium only): `tests/browser/structure-canvas-navigation.spec.ts`: wheel zoom and its limits, toolbar zoom, Fit, 100 %, background and space-drag pan, touch pan and pinch (Chromium touch events), keyboard zoom, arrows, Esc, view kept after a move save and a rename, reduced motion, Finnish labels.
- [x] Migration/integration/architecture validation — typecheck and build.

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build` — both pass (build: only the existing chunk-size notice).
- [x] `npm --prefix frontend run test:unit` — node tests 27 pass, 0 fail; vitest 12 files, 129 tests pass (40 of them are new: view 19, useCanvasView 3, keymap 9, navigation 9).
- [x] `cd frontend && npx playwright test structure-canvas` — 31 passed (all specs in `tests/browser/`, Chromium, mocked API, run on the local Vite server; 13 of them are the new navigation spec). `npx playwright test` (whole directory) — 31 passed. Not run: `backend/tests/test_browser_storage.py` (no backend environment on this machine, and no storage key was added or changed; `frontend/tests/unit/browser-storage.test.ts` passes inside `test:unit`).

## AI review

- [x] Review run on the ticket's diff — self-review by the implementing agent, no review tool or skill run. Findings and outcome: (1) quick toolbar clicks computed each step from the half-animated view, so steps did not add up (Playwright showed 92 % instead of 80 %); fixed with `GraphNavigation.base()` which continues from the animation's end. (2) The library's hand tool pans on pointer movement alone and ends at the first press, so a real "space + drag" did nothing; Space is now handled by `GraphNavigation`/`GraphKeys` (ADR-0051 note 8). (3) `zoomScroll` stops at 20 % and scrolls on a plain wheel; its wheel handler is replaced (ADR-0051 note 7). (4) Found and fixed an existing bug the Finnish texts exposed: `ModelShell`'s nested `Outlet` context replaced the organization context, so every model page read `locale` as undefined and showed English; `ModelShell` now passes the organization context on. (5) Accepted: the view is read with `canvas.viewbox()` (cached, recomputed after each change) per event; no performance measurement (product owner decision).

## Documentation effects

- [ ] No documentation effect
- [ ] Update `docs/user/` — no effect yet: the user guide for the canvas is ticket 09.
- [ ] Update `docs/admin/` — no effect.
- [ ] Update `docs/operations/` or `docs/runbooks/` — no effect.
- [ ] Update `docs/gdpr/` or `docs/legal/` — no effect: the view is held in memory only and no browser-storage key was added (`backend/legal/browser-storage.json` and `storage.*.md` unchanged).
- [x] Update architecture or ADR — `docs/architecture/frontend.md`, `docs/architecture/project-layout.md`, `docs/adr/0051-draw-the-structure-canvas-with-diagram-js.md` (library behaviour notes 7 to 10).
- [x] Update `docs/design/` — `docs/design/ui-foundation.md` (canvas toolbar, zoom and view rules, keyboard map).
- [ ] Update `CONTEXT.md` — no effect: View is already defined; Canvas and View wording is ticket 09.
- [ ] Update `.env.example` — no effect.

Record exact updated file paths and explain every “No documentation effect” choice.

## Blocked by

- 02

## Completion record

- Finished: all five criteria met. New: `canvas/view.ts` (limits, fit, zoom-around, pinch, tween, `ViewMemory`), `canvas/useCanvasView.ts`, `canvas/keymap.ts`, `canvas/CanvasToolbar.tsx`, `canvas/diagram/GraphNavigation.ts` and `GraphKeys.ts` (modules `keyboard` and `hand-tool` joined `shadowGraphModule`); `ShadowCanvas` fits the first load of a line (or restores the remembered view after a remount), renders the toolbar, registers Esc and exposes `fit`, `zoomTo`, `zoomIn`, `zoomOut`, `actualSize`, `centreOn`, `getView`, `registerKey`; `ModelCanvas` passes the view memory (key organization|model|line), the toolbar texts and `onEscape` (leaves connect mode). The ticket's "version" is the line (`?line=`) since versions were retired. The known gap of ticket 01 (a node dragged out of view) is closed: Fit and pan reach it (Playwright test).
- Differences from the ticket text: (1) the library's `zoomScroll` wheel handler is replaced (10 % lower limit, plain wheel zooms around the pointer; ctrl + wheel is the trackpad pinch); (2) space + drag is Shadow's own, the library hand tool is only loaded; (3) touch pan and pinch added (the library has none); (4) Fit never zooms in past 100 %; (5) Esc cancels connect mode first and only then clears the selection; (6) the arrow step is 10 px at the current zoom for a selection (Shift 50 px) and 50 px (Shift 200 px) for panning; (7) the `ModelShell` locale fix above; (8) `tests/canvas/setup.ts` gained `scale` and `translate` on the fake SVG matrix.
- Not verified: nothing was run in a real browser against the real backend or signed in; touch was only exercised with Chromium's synthetic touch events (no real device, no Safari or Firefox); the Mac trackpad pinch (wheel with ctrl) is covered only by the arithmetic test; `backend/tests/test_browser_storage.py` was not run (no storage change).
- For the next canvas tickets: add keys with `ShadowCanvasHandle.registerKey({ id, keys, run })` (newest binding is tried first; return false to fall through; chords with Ctrl, Cmd or Alt never reach the keymap, so undo and redo in ticket 05 register on the library's `keyboard` service, priority above 1100) and list them in the keyboard map of `docs/design/ui-foundation.md`. Centre-and-zoom on a node (ticket 04) is `handle.centreOn(point)` plus `handle.zoomTo(scale)`; both animate unless reduced motion. All view changes must go through `GraphNavigation.setView` so the clamp and the animation rules hold. The view is remembered by `ShadowCanvas` after its first graph is placed; a remount of the same line restores it. `canvas.viewbox.changed` fires on every pan and drag, so keep handlers cheap. Space is taken by Shadow (grab); on a focused node it selects.

## Comments

- Keyboard map in the technical design lists all later keys; each ticket adds its own.
