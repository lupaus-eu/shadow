# TASK-033 Restore Selected Scenario Form

## Source Plan

Developer-approved plan: fix the Scenarios tab regression where navigating to
another workspace tab and then returning to Scenarios preserves the selected
scenario in workspace context but leaves the Selected scenario form empty.

The accepted plan keeps the change in the frontend, reconciles persisted
workspace selection with freshly fetched scenario data when the Scenarios tab
remounts, and adds navigation regression coverage.

## Goal

Restore a usable Selected scenario form whenever the user returns to the
Scenarios page with a scenario already selected.

The selected scenario and organisation state must remain selected when they
still exist, while the scenario-derived local form state is rehydrated from the
latest fetched scenario DTO. The unchanged restored form must not appear dirty
or enable saving.

## Requirements

- Keep this task scoped to the Scenarios tab frontend implementation.
- When scenario loading completes, resolve the scenario stored in workspace
  selection context against the fetched scenario list.
- When the stored scenario still exists:
  - keep it selected,
  - populate the Selected scenario name and description from the fetched DTO,
  - restore scenario-derived defaults in the Fork from existing form,
  - preserve the selected organisation state so the existing org-state loading
    behavior can restore it.
- When the stored scenario no longer exists, select the first fetched scenario
  when one is available and clear any organisation-state selection that belongs
  to the missing scenario.
- Keep the current default behavior when no scenario has been selected: select
  the first fetched scenario and then the first available organisation state.
- Keep `Save scenario` disabled immediately after form restoration because the
  restored fields match the fetched scenario.
- Consolidate duplicated scenario selection and form-initialization logic where
  practical without changing unrelated Scenarios behavior.
- Add frontend regression coverage for navigating away from and back to the
  Scenarios page.
- Do not add dependencies.

## Acceptance Criteria

- [ ] A selected scenario remains selected after navigating to another
      workspace tab and returning to Scenarios.
- [ ] The Selected scenario name field contains the selected scenario's fetched
      name after returning.
- [ ] The Selected scenario description field contains the selected scenario's
      fetched description after returning.
- [ ] `Save scenario` is disabled immediately after the form is restored.
- [ ] The previously selected organisation state remains selected after
      returning when it still exists.
- [ ] The Fork from existing form is initialised from the restored scenario and
      does not contain empty scenario-derived defaults solely because the tab
      remounted.
- [ ] If the persisted scenario no longer exists, the first fetched scenario is
      selected and a stale organisation-state selection is not retained.
- [ ] Initial page-load selection behavior continues to select the first
      scenario and first organisation state when no selection exists.
- [ ] Existing scenario selection, editing, refresh, fork, delete, and org-state
      behavior remains unchanged.
- [ ] Frontend regression tests cover the navigate-away-and-return flow.
- [ ] No new dependency is added.

## Out Of Scope

- Backend logic or API contract changes.
- Database schema, migration, or seed changes.
- Persisting workspace selection across a full browser reload or a new browser
  session.
- Authentication or authorization changes.
- Changes to scenario or organisation-state business rules.
- Broad redesign of workspace routing, selection context, or Scenarios UI.
- New dependencies.

## Implementation Notes

Read these before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/operations/testing.md
docs/archive/tasks/TASK-005-scenarios-tab-ui.md
docs/archive/tasks/TASK-022-scenarios-tab-ui-fixes.md
```

Likely implementation targets:

```text
frontend/src/features/scenarios/ScenariosTab.tsx
frontend/src/App.test.tsx
```

`WorkspaceSelectionProvider` remains mounted while workspace child routes
change, but `ScenariosTab` is unmounted. On remount, the selected scenario ID is
available from workspace context while the component-local scenario edit and
fork fields start empty. The current scenario-loading paths initialise those
fields only when there is no selected scenario.

Reconcile the stored scenario ID with the newly fetched scenario DTOs and use
the matching DTO to hydrate local scenario-derived fields. Preserve the stored
organisation-state selection only when restoring the same valid scenario. Do
not clear it as part of ordinary remount restoration.

If no matching scenario exists, use the existing first-scenario fallback and
clear the stale organisation-state selection before org states are loaded for
the replacement scenario.

Prefer a small shared helper for scenario-derived local state if it removes the
current duplicated initial-load and explicit-selection setup without widening
the change. Avoid an effect that could overwrite user edits on unrelated
rerenders.

No ADR is expected because this is a scoped frontend state-restoration bug fix,
not an architecture change.

## Testing

Required:

- [ ] Frontend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck through the existing frontend build

Not applicable:

- [ ] Backend tests: no backend code is changed.
- [ ] Integration tests: existing React component and routing tests cover this
      frontend state transition without new tooling.
- [ ] Database tests: no schema, migration, or persistence change is involved.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Frontend tests should cover:

- selecting a non-default scenario and organisation state
- navigating from Scenarios to another enabled workspace tab
- returning to Scenarios
- preserved scenario and organisation-state selection
- restored Selected scenario name and description
- disabled `Save scenario` before any edit
- restored scenario-derived Fork from existing defaults
- fallback behavior when a persisted scenario is absent from the fetched list

Manual verification should cover:

- repeat the navigate-away-and-return flow with the protected Reality scenario
- repeat the flow with a non-protected scenario
- verify the Selected scenario fields are populated and Save remains disabled
- verify the selected organisation state is still shown in the workspace
  indicator and scenario sidebar

## Documentation

No documentation updates are expected beyond this task file unless
implementation reveals a genuine mismatch in the current Scenarios workflow
documentation.

Do not update architecture, ADR, domain, concept, data, or diagram documentation
for this scoped frontend bug fix.

## Notes For AI Agent

- Lue `AGENTS.md`, `docs/architecture/overview.md`, `docs/operations/testing.md` ja tämä task ennen
  toteutusta.
- Lue `docs/archive/tasks/TASK-005-scenarios-tab-ui.md` ja
  `docs/archive/tasks/TASK-022-scenarios-tab-ui-fixes.md` nykyisen valintakäyttäytymisen
  taustaksi.
- Toteuta vain tämän taskin scope.
- Älä muuta backendia, API-sopimusta, tietokantaa tai migraatioita.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Säilytä valittu organisation state, kun sama valittu scenario löytyy edelleen
  API-vastauksesta.
- Lisää frontend-regressiotestit navigoinnille ja lomakkeen palautumiselle.
- Jos toteutus edellyttää workspace state -arkkitehtuurin muuttamista, pysähdy
  ja pyydä ihmisen päätös.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
