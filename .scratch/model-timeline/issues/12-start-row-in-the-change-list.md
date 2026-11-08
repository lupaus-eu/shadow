# Ticket 12: start row in the change list

Status: implemented

## Goal

A Scenario's change list starts with a fixed, clickable "Start" row that shows the state the Scenario starts from, read-only.

## Implementation

- The change list of a Scenario gets a fixed first row "Start" (Finnish: "Lähtötilanne") with the text "Starts from: <parent line>, after the change <title> (<date>)" and a link to the parent line and that change.
- Selecting the row (URL `?change=start`, keyboard reachable, `aria-current` when selected) draws the parent line's state after the branch change, read through the parent's state route (`?change_id=<branch change>`); no new backend route. The canvas is read-only with the caption "Start state, not editable. Change it in the parent line." and drawing, undo, delete and the editor are disabled.
- The Base line has no Start row. Opening a Scenario without a `?change=` still shows its present state as today.
- Finnish and English texts; the row is not a Change (no date edit, no delete, not counted in the change count); marks of added, changed and removed elements are not shown for it.

## Acceptance criteria

- [x] A Scenario's list starts with the Start row, naming the parent line, the branch change and its date; the Base line has none.
- [x] Selecting it shows the parent's state after the branch change, read-only, and back to the first Change restores editing.
- [x] The row works by keyboard and is announced; the caption states why it is read-only.
- [x] The row follows a corrected history (the branch change moves or the parent changes before it): the state shown is the current Start.

## Testing

- [x] Backend/API test — not applicable (frontend only)
- [x] Frontend/UI test — unit tests for the row model and read-only rules
- [x] Browser/E2E validation — Playwright with a mocked API: Start row of a Scenario, select, read-only caption, back to a Change
- [x] Migration/integration/architecture validation — typecheck, build, unit tests

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build && npm --prefix frontend run test:unit` — passed (29 vitest files, 320 tests; node tests 0 failures; build ok).
- [x] `cd frontend && npx playwright test structure-canvas model-timeline` — passed, 97 tests (mocked API, headless Chromium; no real sign-in, no real backend).

## AI review

- [x] Review run on the ticket's diff — self-review of the diff by the implementing agent (no separate review tool). Found and fixed: the first Playwright draft looked links up by their `title`, but a link's accessible name is its text (kept: the visible text names the link); `Alert` does not forward `data-testid`, so the caption is wrapped in a div. Accepted: the canvas view (pan/zoom) key follows the drawn line, so the Start state starts with a fresh view.

## Documentation effects

- [x] Update `docs/design/` — `docs/design/ui-foundation.md` (Start row paragraph)
- [x] Update `docs/user/` — `docs/user/README.md` (Start row). Also `docs/architecture/frontend.md` (Start row paragraph). No other documentation effect: no service boundary, data model, env or permission change; the vocabulary sweep is ticket 03.

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 09

## Completion record

- Done: `StartInfo`, `startInfo`, `startShown`, `startRequest`, `startReadOnly` and a `start` row in `changeRows` (`frontend/src/models/timeline.ts`); texts in `timeline-messages.ts` (en, fi); the Start row in `timeline/ChangePanel.tsx` (button with `aria-current`, links to the parent line and Change); `ModelShell.tsx` reads the parent's changes and gives `start`/`startShown` to the outlet and disables "New scenario from here", "New change" and edit buttons while shown; `ModelCanvas.tsx` loads the parent's state at the branch change, read-only, without marks, with a `role="status"` caption. Tests: `frontend/tests/canvas/timeline.test.ts` (row model), `frontend/tests/browser/model-timeline.spec.ts` (Scenario Start row, select by keyboard, caption, no drawing, back to a Change; Base line has none).
- All four acceptance criteria met in the mocked-API checks. Not verified: a real backend, a real browser sign-in or manual use (the product owner tests by hand); the corrected-history criterion is covered at the row-model level (the row reads the current branch change and parent changes) and not by a browser test with a moved branch change; Finnish texts are not browser-checked; the pre-existing nodes-list "node" panel and keyboard shortcuts rely on the same read-only flag as earlier past-change views.

## Comments

- Decision: ADR-0052. Build it after the rename tickets of `.scratch/tech-change-terminology/` (ticket 02) so that it uses the new vocabulary; the status script cannot express that cross-feature order.
