# TASK-065 Frontend Async Test Races

## Source Plan

Developer-approved plan (2026-10-08) after the frontend Customers route test
in `App.test.tsx` failed once in a full `pnpm test` run during TASK-064 and
then passed repeatedly. The developer approved fixing the observed flaky test
and four latent tests with the same cause, and decided not to keep the
forced-delay check described below as permanent tooling.

Amended 2026-10-08 during implementation: running the whole suite under the
forced delay found seven further tests with the same cause. The developer
extended this task to fix them as well.

## Goal

Frontend component tests must not depend on whether React has finished its
follow-up work by the time a `findBy*` or `waitFor` call returns. Each affected test waits
for the specific element, text or request its next assertion depends on, so it
passes regardless of scheduling order.

### Cause

- A `findBy*` query returns as soon as its element is in the DOM. React Testing
  Library then waits only one `setTimeout(0)` before the test continues.
- React runs passive effects (`useEffect`) and some follow-up renders in
  separate tasks, which its scheduler starts with `setImmediate` in Node.
- Node does not guarantee whether `setTimeout(0)` or `setImmediate` runs
  first, so under load a test can occasionally continue before React's
  follow-up work has run.

In the observed failure, the customer list row and the Addresses and Contacts
panels render together, but the panels request their data from effects. The
test waited for the row and then counted customer requests, and occasionally
found only the list request (`expected 1 to be greater than or equal to 3` at
`App.test.tsx:918`). Delaying React's scheduler tasks by 5 ms reproduces this
every time.

## Requirements

### Observed Flaky Test

`frontend/src/App.test.tsx`, "renders the application-wide Customers route
without workspace context in its API":

- After the "Acme Customer" row, wait with `waitFor` until the three expected
  request paths have been called: the customer list, the selected customer's
  addresses and its contacts. This replaces the `>= 3` request count.
- Then wait for both child panels' empty states, "No addresses available." and
  "No contacts available.". The panels start with no items and loading off, so
  these empty states can render before the load effects start; they alone do
  not show that the requests were made.
- Keep the existing check that no customer request path contains the
  organisation identifier.

### Latent Tests With The Same Cause

These tests pass in normal runs but fail when React's scheduler tasks are
delayed, because each one queries synchronously right after a `findBy*` whose
element appears before the data being queried:

| Test file | Test | Waits for | Then queries synchronously |
| --- | --- | --- | --- |
| `frontend/src/features/customers/CustomersTab.test.tsx` | sorts and selects customers, then loads both child collections in parallel | the customer list container (line 37) | its row buttons (line 38) |
| `frontend/src/features/customers/CustomersTab.test.tsx` | does not allow child refreshes and mutations to overlap | the Create contact form (line 230) | the "Save contact" button (line 235) |
| `frontend/src/features/summary/SummaryTab.test.tsx` | starts all scenario requests concurrently and renders the shared timeline | the "Future plan" heading (line 225) | the timeline summary text (line 227) |
| `frontend/src/features/users/UsersTab.test.tsx` | loads, sorts, counts, and selects active users | the active user list container (line 71) | its row buttons (line 72) |

Tests added by the 2026-10-08 amendment. These wait for an element or a mock
call, then query UI that appears only after React renders the response:

| Test file | Test | Waits for | Then queries synchronously |
| --- | --- | --- | --- |
| `frontend/src/App.test.tsx` | confirms event deletion with yes and no buttons | the DELETE request (`waitFor`) | that the "Kickoff" row is removed and "Launch event" is selected |
| `frontend/src/features/users/UsersTab.test.tsx` | cancels deletion and then soft-deletes with a predictable fallback | the delete call (`waitFor`) | that the "ada" row is removed |
| `frontend/src/features/users/UsersTab.test.tsx` | confirms and reports application-session revocation | the revoke call (`waitFor`) | the success status message |
| `frontend/src/features/metrics/MetricsTab.test.tsx` | fetches timeseries for the selected scenario and renders typed cells | the "Metrics" heading | the timeseries count and typed cells |
| `frontend/src/features/metrics/MetricsTab.test.tsx` | filters manual and derived metrics by kind and time unit | the "Filter by" group | the "Average revenue" row |
| `frontend/src/features/predictions/PredictionsTab.test.tsx` | shows active and recent request states, and keeps the server cancellation result | the cancel call (`waitFor`) | the "Completed" state of the cancelled row |
| `frontend/src/features/predictions/PredictionsTab.test.tsx` | uses the visible default level, validates it, and invalidates stale preflight | the first preflight call (`waitFor`) | that "Queue prediction" is enabled |

- In each test, wait with `findBy*` or `waitFor` for the specific element or
  text that the next assertion depends on, for example the first row instead
  of the list container.
- Keep every existing assertion and its intent. A synchronous check that
  documents a deliberate state (for example that something is disabled while
  a request is pending) must still check that state, only after the
  prerequisite UI is present.

### General

- Test-only changes. No application code changes.
- No tests removed, skipped or weakened, and no longer global timeouts or
  retries (`--retry`) used to hide the race.
- No new dependencies and no new test tooling or scripts.

## Acceptance Criteria

- [ ] The Customers route test waits for the three expected request paths
      instead of counting requests, then for both child panels' empty states.
- [ ] Each of the eleven latent tests (four original, seven from the
      amendment) waits for the element, text or state its next assertion
      depends on.
- [ ] All twelve tests pass with React's scheduler tasks delayed by 5, 20 and
      50 ms, using the temporary verification below.
- [ ] The normal frontend suite, lint and build pass.
- [ ] No application code, dependency, test tooling or configuration is
      changed, and no test is removed, skipped or weakened.

## Out Of Scope

- Keeping the forced-delay check as a script, configuration, setup file or CI
  step. The developer decided not to keep it.
- Making the whole suite pass under the forced delay. Tests that use fake
  timers never run the delayed callbacks and time out under it, so their
  failures are not meaningful.
- Other flaky tests not listed here. Report any further test with this cause
  instead of fixing it outside the scope.
- `frontend/src/App.test.tsx`, "hides Users and redirects its route for
  consultants". It already waits for the redirected "Scenarios" heading, but
  the redirect takes about 0.5 s normally and exceeds the default 1 s `findBy*`
  timeout at a 50-100 ms forced delay. That is a timeout margin, not this race;
  report it instead of changing it. For the same reason, App shell tests such
  as the Customers route test can time out at 100 ms before their first
  element appears, so 100 ms is not an acceptance delay.
- Changing React, React Testing Library or Vitest configuration.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/TESTING.md
```

- The Customers route mocks are in `mockSchattenApi` in
  `frontend/src/App.test.tsx`; the customer with id 201 has empty contact and
  address lists.
- The empty-state texts come from `ContactsPanel` and `AddressesPanel` in
  `frontend/src/features/customers/CustomersTab.tsx`.
- A fix for the observed test was tried in a temporary copy during planning:
  waiting for both empty states and checking the three paths passed with a
  5 ms delay and normally. During implementation it still failed at 50 ms,
  because the empty states render before the load effects start, so the test
  waits for the request paths themselves.

### Temporary Forced-Delay Verification

Use this only to verify the twelve tests and delete it before committing:

1. Create a temporary setup file that replaces `globalThis.setImmediate` with
   a wrapper that runs the callback a configurable number of milliseconds
   later through `setTimeout` (for example from a `TMP_DELAY_MS` environment
   variable, default 5). Some races reproduce only at certain delays: role
   queries over the large App DOM can take longer than 5 ms, so the delayed
   work catches up. For example, the Customers route test failed here only at
   50 ms and above.
2. Create a temporary Vitest config with the jsdom environment that loads that
   setup file before `./src/test/setup.ts`. The override must load first,
   because the existing setup imports React Testing Library, which loads
   React's scheduler and captures `setImmediate`.
3. Run the twelve tests with `pnpm exec vitest run --config <temporary config>`
   and their test files at 5, 20 and 50 ms. Before the fix each one fails at
   one or more of these delays (the Customers route test at the request count);
   after the fix all twelve pass at every delay.
4. Delete both temporary files and confirm `git status` shows no leftovers.

## Testing

Required:

- [ ] Frontend tests: the twelve updated tests pass in the normal suite and
      under the temporary forced delay.
- [ ] Lint
- [ ] Build

Not applicable:

- [ ] Backend tests and manual browser verification. Reason: test-only
      frontend change; no application behaviour changes.

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
cd ..
python3 scripts/ai_review_records.py validate
```

## Documentation

- `docs/TESTING.md`: add a short rule for frontend component tests: after a
  `findBy*` query, wait for the specific element, text or request that the
  next assertion depends on, and do not count requests made by child effects
  right after waiting for a parent element, or check UI that a mutation
  response updates right after waiting for the mutation call. Briefly describe
  the TASK-065 coverage.

## Notes For AI Agent

- Use the branch `fix/TASK-065-frontend-async-test-races`.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-065/`.
- Report all changed files, every verification command run, and the result of
  the temporary forced-delay check before and after the fix.
- Run the whole suite once under the forced delay and report any remaining
  failure that is not caused by fake timers.
