# Ticket 04: Type list, filter and search

Status: implemented

## Goal

A left panel lists nodes grouped by type with visibility, collapse, add and search, and clicking a node centres the canvas on it.

## Implementation

- `TypePanel.tsx`: groups by node type with colour tag and count, sorted by type then name; per-type visibility checkbox, Select all, Deselect all, per-type collapse (types without nodes start collapsed), "+" per type that adds a node of that type (placement as today until ticket 05), search box (`/`).
- Hidden types hide their nodes and every connection touching them (a diagram-js marker class); search dims non-matching nodes, Enter centres on the first match.
- Clicking a row selects the node, centres and zooms to it (animation off with reduced motion); rows of hidden types are disabled.
- Collapse state kept in `shadow.canvas.typeCollapse` per model.
- Not done: the node list as a text alternative beyond what this panel provides (ticket 09).

## Acceptance criteria

- [x] Counts match the nodes; hiding a type removes its nodes and touching connections from the canvas and restoring brings them back.
- [x] Select all and Deselect all work; a hidden type's rows are disabled.
- [x] Search by name highlights matches and dims the rest; clearing restores; Enter centres.
- [x] Row click selects and centres the node.
- [x] Collapse state survives reload; works with storage blocked.
- [x] The "+" button adds a node of the chosen type (read-only Organization: not shown).

## Testing

- [x] Backend/API test — `backend/tests/test_browser_storage.py` for the new key; otherwise not applicable.
- [x] Frontend/UI test — vitest for grouping, sorting, filter and search helpers.
- [x] Browser/E2E validation — Playwright: hide a type, search, row click centres, collapse and reload.
- [x] Migration/integration/architecture validation — typecheck, build, `frontend/tests/unit/browser-storage.test.ts`.

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build` — passed (tsc clean, vite build ok).
- [x] `npm --prefix frontend run test:unit` — passed: node tests 27/27 (incl. `browser-storage.test.ts`), vitest 143/143 in 13 files (14 new in `tests/canvas/typelist.test.ts`: grouping, sorting, counts, visibility, search, collapse persistence with blocked/malformed storage, `GraphFilter` markers, Fit ignoring hidden nodes, focus).
- [x] `cd frontend && npx playwright test structure-canvas` — 42 passed (11 new in `tests/browser/structure-canvas-types.spec.ts`, mocked API, Chromium only; the three older spec files still pass).
- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_browser_storage.py` — 3 passed.

Not run: a real browser by hand, real sign-in, Firefox/Safari, touch, a screen reader (the product owner tests the UI by hand).

## AI review

- [x] Review run on the ticket's diff — self-review by the implementing agent (no separate review tool). Findings: (1) diagram-js writes an inline `display: block` on every element group, so the `shadow-hidden` class needed `display: none !important`; fixed and covered by Playwright. (2) A key registered through the canvas handle from a parent effect is lost when React StrictMode recreates the diagram; `ShadowCanvas` now takes `keyBindings` and registers them with each diagram it creates. (3) `browser-storage.test.ts` key regex was lower-case only and read `typeCollapse` as `shadow.canvas.type`; the regex now allows upper case. (4) The older layout spec's `Add` button name became ambiguous with the new "Add a X node" buttons; made `exact`. Accepted: hidden types and the search are in memory only (not remembered across reload); "+" names the node "<Type> <n>" and does not select it.

## Documentation effects

- [ ] No documentation effect (not chosen: docs changed, see below)
- [ ] Update `docs/user/`
- [ ] Update `docs/admin/`
- [ ] Update `docs/operations/` or `docs/runbooks/`
- [x] Update `docs/gdpr/` or `docs/legal/` — `browser-storage.json` and `storage.*.md` for `shadow.canvas.typeCollapse`
- [ ] Update architecture or ADR
- [x] Update `docs/design/` — `docs/design/ui-foundation.md` (type panel, hide/dim/search/click rules, `/` key, storage key)
- [ ] Update `CONTEXT.md`
- [ ] Update `.env.example`

Record exact updated file paths and explain every “No documentation effect” choice.

Updated: `docs/design/ui-foundation.md`, `backend/legal/browser-storage.json`, `backend/legal/storage.en.md`, `backend/legal/storage.fi.md`. No effect on `docs/user/` (the user guide for the canvas is written in ticket 09), admin, operations, architecture (no service boundary, data model or integration change), `CONTEXT.md` or `.env.example`.

## Blocked by

- 02
- 03

## Completion record

- Implemented `TypePanel.tsx` (replaces the ticket 01 node list, also the node list of the phone sheet), `canvas/type-list.ts` (grouping, sorting, visibility, search, placement helpers), `canvas/type-collapse.ts` (`shadow.canvas.typeCollapse`, per model, guarded storage), `diagram/GraphFilter.ts` (markers `shadow-hidden`, `shadow-match`, `shadow-dim`), `GraphNavigation.focus`, the handle method `centreOnNode(id, {zoom})` and the `filter` and `keyBindings` props of `ShadowCanvas`. All six acceptance criteria and all four testing items are met; finnish and english texts added in `models/messages.ts`.
- Not verified: real browser by hand, other browsers, touch, screen reader, reduced-motion in a real browser (the animation switch is the existing `tweenView` option, covered by unit tests of ticket 03).
- Effects recorded under Documentation effects.

## Comments

- None.
