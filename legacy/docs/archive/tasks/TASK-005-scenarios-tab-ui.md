# TASK-005 Scenarios Tab UI

Status: Implemented

## Source Plan

This task comes from the developer-approved Scenarios Tab UI Plan.

The accepted plan implements the Scenarios tab as the control plane for scenario and org-state management in the Shadow frontend.

This file has been updated after implementation to reflect the current Scenarios page behavior.

## Goal

Build the first frontend implementation of the Scenarios tab in `frontend/`.

The tab lets the user view scenarios for the current organisation, manage non-protected scenarios, manage org states inside the selected scenario, and activate Structure and Events after both a scenario and an org state are selected.

## Requirements

- Replace the Scenarios empty state with a scenario management UI.
- Show scenarios in the left selection panel.
- Show the selected scenario's org states inline below that selected scenario in the left panel.
- Do not show org states below unselected scenarios.
- Show the selected scenario/state detail and action forms in the right workspace.
- Add a typed API client for scenarios and org states.
- Load scenarios for the current organisation.
- Mark protected scenarios, including `reality`, as protected in the UI.
- Prevent editing and deleting protected scenarios.
- Allow copying a selected scenario using the selected org state as the target-date boundary.
- Load org states for the selected scenario ordered by target date.
- Automatically select the first org state by target date when a scenario is selected or initialised.
- Allow creating, editing, and deleting org states.
- Synchronise org states for the selected scenario when the toolbar Refresh button is clicked.
- Require a delete confirmation by typing `DELETE` into an input before enabling the delete button.
- Prevent duplicate target dates within the currently loaded org states before submitting create/edit.
- Update workspace selection context when the user selects a scenario and org state.
- Disable Structure and Events until both a scenario and an org state are selected.

## Acceptance Criteria

- [x] Scenarios tab renders a left selection panel and right detail/action workspace.
- [x] Scenario list loads from the API client for the current organisation.
- [x] Protected scenarios display a protected indicator and cannot be edited or deleted.
- [x] Non-protected scenarios can be renamed, described, copied, and deleted through UI flows.
- [x] Scenario delete requires typing `DELETE` before the delete button is enabled.
- [x] Org states load when a scenario is selected and are displayed ordered by target date.
- [x] Org states are displayed inline below the selected scenario only.
- [x] The first org state is selected automatically when a scenario is selected or initialised.
- [x] Org states can be created, edited, and deleted through UI flows.
- [x] Org states are synchronised for the selected scenario from the toolbar Refresh button.
- [x] Org-state delete requires typing `DELETE` before the delete button is enabled.
- [x] Duplicate target dates are blocked in the frontend create/edit form.
- [x] Selecting both scenario and org state updates the workspace header.
- [x] Structure and Events are disabled until both scenario and org state are selected.
- [x] Frontend tests cover loading, selection, protected scenario behavior, duplicate date validation, delete confirmation, refresh-driven sync, mutation calls, and tab activation.
- [x] `pnpm lint`, `pnpm test`, and `pnpm build` pass.

## Out Of Scope

- Backend endpoint implementation.
- Database schema, migrations, or seed data.
- Graph-change-date calculation logic.
- Authorization rules.
- Real Structure or Events tab content.
- ADR changes.

## Implementation Notes

- Keep this task scoped to `frontend/`.
- Backend will later implement the API contract defined by the frontend client.
- `protected: true` means no rename, description update, or delete in the UI.
- Copying a scenario is allowed even when the source scenario is protected.
- Target date uniqueness is per scenario.
- `targetDate` is represented as an ISO date string in `YYYY-MM-DD` format.
- Org states are kept in a single loaded collection for the currently selected scenario.
- Refresh synchronises the selected scenario's org states and preserves the selected org state when it still exists; otherwise the first org state is selected.
- Deleting the selected org state selects the first remaining org state, if one exists.

## Testing

Required:

- [x] Frontend tests
- [ ] Manual verification
- [x] Lint
- [x] Build
- [x] Typecheck via `pnpm build`

Not applicable:

- [ ] Backend tests: no backend code in scope.
- [ ] Integration tests: backend endpoints are contract-only in this task.
- [ ] Database tests: no schema or migration changes.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Last verified by AI agent:

- `pnpm test -- --runInBand`
- `pnpm lint`
- `pnpm build`

Note: `pnpm build` passed, but Vite reported that Node.js `22.8.0` is below its supported `22.12+` range.

## Documentation

- Added and updated `docs/archive/tasks/TASK-005-scenarios-tab-ui.md`.
- No ADR is required.

## Notes For AI Agent

- Lue `AGENTS.md`, `docs/architecture/overview.md`, `docs/adr/0001-tech-stack.md` ja tämä task ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Lisää testit, kun muutos koskee sovelluskoodia.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
