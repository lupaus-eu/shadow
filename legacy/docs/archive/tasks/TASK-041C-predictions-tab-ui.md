# TASK-041C Predictions Tab UI And QA

## Source Plan

Approved plan: "Prediction Feature Task Specifications", based on the approved
Predictions workspace plan and the backend contract implemented by TASK-041B.

Dependency: TASK-041B Predictions Backend And Modelling must be completed and
its API contract accepted before this task is implemented.

## Goal

Add a standalone Predictions workspace tab where users generate, inspect and
compare immutable prediction versions. The UI must clearly separate manually
entered Reality data from saved model outputs and must not change the existing
Analysis workspace.

## Requirements

### Workspace and API client

- Add a `Predictions` workspace tab and route at
  `/shadow/{orgId}/predictions`.
- Do not replace, rename, redirect or otherwise modify the existing Analysis
  tab or `/analysis` route.
- Predictions must not require the globally selected scenario or organisation
  state because one generation can target multiple scenarios.
- Add typed frontend API-client functions and DTOs for TASK-041B's preflight,
  create, list and detail routes.

### Generation form

- Let the user target all active scenarios or choose a non-empty subset of
  active scenarios, including Reality.
- Require a unique prediction-version name and display server-side name and
  eligibility errors accessibly.
- Provide start and end date pickers plus independent start/end event dropdowns.
- Load event options from every active organisation scenario using existing
  scenario and event APIs. Each option must state the scenario, event name and
  event date, and be sorted by date.
- Selecting an event sets the corresponding date picker; manually changing a
  date clears that event selection.
- When a start date is present, show only events strictly later than it in the
  end-event dropdown. When an end date is present, show only events strictly
  earlier than it in the start-event dropdown.
- Require `startDate < endDate`; clear invalid stale event selections and show
  a user-friendly validation message.
- Let the user explicitly choose `asOfStart` or `allCurrentReality`. Explain
  the future-leakage implication of `allCurrentReality` for a retrospective
  prediction.
- Call preflight before creation, display per-scenario/metric eligibility and
  automatic seasonal periods, and expose required manual per-metric period
  inputs. Submit only a valid preflight-backed create request.

### Version library and plotting

- List saved prediction versions with name, creation time, requested date
  range, cutoff mode, target count and generation status.
- Let users select multiple saved versions, scenarios, models/baselines,
  metrics and a plotted date range.
- Display one separate chart per selected numeric metric so units are never
  mixed on one Y-axis.
- Let users include or hide the current manually entered Reality series.
- Make provenance distinguishable in chart lines, legend and tooltips:
  - current Reality values are labelled as manually entered realized data;
  - prediction lines include version name, target scenario and model kind;
  - overlapping versions remain individually identifiable.
- Reuse existing in-repository SVG chart patterns and styles. Do not add a
  frontend charting dependency.
- Cover loading, empty, error and aborted-request states consistently with
  existing workspace tabs.

## Acceptance Criteria

- [ ] Predictions is available at `/shadow/{orgId}/predictions` without a
      selected scenario or organisation state.
- [ ] Analysis remains available and unchanged at its existing route.
- [ ] The generation form supports all active scenarios and explicit
      multi-scenario selection.
- [ ] Event choices include name and date from every active scenario, and both
      event dropdowns filter correctly when either date changes.
- [ ] Invalid or equal start/end dates cannot be submitted.
- [ ] Users can choose the Reality cutoff mode and complete required
      manual-seasonality overrides returned by preflight.
- [ ] Successful creation refreshes the version library and opens or selects
      the saved immutable result.
- [ ] Users can compare multiple saved versions and separately plot multiple
      selected metrics.
- [ ] Users can filter scenarios, model/baseline lines and plot date range,
      and can include or hide current Reality data.
- [ ] A viewer can unmistakably distinguish manually entered realized values
      from predictions and identify overlapping versions.
- [ ] Loading, empty and error states are user-visible and accessible.
- [ ] No frontend dependency is added.

## Out Of Scope

- Changes to Forecasting Domain tables, migrations, API algorithms or model
  behavior.
- Changes to the existing Analysis tab or `/analysis` route.
- Editing Reality values, events, graph structure or target metrics from this
  tab.
- Background job progress UX, polling, scheduling or retry controls.
- A general-purpose charting library, exports, sharing, deleting prediction
  versions or individual numeric-metric selection during generation.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0007-predictions-forecasting-domain.md
docs/architecture/domains/FORECASTING.md
docs/architecture/domains/ORG_STATES.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/operations/testing.md
docs/archive/tasks/TASK-041B-predictions-backend-modeling.md
docs/archive/tasks/TASK-041C-predictions-tab-ui.md
```

- Follow existing workspace-tab, API-client, selection-context, form and
  Summary SVG-chart conventions. The selected global scenario remains
  available to other tabs and must not be changed as a side effect.
- Use the existing `fetchScenarios` and `fetchEvents` APIs to build the event
  selector catalog; this task does not add a bulk event endpoint.
- Keep the generation request's selected scenario IDs explicit. When the user
  chooses all scenarios, resolve that option to the currently active scenario
  IDs before preflight and creation so the saved version is reproducible.
- Date picker values may be arbitrary valid calendar dates; forecast results
  returned by the backend already contain only valid starts for each metric's
  time unit.
- Fetch current Reality timeseries only for the optional realized-data layer.
  It is live manually entered data, while prediction results come from saved
  immutable version detail responses.

## Testing

Required:

- [ ] Frontend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build

Not applicable:

- [ ] Backend tests: backend behavior is TASK-041B.
- [ ] Backend integration tests: no backend changes are made in this task.
- [ ] Backend typecheck: no backend source changes are expected.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Frontend tests must cover:

- Predictions route rendering without global scenario/org-state selection and
  unchanged Analysis routing;
- loading every scenario's events and formatting event name/date options;
- event-to-date synchronization and bidirectional strict dropdown filtering;
- all-versus-selected scenario requests, date validation and cutoff choice;
- preflight eligibility rendering, manual-seasonality input and create payload;
- version-library loading, refresh and error states;
- multi-version, scenario and model/baseline filters;
- separate metric charts, date-range filtering and Reality visibility; and
- provenance labels/styles for current realized data versus overlapping saved
  predictions.

Manual verification must cover:

- opening Predictions while no scenario or organisation state is selected;
- selecting a start or end event from a different scenario and confirming the
  opposite dropdown filters immediately;
- generating a uniquely named version after preflight;
- selecting two overlapping versions and confirming labels/tooltip provenance;
- showing and hiding current Reality data; and
- opening Analysis afterward to confirm its route and content are unchanged.

## Documentation

Update only if implementation requires it:

- `docs/operations/testing.md`, for reusable Predictions UI guidance;
- `README.md` or workspace documentation, if user-visible tab navigation is
  documented there.

No data-model, migration, Forecasting Domain or ADR changes are expected in
this task.

## Notes For AI Agent

- Implement only after TASK-041B's API contract exists.
- Preserve the existing Analysis tab and route exactly.
- Add no frontend dependency; use existing React, SVG and CSS patterns.
- Add tests for all changed UI behavior and report all checks run.
