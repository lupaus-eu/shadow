# TASK-022 Scenarios Tab UI Fixes

## Source Plan

Approved plan: create a frontend follow-up task for the current Scenarios tab
implementation. The task fixes left sidebar layout issues, org-state form
editing behavior, selection defaults, and protected Reality scenario behavior.

This task covers only frontend changes in `frontend/`.

## Goal

Improve the Scenarios tab so scenario and organisation-state selection is
clearer, org states are immediately editable, destructive state deletion
requires an explicit confirmation, and protected Reality scenario behavior only
blocks deletion.

The user should be able to load or refresh the page and immediately get a
usable default scenario and org-state selection when data exists.

## Requirements

- Keep this task scoped to the Scenarios tab frontend implementation.
- Update the left Scenarios panel so:
  - `Protected` / `Not protected` tag width does not depend on description
    content.
  - Scenario descriptions are not shown in the left panel.
  - Org-state descriptions are not shown in the left panel.
  - Scenario and org-state cards use automatic height rather than a locked
    equal-height layout.
- Update selected scenario visuals so:
  - the selected scenario and its org states are wrapped by a thin orange
    border,
  - the border wraps both the scenario and its states rather than only the
    scenario row,
  - the area between the selected scenario and org states has a gray
    background,
  - the org-state list shows a `STATES` subheading above the first state.
- Update org-state detail editing so:
  - the state id element is hidden,
  - the selected org state's name and description are editable immediately,
  - no separate `Edit state` action is required before editing,
  - `Save state` is disabled until the user changes a field.
- Update org-state deletion so:
  - a separate confirmation input appears under `Save org state`,
  - the confirmation input placeholder is `Type DELETE to confirm`,
  - `Delete state` is disabled until the user types exactly `DELETE`.
- Update protected scenario behavior so:
  - the Reality scenario name and description remain editable,
  - protected status only prevents scenario deletion in the frontend,
  - the frontend does not block Reality scenario editing.
- Update default selection behavior so:
  - when the page loads or is refreshed without a current selection, the first
    scenario is selected automatically,
  - the first org state of that scenario is selected automatically when it
    exists.
- Update the Fork from existing form so:
  - selecting `Source state` only changes the source state used for the fork
    payload,
  - selecting `Source state` does not switch the active org-state selection or
    jump the right workspace to the selected org state.

## Acceptance Criteria

- [ ] Protected / Not protected tag width does not depend on the scenario
      description width.
- [ ] Scenario descriptions are not shown in the left panel.
- [ ] Org-state descriptions are not shown in the left panel.
- [ ] The selected scenario and its org states are surrounded by a thin orange
      border.
- [ ] The orange border wraps both the scenario and its states, not only the
      scenario row.
- [ ] The background between the selected scenario and its org states is gray.
- [ ] The org-state list shows a `STATES` subheading above the first state.
- [ ] State id is not visible in the org-state detail view.
- [ ] The selected org state's details are editable immediately without an
      `Edit state` button.
- [ ] The selected org state's name and description fields are editable
      immediately.
- [ ] `Save state` is initially disabled for an unchanged selected org state.
- [ ] `Save state` becomes enabled only after the user changes an editable
      field.
- [ ] A delete confirmation input is shown under `Save org state`.
- [ ] The delete confirmation input placeholder is `Type DELETE to confirm`.
- [ ] `Delete state` is disabled until the user types exactly `DELETE`.
- [ ] Reality scenario name and description are editable.
- [ ] Protected status only prevents scenario deletion in the frontend.
- [ ] Frontend behavior does not block Reality scenario editing.
- [ ] Scenario cards use automatic height.
- [ ] Org-state cards use automatic height.
- [ ] On page load with no current selection, the first scenario is selected
      automatically.
- [ ] On page load with no current org-state selection, the first org state of
      the selected scenario is selected automatically when one exists.
- [ ] The same default selection behavior applies after browser refresh.
- [ ] Selecting `Source state` in Fork from existing does not change the active
      org-state selection.
- [ ] Selecting `Source state` in Fork from existing does not switch the right
      workspace from scenario detail to state detail.
- [ ] Forking a scenario sends the selected fork source state in the copy
      payload.
- [ ] No new dependency is added.

## Out Of Scope

- Backend logic or API changes.
- Database schema, migration, or seed changes.
- ADR changes.
- Authentication or authorization changes.
- Changes outside the Scenarios tab.
- New dependencies.
- Broad redesign of the application shell or other tabs.

## Implementation Notes

- Read these before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/adr/0001-tech-stack.md
docs/architecture/concepts/SCENARIO.md
docs/architecture/concepts/ORGANISATION_STATE.md
docs/operations/testing.md
```

- Keep changes inside existing frontend Scenarios-tab patterns.
- Likely implementation targets include:
  - `frontend/src/features/scenarios/ScenariosTab.tsx`
  - Scenarios-tab styles colocated with the current implementation
  - existing frontend tests such as `frontend/src/App.test.tsx`
- Do not add new packages or UI libraries.
- Frontend protected-scenario behavior is UX only; backend remains the source of
  truth for mutation rules.
- Tests may assume that the backend allows Reality scenario updates, because
  this task only changes the frontend's edit blocking behavior.

## Testing

Required:

- [ ] Frontend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build

Not applicable:

- [ ] Backend tests: backend code is not changed in this task.
- [ ] Integration tests: frontend unit coverage is the default expected level
      unless a lightweight existing path already supports it without new
      tooling.
- [ ] Typecheck: no dedicated frontend typecheck command is currently defined
      in the repository workflow.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Frontend tests should cover:

- protected tag width behavior and hidden left-panel descriptions
- orange selected group border and gray selected group background rendering
- `STATES` subheading rendering
- immediate org-state editing without a separate edit action
- `Save state` enabling only after a field changes
- `DELETE` confirmation behavior for state deletion
- Reality scenario editability while deletion remains blocked
- default scenario and org-state selection on initial load or refresh
- fork source-state selection staying local to the fork payload without
  changing the active org-state view

Manual verification should cover:

- load or refresh the Scenarios tab with scenario and org-state data
- verify the first scenario and first org state are selected automatically
- select Reality and verify its name and description can be edited
- verify Reality scenario deletion remains unavailable
- verify state deletion requires typing exactly `DELETE`
- visually inspect the left panel selection border, gray background, `STATES`
  heading, hidden descriptions, and automatic card heights

## Documentation

No documentation updates are expected beyond this task file unless the
implementation changes visible workflow details that future agents or humans
need to understand.

Do not update architecture, ADR, domain, concept, data, or diagram
documentation unless implementation reveals a genuine documentation mismatch.

## Notes For AI Agent

- Lue `AGENTS.md` ja `docs/architecture/overview.md` ennen toteutusta.
- Lue `docs/adr/0001-tech-stack.md`,
  `docs/architecture/concepts/SCENARIO.md`, `docs/architecture/concepts/ORGANISATION_STATE.md` ja
  `docs/operations/testing.md` ennen toteutusta.
- Toteuta vain taman taskin scope.
- Ala muuta backendia, tietokantaa, migraatioita tai muita valilehtia tassa
  taskissa.
- Ala lisaa uusia riippuvuuksia ilman hyvaksyntaa.
- Lisaa tai paivita frontend-testit Scenarios-sivun valinta- ja
  lomakelogiikalle.
- Jos toteutus edellyttaa backend-, API- tai arkkitehtuurimuutosta, pysahdy ja
  pyydä ihmisen päätös.
- Kerro lopuksi mita muutit ja miten tarkistit tyon.
