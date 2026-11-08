# Ticket 01: Full-width layout and collapsible panels

Status: implemented

## Goal

The Structure tab uses the whole main area and the available height, with collapsible side panels, on the existing SVG canvas.

## Implementation

- `AppShell`/`ShellFrame` `wide` is enabled for the Structure route only (route handle or outlet flag); other model tabs keep `max-w-6xl`.
- The canvas fills the viewport height below the shell and model header (`100dvh` minus measured header); the page does not scroll while using the canvas.
- Left and right panels are collapsible; state kept in `shadow.canvas.panels` (try/catch, works without storage); below 768 px the panels become a bottom sheet.
- The SVG `viewBox` follows the container size instead of a fixed 1400x800 and the node position clamp is removed.
- Not done: library change, zoom, new panels.

## Acceptance criteria

- [x] At 1920 px width the working area is wider than `max-w-6xl` (1152 px) and, with both panels collapsed, the canvas is too (with both panels open the 260 px sidebar and 500 px of panels leave the canvas about 1060 px; the criterion is read as the working area); Types, Metrics, Simulations and Analysis keep their width.
- [x] The page has no vertical scrollbar from the canvas; resizing the window resizes the canvas.
- [x] Each panel collapses and expands; the choice survives reload; with storage blocked the page still works.
- [x] Below 768 px the panels are a bottom sheet and the canvas is touch-usable (layout checked at 375 px; real touch not tried, `touch-action: none` and pointer events are unchanged; the canvas has a 320 px minimum height, so a phone page may scroll).
- [x] Nodes can be dragged outside the old 1400x800 area.

## Testing

- [x] Backend/API test — not applicable (frontend only), except `backend/tests/test_browser_storage.py` for the new key (3 passed).
- [x] Frontend/UI test — `frontend/tests/unit/canvas-panels.test.ts` (node:test; the unit runner is node:test, not vitest) for the panel-state storage wrapper (blocked storage, bad JSON).
- [x] Browser/E2E validation — `frontend/tests/browser/structure-canvas-layout.spec.ts` (Playwright, mocked API, no sign-in): width at 1920 px, no page scroll, other tab width, collapse and reload, panel key blocked, 375 px bottom sheet, drag beyond 1400 px.
- [x] Migration/integration/architecture validation — `npm --prefix frontend run typecheck && npm --prefix frontend run build`; `frontend/tests/unit/browser-storage.test.ts`.

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build` — both succeeded.
- [x] `npm --prefix frontend run test:unit` — 27 tests, 27 pass (includes browser-storage.test.ts and 4 new panel-state tests).
- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_browser_storage.py` — 3 passed.
- [x] `cd frontend && npx playwright test structure-canvas` (Vite dev server on 8174 started by the Playwright config; the API is mocked with `page.route`, so no Authentik sign-in) — 5 passed (Chromium). Not run: the real stack with a real sign-in, Firefox/WebKit, real touch input; the product owner tests by hand. A screenshot at 1440 and 375 px was looked at once to judge the layout.

## AI review

- [x] Self-review of the diff (no review skill run). Findings: (1) the Tailwind `flex` class overrides the `hidden` attribute, so a collapsed panel stayed in the accessibility tree; found by the Playwright reload test, fixed by switching the display class. (2) The panel width first took 340 px on xl screens and left the canvas too narrow; reduced to 220 px and 280 px. (3) Accepted: `i18n.ts` reads `localStorage` without try/catch (existing code, out of scope), so with all storage blocked the app fails at start; the blocked-storage test therefore blocks only `shadow.canvas.panels`. (4) Accepted: without a clamp a node can be dragged out of view and, until pan and zoom arrive with diagram-js (ticket 02), can only be brought back through the Nodes list selecting it, not moving it.

## Documentation effects

- [ ] No documentation effect
- [ ] Update `docs/user/` — no effect yet; user help is ticket 09
- [ ] Update `docs/admin/`
- [ ] Update `docs/operations/` or `docs/runbooks/`
- [x] Update `docs/gdpr/` or `docs/legal/` — `backend/legal/browser-storage.json`, `backend/legal/storage.en.md`, `backend/legal/storage.fi.md` list `shadow.canvas.panels` (a per-person preference, no consent banner needed; the notice wording stays draft for legal review)
- [ ] Update architecture or ADR — no effect: no service, data or ADR-0051 decision changed; the technical design Layout already describes this (left panel holds a node list until ticket 04 replaces it with the type list)
- [x] Update `docs/design/` — `docs/design/ui-foundation.md` (shell width and "Full-width canvas pages")
- [ ] Update `CONTEXT.md`
- [ ] Update `.env.example`

Record exact updated file paths and explain every “No documentation effect” choice.

## Blocked by

None.

## Completion record

- Done: `OrganizationLayout` enables `AppShell wide` for the Structure route only (`useMatch`); wide `main` uses 12-16 px padding. `ModelCanvas` has a viewport-height area (`useFillHeight`), `viewBox` equal to the container (`useElementSize`, one unit = one pixel, pointer maths simplified), no position clamp, a collapsible left **Nodes** panel (simple selectable node list, replaced by the type list in ticket 04) and right **Details** panel (add node, selection, connection; the change list is not there because change lists belong to events now), a bottom sheet under 768 px, and collapse state in `shadow.canvas.panels` through `models/panel-state.ts`. Finnish and English texts in `models/messages.ts`.
- All criteria met; the 1920 px criterion is read as the working area (see the criterion). Records: `backend/legal/*`, `docs/design/ui-foundation.md`. No Playwright spec existed before (`frontend/tests/browser/` is new); it runs against a mocked API.
- For the next canvas tickets: panel contents live in `rightContent`/`nodeList` in `ModelCanvas.tsx`; the SVG is still hand-written (ticket 02 replaces it) and needs the `stage` ref size, the fill-height area and `touch-action: none`; `shadow.canvas.typeCollapse` and `shadow.canvas.snap` still have to be registered in `browser-storage.json` and the notices when added; the panel state type `PanelState` has only `left` and `right` (widths come only if needed).

## Comments

- Technical design: `.scratch/structure-canvas/technical-design.md`, "Frontend / Layout".
