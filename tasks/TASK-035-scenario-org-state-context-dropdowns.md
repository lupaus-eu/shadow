# TASK-035 Scenario And Org State Context Dropdowns

## Source Plan

Developer-approved plan: replace the read-only Scenario and Org state context
chips in the workspace header with dropdowns that let the user change the
active scenario and organisation state from any workspace tab.

The updated accepted plan keeps selection identity in the existing
`WorkspaceSelectionContext`, reuses the existing scenario and organisation-state
read APIs, and keeps the user on the current workspace tab when context changes.
The Scenario dropdown is a two-column scenario-and-state picker with an explicit
`Select` action. The Org state dropdown switches the active state immediately
and only lists states owned by the active scenario.

## Goal

Make the Scenario and Org state values in the workspace header interactive so
the user can change the active planning context without leaving the current
workspace tab.

The Scenario dropdown must let the user preview a scenario and choose one of
that scenario's organisation states before applying both selections together.
The standalone Org state dropdown must switch state within the active scenario
immediately. Context-dependent content on the current tab must then recompute or
refetch as required, and neither selector may expose a state belonging to the
wrong scenario.

## Requirements

- Replace the read-only Scenario and Org state context-chip spans in the
  workspace header with accessible dropdown triggers.
- Keep the existing Organisation dropdown behavior unchanged.
- Preserve the current context-chip label and value presentation in each
  trigger, including `None` when no value is selected.
- Implement the controls as accessible custom button and anchored option-panel
  dropdowns consistent with the existing workspace header treatment.
- Reuse existing design tokens, button, selected-row, alert, and focus styles
  where suitable.
- Do not add a dropdown, popover, state-management, or icon dependency.
- Render the Scenario dropdown as a two-column picker:
  - list the current organisation's active scenarios in the left column,
  - list only the previewed scenario's organisation states in the right column,
  - place a button with the exact visible label `Select` inside the dropdown.
- Load scenario choices through the existing
  `GET /api/v1/organisations/{organisation_key}/scenarios` client operation when
  the Scenario dropdown opens.
- Display active scenarios in the order returned by the existing scenario API.
- Maintain draft scenario and organisation-state selections while the Scenario
  dropdown is open. Clicking a scenario in the left column must change only the
  draft scenario and load its states; it must not change workspace context or
  refetch the current tab yet.
- Initialise the Scenario dropdown draft selection from the active scenario and
  organisation state when they are still present in the fetched choices.
- When a draft scenario has no matching active organisation-state selection,
  select its first organisation state by `targetDate` after loading, consistent
  with the existing Scenarios-tab default.
- Load the right-column choices through the existing
  `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states`
  client operation for the current draft scenario.
- Order right-column organisation states by `targetDate`, visibly distinguish
  the active context from the current draft choices, and display each state's
  name and target date clearly.
- Disable `Select` until both a valid draft scenario and one of its organisation
  states are selected and their data is no longer loading.
- Clicking `Select` must:
  - commit the draft scenario and organisation state together to
    `WorkspaceSelectionContext`,
  - use stable ids plus the current scenario name, state name, and state target
    date,
  - close and reset the dropdown's draft state,
  - keep the current URL and active workspace tab unchanged,
  - cause the active tab to recompute or refetch context-dependent data when the
    committed scenario/state pair differs from the active pair.
- Closing the Scenario dropdown through cancellation, outside interaction, or
  `Escape` must discard uncommitted draft choices without changing workspace
  context or refetching the current tab.
- Disable the Org state dropdown when no scenario is selected.
- Load organisation-state choices through the existing
  `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states`
  client operation when the Org state dropdown opens.
- Load organisation states only for the currently selected scenario and order
  them by `targetDate`, matching the Scenarios tab.
- Clear cached organisation-state choices when the selected scenario changes.
- Cancel or ignore stale organisation-state requests so a response for a
  previously selected scenario cannot replace the current scenario's choices.
- Visibly mark the currently selected organisation state and display each
  state's name and target date clearly.
- When an organisation state is selected:
  - update `selectedOrgState` with its stable id, name, and target date,
  - close the dropdown,
  - keep the current URL, selected scenario, and active workspace tab unchanged,
  - cause the active tab to recompute or refetch organisation-state-dependent
    data when the selected state changes.
- Selecting the already active scenario/state pair or already active standalone
  organisation state must not trigger an unnecessary context-data refetch.
- Ensure every context-dependent workspace tab reacts correctly to an in-place
  context change:
  - Scenarios must reconcile its local lists, selected rows, detail mode, and
    forms with the committed scenario and organisation state,
  - Structure must refetch graph and other state-scoped data for the committed
    scenario/state pair,
  - Events and Metrics must refetch when their scenario context changes,
  - Summary must refetch scenario-scoped data when the scenario changes and
    recompute state-dependent presentation when only the organisation state
    changes,
  - tabs without scenario or organisation-state data must remain mounted and
    unchanged.
- Abort or ignore stale current-tab requests so responses from the previous
  context cannot replace data loaded for the new context.
- Keep dropdown option data local and short-lived; do not widen
  `WorkspaceSelectionContext` into a scenario or organisation-state inventory
  store.
- Fetch choices when a dropdown opens so scenario and organisation-state
  renames, copies, creates, deletes, and cleanup are reflected without adding a
  new cross-feature cache invalidation mechanism.
- Keep the current selected trigger value if option loading fails.
- Show clear loading, empty, request-error, and retry states in the option
  panels.
- Allow each dropdown to close after a committed selection, on outside
  interaction, and with `Escape`.
- Support keyboard operation, visible focus, appropriate accessible names,
  focus behavior, and ARIA expanded state.
- Preserve the existing `orgId`-keyed provider reset behavior when the active
  organisation changes.
- Keep scenario and organisation-state ids out of the URL. The current route
  and tab remain unchanged while `WorkspaceSelectionContext` carries the
  selected item ids.
- Do not change existing scenario or organisation-state API contracts.

## Acceptance Criteria

- [ ] Scenario and Org state are accessible dropdown controls instead of
      read-only spans.
- [ ] The Organisation dropdown continues to work without behavior or visual
      regressions.
- [ ] Opening Scenario renders scenarios on the left and the draft scenario's
      organisation states on the right.
- [ ] The Scenario dropdown distinguishes the active context from the draft
      scenario and organisation-state choices.
- [ ] Clicking a scenario in the left column loads only that scenario's states
      without changing active workspace context, the current route, or current
      tab data.
- [ ] The draft state defaults to the active state when valid, otherwise to the
      first state by target date.
- [ ] `Select` is disabled until a valid draft scenario/state pair is ready.
- [ ] Clicking `Select` commits both draft selections, closes the dropdown, and
      keeps the user on the current tab and URL.
- [ ] Cancelling or dismissing Scenario discards draft choices without changing
      the active context or current-tab data.
- [ ] Org state is disabled when no scenario is selected.
- [ ] Opening Org state loads only the organisation states belonging to the
      currently selected scenario.
- [ ] Organisation states are ordered by target date and the selected state is
      marked.
- [ ] Selecting another organisation state updates workspace context and
      refreshes state-dependent content while preserving the selected scenario,
      current tab, and URL.
- [ ] Changing the draft or committed scenario clears organisation-state
      choices belonging to the previous scenario immediately.
- [ ] A late response for a previously selected scenario cannot expose or
      select that scenario's organisation states.
- [ ] Context-dependent tabs refetch or recompute for the new context without
      displaying stale data from the previous context.
- [ ] Selecting the already active context does not cause an unnecessary data
      refetch.
- [ ] Loading, empty, request-error, and retry states are presented clearly.
- [ ] A failed option request does not clear the current workspace selection.
- [ ] Both dropdowns support keyboard interaction; Scenario closes after
      `Select`, Org state closes after choosing a state, and both close on
      outside interaction or with `Escape`.
- [ ] Dropdown triggers expose appropriate accessible names and expanded state,
      and interactive elements have visible focus treatment.
- [ ] The current organisation name and active tab remain unchanged during
      scenario and organisation-state switching.
- [ ] Switching organisation still resets scenario and organisation-state
      selections through the existing provider behavior.
- [ ] Existing scenario selection, default selection, editing, copying,
      deletion, cleanup, and navigate-away-and-return restoration continue to
      work.
- [ ] Frontend tests cover draft and committed selection, route preservation,
      scenario-scoped state choices, current-tab refresh, stale-response
      protection, error states, and accessibility-critical behavior.
- [ ] No backend, database, API-contract, route-schema, domain-rule, or
      dependency changes are introduced.

## Out Of Scope

- Changes to scenario or organisation-state backend routes, services, schemas,
  validation, lifecycle, or authorization.
- Database schema, migration, seed, or physical data-model changes.
- Persisting scenario or organisation-state selection across a browser refresh
  or new browser session.
- Adding scenario or organisation-state ids to workspace URLs or introducing
  deep-link routes for selected items.
- Navigating to the Scenarios tab as a side effect of a header context change.
- Moving complete scenario or organisation-state collections into
  `WorkspaceSelectionContext` or another global store.
- Scenario or organisation-state create, rename, copy, delete, or cleanup
  actions inside the header dropdowns.
- Redesigning the Scenarios tab, workspace tab bar, or organisation selector.
- Changing automatic first-scenario or first-organisation-state selection
  rules outside the Scenario dropdown's draft-state initialization.
- Adding dependencies.

## Implementation Notes

Read these before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/TESTING.md
docs/domains/ORG_STATES.md
docs/concepts/SCENARIO.md
docs/concepts/ORGANISATION_STATE.md
tasks/TASK-005-scenarios-tab-ui.md
tasks/TASK-022-scenarios-tab-ui-fixes.md
tasks/TASK-033-restore-selected-scenario-form.md
tasks/TASK-034-organisation-context-dropdown.md
```

Likely implementation targets:

```text
frontend/src/pages/Workspace.tsx
frontend/src/components/ContextSelectionDropdown.tsx
frontend/src/components/ScenarioDropdown.tsx
frontend/src/components/OrgStateDropdown.tsx
frontend/src/workspace/WorkspaceSelectionContext.tsx
frontend/src/workspace/WorkspaceSelectionProvider.tsx
frontend/src/features/scenarios/ScenariosTab.tsx
frontend/src/features/structure/StructureTab.tsx
frontend/src/features/events/EventsTab.tsx
frontend/src/features/metrics/MetricsTab.tsx
frontend/src/features/summary/SummaryTab.tsx
frontend/src/styles/components.css
frontend/src/styles/app.css
frontend/src/App.test.tsx
```

Only change context-dependent tab components when inspection or regression
tests show that their existing context-keyed effects do not already provide the
required refetch or recomputation behavior. Avoid mechanical changes to tabs
that already react correctly.

The exact component split is an implementation detail. Prefer a small shared
selection-dropdown presentation component when it removes duplicated trigger,
panel, dismissal, focus, loading, and error behavior. Keep scenario and
organisation-state fetching and selection rules explicit in focused wrapper
components or workspace callbacks.

`WorkspaceSelectionProvider` remains mounted while child workspace routes stay
unchanged. The Scenario dropdown must keep its preview selection in component
state and commit the scenario and organisation state only from `Select`.
Prefer a single context operation for committing a complete scenario/state pair
if separate setters could expose consumers to a transient combination of the
new scenario and old state. Existing setters may remain available for current
Scenarios-tab flows. Do not put dropdown inventories or draft choices into the
shared context.

Do not use `useNavigate` for scenario or organisation-state selection. Do not
replace history state or change the organisation display fallback. Do not
introduce new route parameters or a second selection store.

Fetch lists on dropdown opening rather than retaining long-lived option data.
The Scenario dropdown must load right-column states whenever its draft scenario
changes. Use `AbortController` and an ignore/latest-request guard for both
dropdown data and active-tab data where necessary. A committed scenario change
must close or invalidate an open standalone Org state panel and discard its
previous choices.

Treat the selected context ids as request keys in context-dependent tabs.
Changing those keys must cancel or supersede previous work, clear data that
would otherwise be misleading, and load the data required by the new context.
Do not add a generic refresh counter when existing effect dependencies can model
the context change directly.

`ScenariosTab` needs special attention because it owns local DTO lists, selected
row details, edit fields, and fork defaults. When the header commits context
while Scenarios is already active, reconcile those local values with the new
context just as carefully as on remount, without overwriting later user edits on
unrelated rerenders.

The existing API client already exposes `fetchScenarios` and `fetchOrgStates`;
no API-client production change or API-client test is expected unless
implementation reveals a genuine missing behavior.

No ADR is expected because this uses the current frontend architecture,
dependencies, routes, context, and backend contracts. No backend, data,
domain, concept, or diagram documentation change is expected.

## Testing

Required:

- [ ] Frontend component and routing tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck through the existing frontend build

Not applicable:

- [ ] Backend tests: existing read endpoints and domain behavior are reused
      without changes.
- [ ] Database tests: no schema, migration, persistence, or lifecycle behavior
      changes.
- [ ] API-client tests: existing typed read operations are reused without
      modification.
- [ ] New end-to-end tooling: existing React integration-style tests and manual
      verification cover this scoped workflow.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Frontend tests should cover:

- Scenario and Org state rendering as dropdown triggers instead of read-only
  spans.
- Two-column Scenario layout, active-versus-draft indication, and initial draft
  restoration.
- Clicking a left-column scenario loading only that scenario's right-column
  states without committing context.
- Right-column target-date ordering, state choice, exact `Select` label, and
  disabled `Select` behavior while no complete choice is ready.
- `Select` committing the scenario/state pair together while preserving the
  current pathname, active tab, and organisation display name.
- Scenario dropdown dismissal discarding drafts without context changes or
  current-tab requests.
- Org state being disabled without a selected scenario.
- Org-state requests using only the currently selected scenario's stable id.
- Org-state target-date ordering, selected indication, immediate switching, and
  current-route preservation.
- A delayed old-scenario response being ignored after the scenario changes.
- Structure refetching state-scoped data after either selection path changes its
  scenario/state request key.
- Events and Metrics refetching after the Scenario picker commits a different
  scenario.
- Summary refetching after a scenario change and recomputing its selected-state
  presentation after an org-state-only change.
- Scenarios reconciling rows and detail/form state when context is committed
  while that tab is already active.
- No unnecessary current-tab fetch when the committed pair or clicked
  standalone state is already active.
- Loading, empty, API-error, retry, `Escape`, outside-interaction, focus, and
  accessibility-critical behavior.
- Existing navigate-away-and-return restoration and organisation-switch reset
  behavior remaining intact.

Manual verification should cover:

- On Structure, preview several scenarios and states, dismiss the dropdown, and
  verify neither the context nor graph changes before `Select`.
- On Structure, commit another scenario/state pair and verify the URL stays on
  Structure while the graph reloads for the new pair.
- On Structure, switch only Org state and verify the graph reloads without a
  route or scenario change.
- Repeat a scenario switch on Events, Metrics, Summary, and Scenarios, checking
  that each current tab stays active and refreshes or reconciles only the data
  affected by its context dependencies.
- Switch between scenarios with visibly different state lists and verify both
  dropdowns never show states from the wrong scenario.
- Exercise both dropdowns with keyboard-only input, including cancellation
  with `Escape` and focus restoration.
- Verify loading, empty, and request-error displays.
- Check header wrapping and panel placement at the existing narrow responsive
  breakpoints.
- Switch organisation and confirm both context selections reset.

## Documentation

This task file documents the approved scope. No architecture, ADR, domain,
concept, data, database, API, or diagram documentation update is expected
because the implementation exposes existing selection and current-tab refresh
behavior without changing its meaning or ownership.

Update other documentation only if implementation reveals a genuine mismatch
in the current documented route, selection, or API behavior.

## Notes For AI Agent

- Lue `AGENTS.md`, tämä task, `ARCHITECTURE.md`, `docs/TESTING.md` sekä taskissa
  luetellut relevantit domain-, concept- ja aiemmat task-dokumentit ennen
  toteutusta.
- Toteuta vain tämän taskin scope.
- Säilytä scenario- ja organisation-state-valintojen vakaat id:t
  `WorkspaceSelectionContext`-kontekstissa.
- Pidä Scenario-dropdownin luonnosvalinnat paikallisina ja päivitä aktiivinen
  scenario ja organisation state yhdessä vasta `Select`-painikkeesta.
- Älä navigoi toiselle välilehdelle scenario- tai organisation-state-valinnan
  seurauksena.
- Älä näytä organisation stateja, joita ei ladattu nykyisen valitun scenarion
  tai Scenario-dropdownissa esikatsellun scenarion endpointista.
- Suojaa organisation-state-lataus vanhentuneilta vastauksilta.
- Varmista, että nykyinen kontekstiriippuvainen välilehti hakee tai laskee
  sisältönsä uudelleen uuden valinnan mukaisesti eikä näytä vanhaa vastausta.
- Älä muuta backendia, API-sopimusta, reittiskeemaa, tietokantaa, migraatioita,
  domain-sääntöjä tai autentikointia tässä taskissa.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Lisää frontend-regressiotestit luonnosvalinnalle, vahvistetulle valinnalle,
  reitin säilymiselle ja nykyisen välilehden datan päivittymiselle.
- Jos toteutus vaatii arkkitehtuuri- tai reittimallin muutoksen, pysähdy ja pyydä
  ihmisen päätös ennen koodausta.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
