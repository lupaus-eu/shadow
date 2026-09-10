# TASK-058 Prediction Request List UI Follow-up

## Source Plan

Approved plan: "Prediction Request List UI Follow-up", accepted for task
creation on 2026-09-10. This is a new follow-up to
[TASK-057D](TASK-057D-prediction-request-ui.md), so it uses the next free task
number rather than extending the original TASK-057A--E implementation plan.
Task creation does not implement the UI.

Dependency: [TASK-057D](TASK-057D-prediction-request-ui.md).

## Goal

Make prediction request history easier to scan, expose useful lifecycle timing
on every request card, and keep users informed when requests submitted from the
current tab finish. Preserve visibility and control of all active work.

## Requirements

- Keep every queued, running, and cancelling request visible in "Active work"
  and preserve its existing cancellation action and ordering.
- Initially show only the three most recently finished requests in "Recent
  history". When more than three terminal records were returned, add one
  accessible `Show more` / `Show less` button that reveals or hides the
  remainder of the backend's newest-first history, up to its existing limit of
  50. Use `aria-expanded` and `aria-controls`, retain expansion across polling,
  and reset it when the organisation changes.
- Show the following labelled metadata on every `article.prediction-request`
  card: queued timestamp, processing-start timestamp, finish timestamp, queue
  duration, and processing duration.
- Format timestamps in the browser's local timezone to minute precision and
  retain the machine-readable source value on a semantic `time` element.
  Represent missing lifecycle stages explicitly as `Not started` or `Not
  finished` rather than displaying a misleading time.
- Derive queue duration from submission to start; for a terminal request that
  never started, derive it from submission to finish; and while still queued,
  derive it from submission to the current time. Derive processing duration
  from start to finish or, while running/cancelling, from start to the current
  time. Show `Not started` if no processing start exists.
- Display durations as completed local-time-independent elapsed minutes: use
  `<1 min` below one minute, compact minute/hour/day units thereafter, and
  prevent negative output if timestamps or the browser clock are inconsistent.
  Ongoing durations may refresh with the existing two-second request polling;
  do not introduce another timer.
- Replace the single submission message with one notice for each prediction
  request successfully submitted during the current mounted tab and
  organisation context. Keep notices ordered newest submission first and do
  not create notices for requests merely discovered through polling.
- Initially show `Prediction request “{name}” was accepted and queued.` for each
  locally submitted request. Keep that text while the request is running or
  cancelling, then replace it with exactly one terminal message:
  `Prediction request “{name}” completed.`, `Prediction request “{name}” was
  cancelled.`, or `Prediction request “{name}” failed.` Append the backend's safe
  failure reason to a failed message when one is available.
- Render queued, completed, and cancelled notices as informational status
  messages. Render failed notices as danger alerts. Update notice state only on
  a real lifecycle transition so unchanged polls do not cause repetitive live-
  region announcements.
- Give every notice an accessible individual dismiss action. A dismissed
  notice must not reappear after later polls or lifecycle changes. Clear all
  notices on organisation change or component unmount; notices are not
  persisted across navigation, reload, or login sessions.
- Update notices from list and cancellation responses. Because the list caps
  terminal history at 50, use the existing request-detail client for any
  locally submitted, still-tracked non-terminal request that disappears from a
  poll response, and feed a resolved completion through the existing saved-
  version refresh/selection behavior. Keep polling non-overlapping and retain
  the existing stale-organisation, mutation-race, visibility, abort, and
  authentication guards.
- Reuse existing alert, dismiss-control, button, card, responsive, and
  accessibility patterns. Add no dependency and make no backend, database, API
  schema, prediction DTO, queue-lifecycle, or saved-version behavior change.

## Acceptance Criteria

- [ ] All active requests remain visible and actionable while Recent history
      shows only its newest three records by default.
- [ ] History with more than three records can be fully expanded and collapsed
      using an accessible button; polling does not collapse it, and an
      organisation change restores the default.
- [ ] Every request state displays truthful local queued/start/finish times and
      queue/processing durations, including ongoing, never-started, and
      sub-minute cases.
- [ ] Several requests submitted from the current tab produce separate,
      newest-first notices that independently transition to completed,
      cancelled, or failed messages.
- [ ] Failed notices include only the safe server-provided reason, terminal
      changes are not re-announced on unchanged polls, and other users'
      requests do not create submission notices.
- [ ] Each notice can be dismissed without reappearing, and all notice state is
      cleared when the organisation or mounted tab context changes.
- [ ] A tracked request omitted from the capped list is resolved through its
      detail endpoint, including completion-driven saved-version refresh and
      current-tab auto-selection.
- [ ] Existing request polling, cancellation races, comparison selections,
      responsive layout, and saved prediction behavior remain intact.
- [ ] Frontend lint, tests, and production build pass with no dependency or
      backend change.

## Out Of Scope

- Backend endpoints, response fields, request-history limits, database schema,
  worker behavior, queue ordering, cancellation semantics, or authentication.
- Hiding active requests, pagination, server-side filtering, request deletion,
  persistent or cross-device notifications, global workspace notifications,
  browser notifications, or automatic notice expiry.
- New progress percentages, estimates, work counters, chart behavior, or saved
  prediction actions.

## Implementation Notes

Read `AGENTS.md`, `ARCHITECTURE.md`, ADR-012,
`docs/domains/FORECASTING.md`, `docs/TESTING.md`, and TASK-057D before changing
the frontend. The primary implementation surfaces are
`frontend/src/features/predictions/PredictionsTab.tsx`, its component tests, and
the prediction-request styles in `frontend/src/styles/components.css`.

The existing `PredictionRequestSummaryDto` already contains `submittedTime`,
`startTime`, and `finishTime`; do not change it. Reuse
`fetchPredictionRequest` for the capped-list fallback. Keep notification state
separate from `submittedRequestIdsRef` so dismissing a notice does not prevent a
completed locally submitted version from being selected.

Prefer small pure timestamp/duration formatting helpers that can be tested with
a fixed clock. Reuse or adapt the existing Metrics notice dismissal pattern
without coupling Predictions to a feature-private component. Preserve the
server's terminal-history order instead of introducing another ordering source.

## Testing

Required: frontend component/helper tests, manual browser verification, lint,
and build.

Automated coverage must include:

- zero through three history records without a disclosure and four or more
  records through expand/collapse, active visibility, poll stability, and
  organisation reset;
- local minute-precision timestamps and queue/processing durations for queued,
  running, cancelling, completed, failed, and cancelled-before-start requests;
- multiple submission notices, terminal transitions from polling and
  cancellation responses, safe failure reasons, accessible roles, individual
  dismissal, context clearing, and exclusion of other users' requests;
- a tracked request missing from the capped list and resolved through detail,
  including completion refresh/selection; and
- regressions for non-overlapping polling, stale responses, cancellation races,
  saved-version comparison preservation, and responsive request-card actions.

Use fake timers, a fixed system time, and controllable API responses for timing,
polling, and race cases. Avoid assertions that depend on the test runner's host
timezone; derive expected local timestamp text with the same explicit
minute-precision `Intl.DateTimeFormat` options or isolate the formatter.

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Manually verify `Show more` / `Show less`, narrow-screen card layout, browser-
local timestamp display, ongoing durations, multiple notices, terminal updates,
and keyboard/screen-reader labels for disclosure and dismissal.

Not applicable: backend tests, PostgreSQL integration tests, migrations,
backend typecheck, image checks, Compose checks, or deployment verification
because this task changes frontend presentation and local UI state only.

## Documentation

Update `docs/domains/FORECASTING.md` and the Prediction Request UI section of
`docs/TESTING.md` with collapsed recent history, lifecycle timing, and current-
context submission notices. No ADR, architecture diagram, domain diagram,
workflow diagram, or data documentation change is required because the API,
lifecycle, ownership, and architecture remain unchanged.

## Notes For AI Agent

- Implement only when explicitly requested, and keep the change frontend-only.
- Add no dependencies and do not change the prediction request API contract.
- Preserve all active-request actions and TASK-057D's polling/race guarantees.
- Record eventual Step 13 reviews under `docs/ai-reviews/TASK-058/` and run
  `python3 scripts/ai_review_records.py validate` from the repository root.
- Report changed files, automated checks, and any manual verification still
  outstanding.
