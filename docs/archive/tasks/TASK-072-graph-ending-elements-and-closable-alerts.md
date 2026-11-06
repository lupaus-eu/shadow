# TASK-072 Graph Ending Elements And Closable Alerts

## Source Plan

Developer-approved plan (2026-10-30) for two frontend improvements:

1. A node created in org state 1 (2026-01-01) and removed in org state 2
   (2026-02-01) is still shown in the state 2 graph, and is correctly gone
   in state 3 (2026-03-01). The state 2 graph does not say that the node ends
   there. The graph should show that such an element exists up to and
   including this state but not in later states.
2. Every alert in the application should be closable with an "×" button.

The developer decided:

- an element is marked as ending in the selected org state by comparing its
  `deleteDate` with the next org state of the scenario, not by `deleteDate`
  alone;
- the Delete action is disabled for an element that already ends in the
  selected org state;
- the security note "Local program" on the MCP consent page
  (`/ai/authorize`) is not closable.

## Goal

When a user views an org state, the Structure graph, node list and edit forms
clearly show which nodes and edges are in their last org state. Every
alert banner in the application has a consistent "×" button that closes it.
Both changes are frontend-only.

### Background

- The org-state graph API already returns `createDate` and nullable
  `deleteDate` for every node and edge (`frontend/src/api/orgTwinStructure.ts`).
- An element is visible at a target date when
  `createDate <= targetDate` and `deleteDate` is null or
  `deleteDate >= targetDate` (`docs/architecture/domains/ORG_TWIN_STRUCTURE.md`). The
  logical end date is inclusive.
- Deleting an element created before the selected org state sets its
  `deleteDate` to the org state's `targetDate`. The element stays visible in
  that state and disappears from later states. `GraphViewer` ignores
  `deleteDate`, so nothing shows the difference.
- Node deletion also ends connected edges with a compatible `deleteDate`, so
  those edges are ending too.
- Change sets can set a `deleteDate` that is not any org state's
  `targetDate`. That is why the rule compares with the next org state.
- Two notices already have their own "×" button: `MetricsNotice`
  (`frontend/src/features/metrics/MetricsTab.tsx`) and the prediction
  submission notices (`frontend/src/features/predictions/PredictionsTab.tsx`),
  styled by `.metrics-notice__dismiss` and `.prediction-notice__dismiss` in
  `frontend/src/styles/app.css`. All other alerts are hand-written
  `.alert` blocks with no close button.

## Requirements

### Ending Rule

- Add `frontend/src/features/structure/lifetime.ts` with a pure function
  `endsInOrgState(deleteDate, targetDate, nextTargetDate)`. It returns `true`
  when `deleteDate` is not null and either `nextTargetDate` is null or
  `deleteDate < nextTargetDate`. Dates are ISO `YYYY-MM-DD` strings.
- The next org state is the active org state of the selected scenario with
  the smallest `targetDate` greater than the selected org state's
  `targetDate`.
- `StructureTab` loads the scenario's org states with the existing
  `fetchOrgStates` (`frontend/src/api/scenarios.ts`) together with the graph
  and type catalog, under the same context guard and abort signal.
- A failed org-state load must not fail the graph load and shows no error. In
  that case only elements with `deleteDate === targetDate` count as ending.
- `StructureTab` computes `endingNodeIds` and `endingEdgeIds` once per graph
  and org-state context and passes them to `GraphViewer`, `NodeList`,
  `NodeForm` and `EdgeForm` as needed.

### Graph

- Ending nodes get the Cytoscape data flag `ending: "true"`, styled by a
  `node[ending = "true"]` selector:
  - faded fill (lower `background-opacity`) and a lighter label color
    (`#736c5e`, at least 4.5:1 on the faded default node fill) at the
    normal node font size;
  - dashed border in the danger color (`--color-danger-500`, `#c0342a`,
    written as a literal like the other `GRAPH_STYLES` colors);
  - no end-date line in the node label, which has no room for a third line;
    the popover shows the end date.
- Ending edges get the same data flag, styled by `edge[ending = "true"]`: a
  gray (`#9ca3af`) dashed line and arrows, whatever the edge type's line style,
  and a lighter label color, with no end-date line in the label. The edges of
  a node deleted in this state end with it, so they are shown this way.
- Developer decision during manual review (2026-11-02): the node and edge
  end-date lines were removed, the node label kept the normal font size with a
  lighter color, ending edges became gray dashed lines, and ending edges got
  the same end-date popover as nodes. Review round 3 darkened the lighter
  label color from `#807868` to `#736c5e` to meet 4.5:1 contrast.
- The `:selected` style still shows the selection on ending elements.
- The node hover popover adds the line
  "Exists until YYYY-MM-DD. Not shown in later org states." for ending nodes.
  Hovering an ending edge or its label box (`text-events: yes`) shows a popover
  at the edge midpoint with the edge name and the same line. Other edges get no
  popover.
- When the graph has at least one ending element, the graph controls area
  next to "Zoom to Fit" shows a small key: a dashed swatch with the text
  "Ends in this state". The key is hidden otherwise.
- Elements that are not ending look exactly as before, including elements
  with a `deleteDate` after the next org state.

### Node List And Forms

- `NodeList` shows a small "Ends" badge after the name of each ending node,
  with an accessible name such as "Ends 2026-02-01".
- The edit `NodeForm` and `EdgeForm` show, for an element with a
  `deleteDate`, the line "Exists until YYYY-MM-DD." For an ending element they
  add "Not shown in later org states."
- When the selected element's `deleteDate` equals the selected org state's
  `targetDate`, the Delete button is disabled with the explanation
  "Already removed in this org state." Delete is still available for an
  element whose `deleteDate` is later than the selected `targetDate`, because
  deleting it moves the end date earlier.

### Closable Alerts

- Add `frontend/src/components/Alert.tsx`, a shared component that renders the
  existing `.alert` markup:
  - props: `variant` (`"danger" | "info"`), optional `role`
    (`"alert" | "status"`), optional `title`, optional `message` (the text,
    rendered as `.alert__text`), optional `children` (extra content such as
    a list or a Retry button), optional `id`, optional `className`, optional `ariaLabel`, optional `onDismiss`
    and optional `dismissLabel`;
  - always renders an "×" button (`<span aria-hidden="true">×</span>`) with
    the accessible name `dismissLabel`, defaulting to
    `Dismiss {title} notice` with a title and `Dismiss notice` without one;
  - with `onDismiss`, the button calls it and the owner clears its state;
  - without `onDismiss`, the component hides itself. Callers give it a `key`
    from its message, so a new message is shown again;
  - review round 1 added optional `onRetry`, `retryLabel` and
    `retryDisabled`, which render the alert's Retry button and keep a compact
    Retry button after the alert hides itself, and optional `boxClassName`,
    which replaces the `.alert` box classes for a caller with its own box.
- Add one `.alert__dismiss` rule in `frontend/src/styles/components.css`,
  based on the current `.metrics-notice__dismiss` /
  `.prediction-notice__dismiss` rules, including hover and `:focus-visible`.
  Alert text must not run under the button. Remove the two old dismiss rules.
- `MetricsNotice` and the prediction submission notices use `Alert`. Their
  current accessible labels stay unchanged
  (`Dismiss {title} notice` and
  `Dismiss prediction request “{name}” notice`).
- Convert every `.alert` in these files to `Alert` with a close button:
  - `frontend/src/auth/LoginPage.tsx`
  - `frontend/src/pages/HomePage.tsx`
  - `frontend/src/components/OrganisationDropdown.tsx`
  - `frontend/src/components/OrgStateDropdown.tsx`
  - `frontend/src/components/ScenarioDropdown.tsx`
  - `frontend/src/features/ai/AuthorizePage.tsx` ("Decision failed" only)
  - `frontend/src/features/ai/ChangeSetList.tsx`
  - `frontend/src/features/ai/ChangeSetReview.tsx`, including the
    "Validation errors" section
  - `frontend/src/features/ai/ConnectionsList.tsx`
  - `frontend/src/features/customers/CustomersTab.tsx`
  - `frontend/src/features/events/EventsTab.tsx`
  - `frontend/src/features/metrics/MetricsTab.tsx`
  - `frontend/src/features/predictions/PredictionsTab.tsx`, including the
    single-paragraph `<p className="alert ...">` alerts. The interval error
    keeps `id="prediction-interval-error"` for its `aria-describedby` link.
  - `frontend/src/features/scenarios/ScenariosTab.tsx`
  - `frontend/src/features/structure/EdgeForm.tsx`
  - `frontend/src/features/structure/NodeForm.tsx`
  - `frontend/src/features/structure/StructureTab.tsx`
  - `frontend/src/features/structure/TimeseriePanel.tsx`
  - `frontend/src/features/users/UsersTab.tsx`
- Closing clears the owning state (for example `setActionError("")`) when the
  component owns the message or receives it with a setter. Shared alert
  sub-components that only receive `message` (for example `ActionError` in
  Customers, Events, Scenarios and Users) get an `onClose`/`onDismiss` prop.
  Use the self-hiding mode where no owner state exists, such as messages
  from the URL, conditions derived from other state (invalid dates, no
  active scenarios, no forecastable metrics) or validation errors inside
  loaded change-set data. Load errors that come with a Retry button also hide
  themselves: clearing their state would show the area's "No … available"
  empty message instead of the error. They pass their Retry action as
  `onRetry`, so a compact Retry button stays after closing. Their owners clear
  the error before every load, so a repeated failure shows the alert again.
- The Summary tab error (`.summary-state--error` in
  `frontend/src/features/summary/SummaryTab.tsx`) keeps its own box through
  `Alert`'s `boxClassName` and gets the shared "×" button. Closing clears the
  error. The Retry button stays.
- Closing the prediction-interval error keeps the input's `aria-invalid`
  marker, which is derived from the value, while the value is invalid.
- The "Local program" note on `AuthorizePage` (`role="note"`) is not closable
  and keeps its current markup.

## Acceptance Criteria

- [ ] With states 1 (2026-01-01), 2 (2026-02-01) and 3 (2026-03-01) and a
      node created in state 1 and deleted in state 2:
  - [ ] in state 1, the node looks normal;
  - [ ] in state 2, the node is faded with a dashed border and a lighter
        label, the key "Ends in this state" is shown, and the node list shows
        the "Ends" badge;
  - [ ] in state 3, the node is not shown.
- [ ] Edges ended together with the node are shown as gray dashed lines in
      state 2.
- [ ] A node whose `deleteDate` is between two org states is shown as ending
      in the earlier one only.
- [ ] A node whose `deleteDate` is on or after the next org state's
      `targetDate` is not shown as ending.
- [ ] When there is no later org state, any element with a `deleteDate` is
      shown as ending.
- [ ] If loading the org states fails, the graph still loads and only
      elements with `deleteDate === targetDate` are shown as ending.
- [ ] Selecting an ending node or edge still shows the selection highlight.
- [ ] The hover popover of an ending node or ending edge shows its end date.
- [ ] The edit form shows "Exists until …" for elements with a `deleteDate`,
      and Delete is disabled with an explanation when `deleteDate` equals the
      selected org state's `targetDate`.
- [ ] Every alert listed under Closable Alerts, and the Summary error, has an
      "×" button with an accessible name, and clicking it hides the alert.
- [ ] After closing an error alert, the next failure of the same action shows
      the alert again, even with the same message.
- [ ] The "Local program" note on `/ai/authorize` has no close button.
- [ ] Existing Metrics and prediction notice dismiss labels and behaviour are
      unchanged.
- [ ] No backend, API, migration or dependency changes.

## Out Of Scope

- Backend, API, schema or migration changes.
- Showing elements that are no longer visible (ghosts of earlier or later
  states) in the graph.
- Restoring ("undeleting") an ended element or editing its end date in the
  UI.
- Changes to the Summary timeline or other tabs' lifetime displays.
- Auto-dismissing alerts, toasts or an alert queue.
- The full-page route load error in `DeferredRoute.tsx`, which is a page
  state with a Reload button, not an alert banner.
- New dependencies.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/architecture/concepts/ORGANISATION_STATE.md
docs/operations/testing.md
```

- Graph files expected to change:
  - `frontend/src/features/structure/lifetime.ts` (new) and its test;
  - `frontend/src/features/structure/StructureTab.tsx`: org-state load,
    ending sets, props to children;
  - `frontend/src/features/structure/GraphViewer.tsx`: `ending` flag, label
    line, styles, popover line and key;
  - `frontend/src/features/structure/NodeList.tsx`: badge;
  - `frontend/src/features/structure/NodeForm.tsx` and `EdgeForm.tsx`:
    lifetime line and disabled Delete;
  - `frontend/src/styles/app.css`: key, badge and form line styles.
- Cytoscape styles are plain values in `GRAPH_STYLES`; add the
  `node[ending = "true"]` and `edge[ending = "true"]` selectors before
  `:selected`, so the selection still wins for border and line color. A data
  flag instead of a class reuses `GraphViewer`'s existing element data sync.
  Cytoscape is mocked in `GraphViewer.test.tsx`; assert on the element data
  (`ending`, `label`) passed to the mock.
- Node and edge ids are kept in separate sets.
- `StructureTab` already reloads the graph after deleting an element created
  before the selected org state, so the new ending styling appears straight
  after a delete. The org-state list does not change during a delete.
- The alert conversion touches many files with small edits. Keep each edit
  mechanical: same text, same role and same title as now. Tests that count
  all buttons, or use `getByRole("button")` without a name, may need a more
  specific query.
- Expect roughly 300 lines for the graph part and 300-400 for the alerts,
  including tests. This may exceed the 500-line guideline. The developer chose
  to keep both in one task.
- No new dependencies, no ADR and no diagram changes.

## Testing

Required:

- [ ] Frontend tests:
  - `lifetime.test.ts`: null `deleteDate`; `deleteDate` equal to the target
    date; between the target and the next state; equal to and after the next
    state; no next state;
  - `GraphViewer.test.tsx`: ending nodes and edges get the `ending` flag and
    keep their two-line label; others do not; the ending styles; the key is shown only
    when there are ending elements; the popover line for an ending node and
    an ending edge, and no popover for other edges;
  - `StructureTab.test.tsx`: the three-state example above, using
    `fetchOrgStates`; the org-state load failure fallback; Delete disabled
    with explanation when `deleteDate` equals the target date; Delete still
    enabled when `deleteDate` is later; the "Ends" badge in the node list;
  - `Alert` component tests: close button with default and custom labels;
    `onDismiss` called; self-hiding mode and showing again with a new `key`;
  - at least one dismiss test per converted feature area (Structure,
    Scenarios, Users, Events, Customers, AI, Predictions, dropdowns, Login,
    Home, Summary), including showing the alert again after a repeated
    failure;
  - `AuthorizePage` test: the "Local program" note has no close button;
  - existing `MetricsTab.test.tsx` and `PredictionRequests.test.tsx` dismiss
    tests pass unchanged.
- [ ] Manual verification at `https://app.localhost` with the three-state
      example: check states 1-3, hovering, selecting, the node list, the edit
      form and Delete; trigger and close at least one alert in Structure,
      Scenarios and Metrics; check the "×" button in light layout at 1280px
      and 700px.
- [ ] Format check
- [ ] Lint
- [ ] Build (includes the TypeScript check, `tsc -b`)

Not applicable:

- [ ] Backend tests. Reason: frontend-only change; the API already returns
      `deleteDate`.

Commands:

```bash
cd frontend
pnpm format:check
pnpm lint
pnpm test
pnpm build
cd ..
python3 scripts/ai_review_records.py validate
```

## Documentation

- `docs/architecture/domains/ORG_TWIN_STRUCTURE.md`: in "Graph Scope And Lifetimes", add
  that the Structure UI marks elements in their last visible org state
  (compared with the next org state), shows their end date and disables
  Delete when the element already ends in the selected state.
- `docs/operations/testing.md`: mention the shared `Alert` component dismiss coverage if
  the frontend test section lists UI component coverage.
- No architecture, ADR, concept, data or diagram changes.

## Notes For AI Agent

- Use the branch `feature/TASK-072-graph-ending-elements-and-closable-alerts`
  from `main`.
- Implement only this task's scope.
- Do not add dependencies.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-072/`.
- Report all changed files and every verification command run.
