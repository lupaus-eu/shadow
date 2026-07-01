# TASK-021B Org States Clean Frontend

## Source Plan

Approved plan: add a right-aligned `Clean states` action in the Scenarios tab
detail-mode switch panel. The action should call the backend cleanup endpoint
for the selected scenario and then refresh the org-state list.

This task covers only the frontend UI, API client wiring and frontend tests. It
assumes the backend endpoint from `TASK-021A` exists.

## Goal

Implement the frontend flow for cleaning organisation states from the selected
scenario without introducing new dependencies or expanding into unrelated
Scenarios tab behavior.

The user should see a clearly placed action, a confirmation step, a busy state,
and a refreshed org-state list after a successful cleanup.

## Requirements

- Depends on `TASK-021A Org States Clean Backend`.
- Add a right-aligned `Clean states` button to the
  `detail-mode-switch-panel` in the Scenarios tab.
- Add frontend API client support for:
  - `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/clean`
- Treat the cleanup response as:
  - `{ "cleaned": <n> }`
- Button behavior:
  - disable when no scenario is selected
  - disable when the selected scenario is protected
  - disable while cleanup is already in progress
- Show a confirmation step before sending the cleanup request.
- Show a busy label or spinner state while the request is running.
- On success:
  - show a user-visible success message containing the cleaned count
  - refresh the selected scenario org-state data using existing read flow
  - update selection so it stays on the current org state if it still exists,
    otherwise select the first remaining org state or none
- On failure:
  - surface user-friendly messages for `404`, `409` and generic server errors
- Do not add a new dependency.
- Do not implement backend behavior in this task.

## Acceptance Criteria

- [ ] `Clean states` button is visible in the detail-mode switch panel.
- [ ] The button is right-aligned relative to the existing detail-mode switch
      controls.
- [ ] The button is disabled when no scenario is selected.
- [ ] The button is disabled when the selected scenario is protected.
- [ ] The button is disabled while the cleanup request is in progress.
- [ ] Confirming the action sends `POST` to the cleanup endpoint for the
      selected organisation and scenario.
- [ ] Successful cleanup shows the cleaned count to the user.
- [ ] Successful cleanup refreshes the visible org-state list.
- [ ] Failure states show a user-friendly error message.
- [ ] No new dependency is added.

## Out Of Scope

- Backend endpoint or service implementation.
- Authentication or authorization implementation.
- Changes outside the Scenarios tab cleanup flow.
- New global toast or notification library.
- Broad redesign of the Scenarios tab layout.
- E2E automation unless an existing lightweight path already supports it
  without new tooling.
- Documentation-only work beyond small inline code comments if needed.

## Implementation Notes

- Depends on `TASK-021A Org States Clean Backend`.
- Read these before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-001-tech-stack.md
docs/domains/ORG_STATES.md
docs/concepts/SCENARIO.md
docs/concepts/ORGANISATION_STATE.md
docs/TESTING.md
```

- Keep frontend behavior consistent with current repo patterns in:
  - `frontend/src/features/scenarios/ScenariosTab.tsx`
  - `frontend/src/api/scenarios.ts`
  - `frontend/src/App.test.tsx`
- The repository currently uses inline error strings and existing component
  state rather than a toast dependency. Reuse those patterns.
- Use the existing selected-scenario reload path instead of inventing a second
  refresh mechanism.
- Protected-scenario UX is a convenience only; backend remains the source of
  truth for mutation rules.
- If backend response shape differs from the planned `{ "cleaned": n }`,
  update this task before implementation rather than guessing.

## Testing

Required:

- [ ] Frontend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build

Not applicable:

- [ ] Backend tests: backend code is not changed in this task.
- [ ] Integration tests: frontend unit coverage is the default expected level
      unless a lightweight existing integration path is already present.
- [ ] Typecheck: no dedicated frontend typecheck command is currently defined in
      the repository workflow.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Frontend tests should cover:

- button disabled state with no selected scenario
- button disabled state for protected scenario
- confirmation flow before request submission
- busy state while cleanup is in progress
- successful cleanup request and refreshed org-state list loading
- visible success feedback with cleaned count
- error handling for failed cleanup response

Manual verification should cover:

- select a non-protected scenario in the Scenarios tab
- trigger `Clean states` and confirm the action
- verify the loading state and refreshed list
- verify protected scenarios do not allow the action

## Documentation

Documentation updates are primarily covered by `TASK-021C`.

If implementation changes visible labels, messages or manual steps that would
be unclear without docs, update only the minimum relevant docs:

- `docs/domains/ORG_STATES.md`
- `docs/LOCAL-DEVELOPMENT.md`

## Notes For AI Agent

- Lue `AGENTS.md` ja `ARCHITECTURE.md` ennen toteutusta.
- Lue relevantit domain-, concept- ja testing-dokumentit ennen toteutusta.
- Toteuta vain taman taskin scope.
- Ala lisaa uusia riippuvuuksia ilman hyvaksyntaa.
- Ala muuta backendin behavioria tassa taskissa.
- Kayta olemassa olevia Scenarios-tabin tilanhallinnan ja API-clientin
  abstrahointeja.
- Lisaa tai paivita frontend-testit muutoksen riskin mukaan.
- Kerro lopuksi mita muutit ja miten tarkistit tyon.
