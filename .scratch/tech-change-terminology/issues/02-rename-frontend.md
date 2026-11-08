# Ticket 02: rename frontend

Status: implemented

## Goal

Rename event to Change and change to Edit in the web interface and its tests.

## Implementation

- Types in `client.ts`, components, message files (Finnish: muutos, suunniteltu muutos, muutoslista, muokkaus; English: Change, planned change, change list, Edit), the URL parameter `?change=`, outlet fields, canvas edit calls, Playwright mocks and tests.
- The message completeness test keeps both languages complete; no stale wording in marks, legends, announcements and refusal messages.
- Not done: the Start row (model-timeline ticket 12), documents (ticket 03).

## Acceptance criteria

- [x] No stale use of the old words in `frontend/src` and `frontend/tests` except DOM events and the like.
- [x] Typecheck, build, unit tests and the Playwright specs pass against the renamed API shapes.
- [x] Every refusal message uses the new vocabulary in both languages.

## Testing

- [ ] Backend/API test — not applicable
- [x] Frontend/UI test — renamed tests, message completeness
- [x] Browser/E2E validation — Playwright specs with the renamed mocks
- [x] Migration/integration/architecture validation — `npm --prefix frontend run typecheck && npm --prefix frontend run build && npm --prefix frontend run test:unit`

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build && npm --prefix frontend run test:unit` — passed: typecheck clean, build ok, 29 node unit tests (incl. the new `tests/unit/change-terminology.test.ts` guard) and 315 vitest tests in 29 files.
- [x] `cd frontend && npx playwright test` (whole browser suite, mocked API, headless Chromium) — passed: 95 passed. An earlier run had one failure in `structure-canvas-drawing.spec.ts` (undo recreating a node), which passed on a rerun alone and in two full runs; it is the known flaky one. No real sign-in or real-backend browser run was done.
- [x] `cd backend && TEST_DATABASE_URL=postgresql+psycopg://shadow@localhost:55432/shadow_platform_test ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_browser_storage.py` — passed: 3 passed.
- [x] `grep -rniE event frontend/src frontend/tests` minus DOM and library events — only the allowed leftovers below remain.

## AI review

- [x] Self-review of the diff (no separate tool): the rename was scripted in two passes (step `change` to `edit` by exact tokens, then `event` to `change` only in the timeline files and specs, with DOM and diagram-js names protected). Findings fixed by hand: a first run also touched `ShadowCanvas.tsx` (DOM handlers) and rewrote DOM `(event) =>` handlers in the change editor, both reverted; the key collision `changeDate` (old step label) against the renamed event date label (now `dateLabel`); local variables named `change` in `ModelCanvas.tsx` and patch parameters `changes` in `client.ts` renamed (`graphEdit`, `onMediaChange`, `fields`); the state-marker field `changes` of `LineState` renamed `marks` so it cannot be mistaken for the Change list; a mock response `changes: [` that must be `edits: [` (found by the guard); Finnish grammar of the plural count and the adopt refusal written by hand.

## Documentation effects

- [x] Update `docs/design/` — no documentation effect in this ticket: no test or reference depends on `docs/design/ui-foundation.md` or `docs/architecture/frontend.md`, so their vocabulary is swept in ticket 03.

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 01

## Completion record

- Done: the web interface and its tests use Change and Edit: types (`LineChange`, `ChangeEdit`, `LineState.marks`), client functions and routes (`/lines/{line}/changes`, `/changes/{change}`, `?change_id=`, `branch_change_id`, `edits[]`, `edit_count`, `edit_counts`, `change_count`, `latest_change`), components (`ChangePanel.tsx`, `ChangeEditor.tsx`), the URL parameter `?change=`, outlet fields (`change`, `changeIsLast`, `changes`, `reloadChanges`), hint codes and fields, `limit: "changes_per_line"` text, English and Finnish texts (Change, planned change, change list, Edit; muutos, suunniteltu muutos, muutoslista, muokkaus), the Now divider, refusal and state captions, the Activity page (new `change` area; the `event` area is labelled as older entries so both `event.*` and `change.*` rows are reachable), Playwright mocks and tests. New guard test `frontend/tests/unit/change-terminology.test.ts`. All three criteria met.
- Allowed leftovers of "event" in `frontend/`: DOM and library events (`KeyboardEvent`, `addEventListener`, `preventDefault`, diagram-js `eventBus`, `waitForEvent`, handler parameters named `event`), `loadAuditEvents` and the `audit-events` route (Audit Event), the platform support console (`SupportEvent`, `/support-access/.../events`), and legacy Yearclock texts in `src/i18n.ts` (Events, Series, summary of upcoming Events, Support Access scope) and `.yc-print-events` in `theme.css`; those belong to the old calendar product, not this rename.
- For the Start row (model-timeline ticket 12): use `ChangePanel.tsx` (the list rows are `ChangeRow` kinds `change` and `now` in `timeline.ts`), `shownChange`, the outlet field `change`, `timelineMessages` keys with `change`/`edits`, `?change=`; the state of the Start row is read through the parent's state route with `?change_id=` of `branch_change_id`. Documents (`docs/design/ui-foundation.md`, `docs/architecture/frontend.md`) still use the old words until ticket 03.

## Comments

- Design: `../technical-design.md`; decision: ADR-0052.
