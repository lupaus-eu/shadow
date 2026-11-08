# Ticket 09: Accessibility, texts, browser test and documentation

Status: implemented

## Goal

The canvas is usable without a mouse, in Finnish and English, covered by a browser test, and documented.

## Implementation

- `a11y/NodeList.tsx` (done in the existing `TypePanel`, which already was the focusable list; `canvas/a11y.ts` holds the helpers): focusable list of every node with name, type, description and connections as the text alternative; selecting a row selects and centres the node; live region for selection, connect mode and refusals; focus returns to the canvas after dialogs.
- Finnish and English texts for every new label, message and shortcut hint (`models/messages.ts`).
- Playwright keyboard-only path and a mobile viewport path; contrast and reduced-motion check in both themes.
- Documentation: `docs/design/` canvas guidance, `docs/user/README.md`, `docs/architecture/stack.md`, `project-layout.md`, `frontend.md`, `CONTEXT.md` (Canvas, View).
- Not done: new features.

## Acceptance criteria

- [x] Every mouse action has a keyboard route; nodes are reachable by Tab/arrows and announced with name and type. (Mocked-API Playwright, Chromium; limits in `docs/design/ui-foundation.md`: a drag by an arbitrary distance is arrow steps, moving a connection end is the From/To selects, selecting a connection is the node's Connections list.)
- [x] Selection, connect mode and refusals are announced; marks never rely on colour alone. (Announcements: Playwright reads the live region; marks: `+`, `~`, `−` glyphs, legend text, "Planned" label, outlines, from tickets 02, 04 and 08 and audited here.)
- [x] Every user-visible string exists in both languages; no raw server text reaches the page. (`tests/canvas/messages.test.ts` for the model, canvas and timeline message files; grep of the canvas error paths: only structured fields (`cause`, `reason`, `limit`) are read, never `message` or server text.)
- [ ] No animation under `prefers-reduced-motion`; contrast passes in light and dark themes. Reduced motion: done (global rule, Playwright with emulated media). Contrast: passes in the light theme (`tests/canvas/contrast.test.ts`); **no dark theme exists**, so the dark half cannot be met or tested yet; the test fails when a dark rule appears so it is not forgotten. Left unticked for that reason.
- [x] The browser test covers zoom, fit, add, connect, filter, undo and export, plus the keyboard path. (Existing specs `structure-canvas-navigation`, `-types`, `-drawing`, `-tools` cover zoom, fit, add, connect, filter, undo and export; the new `structure-canvas-accessibility.spec.ts` the keyboard path.)

## Testing

- [x] Backend/API test — not applicable (frontend only); `backend/tests/test_browser_storage.py` stays green (3 passed; `i18n.ts` only gained try/catch, no new key).
- [x] Frontend/UI test — Vitest `messages.test.ts` (every key in both locales, no empty or copied text, live-region and text-alternative helpers), `contrast.test.ts`; node:test for blocked storage in `i18n.test.ts`.
- [x] Browser/E2E validation — Playwright `structure-canvas-accessibility.spec.ts`: keyboard-only path, node list, refusal and connect-mode announcements, reduced motion, 375 px path with an axe pass on the open sheet, axe on the page with a selected node. Mocked API, Chromium only.
- [x] Migration/integration/architecture validation — typecheck and build pass; no Compose file touched, so `check-compose-ports.py` is unaffected (not run).

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build && npm --prefix frontend run test:unit` — pass; node:test 28 of 28, Vitest 29 files, 315 tests (31 of them in the two new files).
- [x] `cd frontend && npx playwright test` (the whole browser suite) — 95 passed (89 before this ticket plus 6 new). One earlier run had 1 failure, `structure-canvas-drawing.spec.ts` "a new node opens for naming ..." (an unguarded `boundingBox()` right after the redraw); it failed 5 of 16 runs on the code without this ticket's source changes too, so it was a pre-existing flake; the test now polls and passed 16 of 16, then in the full run. The known flaky test noted in the brief did not fail.
- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_browser_storage.py` — 3 passed.
- Not run: `python3 scripts/check-compose-ports.py` (no Compose change).

## AI review

- [x] Self-review of the diff (no independent review tool was run). Findings: (1) the connections rows added to the node list made `getByRole("button", {name: "Support"})` ambiguous in the types spec and the rows' names longer; the types spec helper now matches the start of the name. (2) A node being named on a phone was under the open sheet: the sheet now closes when a node is added. (3) A deleted node left keyboard focus on `body`: `restoreFocus` returns it to the canvas. (4) A connection could be selected only with the pointer: the details panel lists the node's connections as buttons. (5) The unguarded measurement in a drawing spec (pre-existing flake) now polls. Accepted: a collapsed type group is hidden from assistive technology until opened (the expand button is announced); the live region repeats "Selected ..." after a reload re-selects the same element only when the selection really changed (deduplicated by ids); the popover is still not hoverable (ticket 06's accepted decision).

## Documentation effects

- [ ] No documentation effect
- [x] Update `docs/user/` — `docs/user/README.md` (section was complete; added the keyboard route, text alternative and announcements)
- [ ] Update `docs/admin/`
- [ ] Update `docs/operations/` or `docs/runbooks/`
- [ ] Update `docs/gdpr/` or `docs/legal/`
- [x] Update architecture or ADR — `docs/architecture/stack.md`, `docs/architecture/project-layout.md`, `docs/architecture/frontend.md` (no ADR: no durable decision beyond ADR-0051)
- [x] Update `docs/design/` — `docs/design/ui-foundation.md` (keyboard map, accessibility section, contrast table and test, reduced motion, phones), `docs/design/README.md` (pointer)
- [x] Update `CONTEXT.md` — Canvas and View were already defined by model-timeline ticket 11 and verified; no change
- [ ] Update `.env.example`

Record exact updated file paths and explain every “No documentation effect” choice.

## Blocked by

- 01
- 02
- 03
- 04
- 05
- 06
- 07

## Completion record

- Done: the type list is the text alternative (it gained a spoken type and connections line; no second `NodeList` component, to avoid a duplicate); a node's connections are buttons in the details panel (the keyboard route to selecting a connection); the live region now also announces selection and connect mode on, source chosen and off; `ShadowCanvas` has `focus()` and a key-summary description, and focus returns to the canvas after the delete confirmation and the connection-type dialog; the phone sheet closes when a node is added; `i18n.ts` tolerates blocked storage; a global reduced-motion rule; message-completeness, contrast and helper unit tests; a Playwright spec (keyboard path, refusals, node list, reduced motion, 375 px, axe); the drawing spec's shared mock moved to `tests/browser/canvas-mock-api.ts`; documentation as listed.
- Criteria met: all except the dark-theme half of the reduced-motion and contrast criterion (no dark theme exists; light contrast passes and is tested).
- Not verified: a real screen reader (NVDA, VoiceOver, JAWS), a real touch device or phone, other browsers, real sign-in and the real backend, the production build behind Caddy, and hand testing by the product owner. All browser evidence is Chromium against a mocked API; reduced motion is Playwright's media emulation. Contrast is computed from the tokens, not measured on rendered pixels; a node's own type colour is not checked.
- Follow-ups worth a ticket: a dark theme (then extend `contrast.test.ts`); keyboard dragging of a connection end (bendpoints do not exist); a hoverable popover (WCAG 1.4.13); a hand run with a screen reader.

## Comments

- Ticket 08 (time control) documents its own design effects and may land before or after this ticket.
