# Ticket 07: Snap, align, auto layout, minimap and export

Status: implemented

## Goal

A person can tidy a graph with snap, align and auto layout, find their way with a minimap, and export the view.

## Implementation

- Configure the built-in `grid-snapping` (toggle `shadow.canvas.snap`), `align-elements` and `distribute-elements` (align left, centre, top, middle; distribute with equal gaps) with toolbar buttons; each is one command-stack entry and therefore one undo step.
- Auto layout (layered, `elkjs`, lazy loaded; confirm its licence before adding) on request only, applied as one `elements.move` command; nothing rearranges on its own.
- Minimap with `diagram-js-minimap` (package name verified in ticket 02): shows all nodes and the viewport; click and drag move the view; collapsible.
- Export: SVG by serialising the canvas SVG with inlined styles, PNG by drawing that SVG onto a canvas at scale 2; hidden types stay hidden (our code).
- Not done: other layouts, saving several layouts.

## Acceptance criteria

- [x] With snap on, moved nodes land on the grid; the choice survives reload.
- [x] Align and distribute produce the expected coordinates for a selection of three or more nodes.
- [x] Auto layout arranges a 50-node graph without overlaps of node boxes and can be undone in one step.
- [x] The minimap matches the canvas and moves the view when clicked.
- [x] PNG and SVG files download and show the current visibility.

## Testing

- [x] Backend/API test — `backend/tests/test_browser_storage.py` for `shadow.canvas.snap`; otherwise not applicable.
- [x] Frontend/UI test — vitest for the snap, align and distribute configuration, the position-batch helper and the SVG serialiser (`tests/canvas/tools.test.ts`, `arrange.test.ts`, `layout.test.ts`, `export.test.ts`, `minimap.test.ts`).
- [x] Browser/E2E validation — Playwright: align, auto layout and undo, minimap click, PNG download (`tests/browser/structure-canvas-tools.spec.ts`, mocked API, Playwright's Chromium; no real sign-in).
- [x] Migration/integration/architecture validation — typecheck, build, lazy chunks not in the initial bundle.

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build` — passed. Bundle (`dist/assets`, minified, gzip): initial `index-*.js` 934.99 kB (287.15 kB) before and 963.90 kB (296.50 kB) after (+28.9 kB, +9.4 kB: align, grid-snapping, the menu, icons, our tools); `theme.css` 64.08 kB (12.77 kB) before, 66.41 kB (13.09 kB) after (the minimap stylesheet and our rules). New separate chunks: `minimap-*.js` 11.97 kB (3.94 kB) and `elk.bundled-*.js` 1,474.41 kB (448.47 kB). `dist/index.html` loads only `index-*.js`; the main bundle has no static import of either chunk (`grep` of `elk.bundled` and `minimap-` finds only the two `import()` references), and the Playwright tests assert that no request for the minimap code is made before the minimap is opened and none for `elkjs` before Arrange is pressed.
- [x] `npm --prefix frontend run test:unit` — passed: Node runner 27 tests (including `browser-storage.test.ts`), Vitest 25 files, 257 tests (47 new: `tools.test.ts` 17, `arrange.test.ts` 9, `layout.test.ts` 8, `export.test.ts` 9, `minimap.test.ts` 4). `elkjs` runs in Vitest (jsdom), so the 50-node no-overlap property is tested with the real layout, twice (pure, and on a diagram).
- [x] `npm --prefix frontend run test:browser` (layout and export path) — run as `cd frontend && npx playwright test structure-canvas`: 80 passed on three of four runs, with one test failing once on each of two runs (`structure-canvas-drawing.spec.ts:397`, "an undo is refused ... another session changed the element": the test changes the mocked server state right after an optimistic rename, which races the rename's own write; it passed 12 of 12 repeated alone and the code under it is not touched by this ticket). The new `structure-canvas-tools.spec.ts` has 9 tests (snap and reload, align and distribute with enabling and undo, 50-node layout and undo, minimap click and drag and collapse, SVG and PNG download with hidden type, keyboard path, axe scan with the minimap open, phone width, PNG under the production image policy) and passed every run. Mocked API, Playwright's Chromium, no real sign-in and no other browser.
- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_browser_storage.py` — 3 passed.
- [x] `docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T frontend npm install` — run after changing `package.json` (the dev stack was running).
- Not run: a real browser other than Chromium, a real sign-in, Safari/Firefox PNG export, the production build behind the real Caddy (the image policy was checked with a policy header added to the page in Playwright, not with Caddy itself).

## AI review

- [x] Review run on the ticket's diff — a self-review by the implementing agent (no separate reviewer tool or skill was run). It found, and the tests then confirmed and fixed: (1) `GraphLayouter` threw when the *target* node of a connection moved (the library passes `connectionStart: false` and `false ?? centre` stayed `false`); this was an existing bug that drag, align and layout all hit, fixed with a regression test; (2) the minimap's injector adapter dropped `get`'s `strict` argument, which would have thrown on opening (caught by the first minimap test); (3) a duplicate `xmlns` made the exported SVG invalid XML (caught by the export test); (4) the library's `distribute-elements` leaves gaps a few units unequal with four or more nodes (measured), replaced by `canvas/arrange.ts`; (5) the minimap at the top right covered the toolbar and, at the bottom right, covers a corner of the drawing and broke 11 existing tests that click the background corner, so it starts closed and loads its code on first opening; (6) the production Content-Security-Policy allows `data:` images but not `blob:`, so the PNG loads the SVG as a `data:` URL (a Playwright test with the policy added fails with a blob URL and passes with the data URL). Accepted as is: arrow-key moves are not snapped; auto layout also places nodes of hidden types; the first and last nodes of a distribute stay put and a distribute with no free space does nothing silently (the button stays enabled).

## Documentation effects

- [ ] No documentation effect — not applicable, every item below that applies is ticked
- [ ] Update `docs/user/`
- [ ] Update `docs/admin/`
- [ ] Update `docs/operations/` or `docs/runbooks/`
- [x] Update `docs/gdpr/` or `docs/legal/` — `backend/legal/browser-storage.json`, `backend/legal/storage.en.md` and `backend/legal/storage.fi.md` for `shadow.canvas.snap`
- [x] Update architecture or ADR — `docs/architecture/stack.md` (`diagram-js-minimap`, `elkjs` and its licence), `docs/architecture/project-layout.md`, `docs/architecture/frontend.md`, `docs/adr/0051-draw-the-structure-canvas-with-diagram-js.md` (licence decision and findings 19-24), `.scratch/structure-canvas/technical-design.md`
- [x] Update `docs/design/` — `docs/design/ui-foundation.md` (toolbar, minimap, export)
- [ ] Update `CONTEXT.md`
- [ ] Update `.env.example`

Record exact updated file paths and explain every “No documentation effect” choice.

Not updated, with reasons: `docs/user/` (user guidance for the canvas is ticket 09), `docs/admin/` and `docs/operations/` (no operator-facing change), `CONTEXT.md` (no new domain term; Canvas and View are ticket 09), `.env.example` (no variable), LikeC4 and DBML (no service boundary or data change).

## Blocked by

- 05

## Completion record

- Finished: grid snapping (toggle, `shadow.canvas.snap` per person, registered in the legal list and both notices), align (left, centre, top, middle) and distribute (horizontal, vertical, equal gaps) with toolbar buttons enabled at two and three selected nodes, auto layout with `elkjs` (layered, lazy chunk, on request, then Fit), the minimap (`diagram-js-minimap` 5.6.0, lazy chunk, closed to begin with, `aria-hidden`, toolbar toggle), and SVG and PNG export through a toolbar menu with sanitised `model-line` file names, with Finnish and English texts, announcements and a keyboard path. Each tool is one command, one positions write and one journal entry.
- `elkjs` licence: it is `EPL-2.0 OR GPL-3.0-or-later`; taken under EPL-2.0, unmodified from npm, in a lazy chunk; reasoning recorded in ADR-0051 and `stack.md`. Acceptable, so work continued.
- Criteria met: all five, with the evidence in `## Ajetut tarkistukset` (unit, jsdom with real layout, and mocked-API Chromium tests).
- Differences from the ticket text, recorded in ADR-0051 and the technical design: distribute is our own arithmetic (the library's leaves unequal gaps); the layout is one Shadow command that moves each node (one `elements.move` cannot give different distances); the minimap starts closed and is attached after first opening; its stylesheet is in `theme.css` (the build allows one stylesheet); the PNG uses a `data:` URL because of the production CSP; an existing `GraphLayouter` bug on moving a connection's target node was fixed.
- Not verified: other browsers, a real sign-in, the production build behind Caddy, and look and feel by a person (the product owner tests the UI by hand); the existing flaky test noted above.
- Documentation effects: see the list above.

## Comments

- Performance is not gated; see the technical design.
- For later tickets: the toolbar now wraps onto more rows (ticket 08 adds time control; consider its own bar). Ctrl/Cmd keys go on `GraphKeys`, single keys through `keyBindings`; none were added here. Anything that moves nodes should go through `GraphModeling.arrange` (several nodes, one write) or `moveElements` plus a flush. The `viewbox` of the library is reached through `GraphNavigation.setView` everywhere, the minimap included.
