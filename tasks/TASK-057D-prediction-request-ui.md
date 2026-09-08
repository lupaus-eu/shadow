# TASK-057D Prediction Request UI

## Source Plan

Approved plan: "Background Prediction Requests", accepted for task creation on
2026-09-07. The selected progress experience is state-only in the current
organisation's Predictions tab, with prompt Stop and Remove from queue actions.

Dependencies: [TASK-057A](TASK-057A-background-predictions-architecture.md) and
the API implemented by
[TASK-057C](TASK-057C-durable-prediction-requests-worker.md).
Task creation does not implement the UI.

## Goal

Let users submit long-running predictions without blocking the workspace, see
which named requests are queued or calculating, and stop/remove active work.
Keep completed prediction comparison behavior intact.

## Requirements

- Extend `frontend/src/api/predictions.ts` with typed request states/summaries
  and list/detail/cancel clients matching TASK-057C. Update creation to consume
  `202 Accepted` and a request summary instead of a completed version.
- Retain the existing generation form, preflight, validation, and input payload.
  On acceptance, display the queued request immediately and release the form
  for another submission. Do not automatically resubmit after network failure.
- Add a "Prediction requests" section to `PredictionsTab.tsx`, showing the
  prediction name on every row. Separate active work from recent history;
  show all active requests and the returned 50 most recently finished requests.
  Order queued requests oldest first.
- Map backend states to clear labels: `queued` -> "Queued", `running` ->
  "Calculating prediction values", `cancelling` -> "Stopping", `completed`
  -> "Completed", `cancelled` -> "Cancelled", and `failed` -> "Failed".
- Provide "Remove from queue" for queued requests and "Stop" for running
  requests, including other users' requests under existing business permissions.
  Explain that stopping discards calculated output. Disable cancellation while
  its mutation is pending and while state is stopping.
- Render the server-returned state after cancellation, including completion
  winning a race. Keep terminal records in history; removing from the queue
  does not delete a saved prediction or request history.
- Poll lightweight summaries every two seconds while the Predictions tab is
  visible, even with no active requests so other users' submissions appear.
  Avoid overlapping polls. Refresh immediately when the tab becomes visible;
  abort requests/timers on unmount, organisation change, or authentication loss.
- Guard against stale asynchronous responses crossing organisation changes or
  overwriting a newer mutation result. Browser fetch cancellation must not
  invoke server-side prediction cancellation.
- On completion, refresh the saved-version library and fetch the new result
  once needed. Auto-select completed requests submitted from this tab while
  preserving comparison/filter selections. Other users' results become
  available without automatically changing chart selections.
- Keep polling errors separate from calculation failures. Preserve last-known
  request state with a refresh-error message, recover on successful polling,
  and show safe per-request failure reasons. Accepted work survives navigation,
  logout, and reload; restore the queue from the backend when returning.
- Reuse existing styles and accessible status/action patterns. Expose loading,
  empty, submission, cancellation, and refresh errors without blocking saved
  result comparison. Avoid repetitive live-region announcements on every poll.

## Acceptance Criteria

- [ ] Each active request is identifiable by prediction name and its actual
      queued, calculating, or stopping state.
- [ ] Submission returns control to the form while the request continues, and
      another uniquely named prediction can be submitted.
- [ ] Queued removal and running Stop call the correct API and display the
      returned lifecycle, with disabled duplicate actions while stopping.
- [ ] Completed, cancelled, and failed requests appear in recent history;
      failed/cancelled names can be used for a new submission.
- [ ] Polling discovers other users' requests while idle and stops/refreshes
      correctly across visibility, organisation, route, and auth changes.
- [ ] Poll failures retain last-known state and are not shown as model failures.
- [ ] Completion refreshes saved results without resetting chart comparisons;
      current-tab submissions are selected when they complete.
- [ ] Reloading or leaving the tab cannot cancel accepted backend work.
- [ ] State-only progress contains no percentages, work counters, or estimates.
- [ ] Analysis routing and saved prediction chart behavior remain unchanged;
      no dependency or backend change is introduced.

## Out Of Scope

- Backend queue/worker implementation, auth changes, or schema changes.
- Global workspace indicators, percentage or model/metric-level progress,
  scheduling, priorities, automatic retries, and automatic resubmission.
- Deleting saved versions, pruning request history, new charting features,
  dependencies, or deployment wiring.

## Implementation Notes

Read `AGENTS.md`, `ARCHITECTURE.md`, ADR-012,
`docs/domains/FORECASTING.md`, `docs/TESTING.md`, and TASK-057C's implemented
schemas before changing clients. Reuse `authenticatedFetch`, existing
Predictions tests, styles, abort handling, and comparison controls. Poll request
summaries rather than repeatedly downloading all saved prediction points.

## Testing

Required: frontend client/component tests, manual browser verification, lint,
and build. Use fake timers and controllable responses for polling and races.

Cover all states, creation's new response, queue order, recent history,
cancel/completion races, repeated clicks, request failures, stale responses,
visibility/route/org changes, auth loss, idle polling, and completion-driven
version refresh/selection. Retain existing preflight/chart regression coverage.

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Manually exercise named queued/running requests, Stop, Remove from queue,
failed/cancelled name reuse, reload/return, and comparison of completed versions.
Full worker/container browser QA is completed in TASK-057E.

Not applicable: backend tests, migrations, typecheck, and image checks because
this task changes frontend behavior only.

## Documentation

Update relevant Predictions usage guidance and `docs/TESTING.md` with the new
submission/status/cancellation flow. Keep API/domain architecture aligned with
ADR-012; no new domain or data-model decision belongs in this task.

## Notes For AI Agent

- Implement only when requested and TASK-057C's contract exists.
- Keep the confirmed state-only progress scope and add no dependencies.
- Record eventual Step 13 reviews under `docs/ai-reviews/TASK-057D/` and run
  `python3 scripts/ai_review_records.py validate` from the repository root.
- Report changed files, checks, and any manual verification still outstanding.
