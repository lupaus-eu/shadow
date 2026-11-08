# Ticket 09: frontend change list and scenario picker

Status: implemented

## Goal

Replace the version controls with a line picker, a change list and the change editor.

## Implementation

- `ModelShell`: line picker, new Scenario from the shown change, rename, delete, adopt; change list with date, title, Planned label and colour, and a Now divider; selecting a change redraws the state.
- Change editor with ordered edits, date change, delete, and refusal messages for every cause in Finnish and English; the form keeps input; scenario start-changed notice with acknowledge.
- All tabs follow the selected line; Types says it is shared.

## Acceptance criteria

- [x] Planned changes are marked by colour and text; the Now divider sits between the last happened and first planned change.
- [x] A refused change shows change, element, reason and what to do, with no raw server text.
- [x] A new Scenario can be started from a past change and appears in the picker under its parent.

## Testing

- [x] Backend/API test — not applicable (backend done)
- [x] Frontend/UI test — message builder, list grouping and marks
- [x] Browser/E2E validation — create Scenario from a past change, plan a change, break and fix a chain
- [x] Migration/integration/architecture validation — `npm run typecheck`, `build`, `test:unit`

## Ajetut tarkistukset

- [x] `npm --prefix frontend run typecheck && npm --prefix frontend run build && npm --prefix frontend run test:unit` — passed (26 vitest files, 275 tests, 18 of them new in `tests/canvas/timeline.test.ts`; node tests passed).
- [x] `cd frontend && npx playwright test structure-canvas model-timeline` — passed, 84 tests (5 new in `tests/browser/model-timeline.spec.ts`: Planned marks and Now divider, choosing an event redraws read-only, Scenario from a past event under its parent, refused date change keeps input, axe). Mocked API only; no real sign-in and no real-browser run against the backend.

## AI review

- [x] Self-review of the diff (no separate review tool run). Findings: (1) an open event column or strip squeezed the canvas and broke the pixel-exact canvas specs, so the list is a column opened with the "Events (n)" button (open by itself from 1600 px); (2) the canvas finds the last event itself unless an earlier event is chosen, which keeps the existing save path and timing; (3) `reloadEvents` sets state only when the list changed. Accepted: the event editor does not edit changes (the canvas does), and Base line writing by a Member is not blocked on the canvas beyond the 403 message.

## Documentation effects

- [x] Update `docs/design/`
- [ ] Update `CONTEXT.md` — left to ticket 11 (documentation and vocabulary); no term changed here

Record exact updated file paths and explain every "No documentation effect"
choice.

## Blocked by

- 04
- 06
- 07

## Completion record

- Done: line picker (Base line first, Scenarios under their parent) with kind label and colour; New scenario from the shown event (dialog keeps the name); rename, delete, adopt with role-based buttons and readable refusals (403 handled); event list with Planned label and amber dashed frame, Now divider and branch badges; `?event=` selection redraws through `useGraphState` and keeps the canvas read-only unless the last event is shown; event editor (title, date, note, ordered changes with names, delete, new event with today suggested); `chainBrokenMessage` for all nine causes, `branch_point`, limits, stale and 403 in Finnish and English; start-changed notice with acknowledge; Types tab says types are shared; tab links carry line and event.
- Criteria: all three met. Documentation: `docs/design/README.md` (new section), `docs/architecture/frontend.md`. No backend change.
- Not verified: a real browser against the real backend and sign-in (the product owner tests by hand); the Finnish texts were read, not reviewed by a native speaker; the phone layout was not exercised.
- For structure-canvas ticket 08: the outlet gives `event` (shown event or last), `eventIsLast`, `events`, `reloadEvents`, `role`, `canWriteLine`. `ModelCanvas` computes `writable = subscription && eventIsLast && canWriteLine` and passes `eventId` to `useGraphState` only for an earlier event; to draw into the shown event, use `event` as the edit target instead of the last one, drop the `eventIsLast` condition and keep the notice. Edits call `reloadEvents()` afterwards. The event column is in `ModelShell` (not inside the canvas area).

## Comments

- Design: `../technical-design.md`; rules: `../domain-model.md`; ADR-0048, ADR-0049, ADR-0050.
