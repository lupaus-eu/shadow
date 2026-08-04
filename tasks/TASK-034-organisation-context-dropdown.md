# TASK-034 Organisation Context Dropdown

## Source Plan

Developer-approved plan: replace the read-only organisation context chip in the
workspace header with a dropdown that lets the user switch, rename, soft delete,
and add organisations.

The accepted plan reuses the existing organisation list, create, patch, and
delete backend endpoints. It keeps the change frontend-focused, uses the current
workspace routing and selection reset behavior, and adds explicit destructive
confirmation before soft deletion.

## Goal

Make the organisation shown in the workspace header an interactive context
selector so the user can manage and change the active organisation without
returning to the home page.

The dropdown must support safe inline rename, creation, and soft deletion while
keeping the URL, displayed organisation name, session-storage fallback, and
workspace selection state consistent with the active organisation.

## Requirements

- Replace only the read-only Organisation context chip in the workspace header
  with an accessible dropdown trigger.
- Keep the Scenario and Org state context chips read-only.
- Load active organisations through `GET /api/v1/organisations` when the
  workspace organisation control is initialised.
- Display organisations alphabetically and visibly mark the organisation whose
  stable key matches the current `orgId` route parameter.
- Allow the dropdown to close after selection, on outside interaction, and with
  `Escape`.
- Support keyboard operation and appropriate accessible names, focus behavior,
  and ARIA state for the dropdown and its controls.
- When another organisation is selected:
  - navigate to `/schatten/:orgId/:tabSignature` for the selected organisation,
  - preserve the current tab signature where practical,
  - pass the selected organisation name in navigation state,
  - update the session-storage display fallback,
  - allow the existing provider keyed by `orgId` to reset scenario and
    organisation-state selections,
  - close the dropdown.
- If the preserved tab requires a scenario and organisation state, keep the
  existing unselected-tab behavior until the user selects context for the new
  organisation.
- Add an icon-only pen button for the current organisation with the accessible
  name `Rename organisation`.
- Use an inline SVG or existing code-native icon treatment for the pen icon; do
  not add an icon dependency.
- Clicking the pen button must open an inline rename form that:
  - is pre-filled with the current organisation name,
  - focuses the name input,
  - provides Save and Cancel controls,
  - disables Save for a blank or unchanged trimmed name,
  - prevents duplicate submission while the request is pending,
  - displays backend validation, duplicate-name, and other request errors
    without closing the editor.
- Submit rename through
  `PATCH /api/v1/organisations/{organisation_key}` with `{ "name": string }`.
- After a successful rename, update the organisation list, dropdown trigger,
  navigation state, and session-storage display fallback without changing the
  stable organisation key.
- Add an icon-only red trash-bin button for the current organisation with the
  accessible name `Delete organisation`.
- Use an inline SVG or existing code-native icon treatment for the trash-bin
  icon; do not add an icon dependency.
- Clicking the trash-bin button must show a destructive confirmation panel in
  the dropdown that:
  - clearly names the organisation being deleted,
  - provides a confirmation input,
  - uses the exact placeholder `Type DELETE to confirm`,
  - provides Cancel and red `Delete organisation` buttons,
  - keeps `Delete organisation` disabled until the input value is exactly the
    case-sensitive string `DELETE`,
  - prevents duplicate submission while the request is pending,
  - displays deletion errors without closing the confirmation panel.
- Confirmed deletion must call
  `DELETE /api/v1/organisations/{organisation_key}` and rely on the backend's
  existing soft-delete behavior.
- After successful deletion:
  - remove the deleted organisation from the local list,
  - remove its session-storage organisation-name fallback,
  - select and navigate to another active organisation when one remains,
  - navigate to `/` when no active organisation remains,
  - reset and close the deletion UI.
- Add an `Add organisation` button at the bottom of the dropdown, visually
  separated from the organisation list.
- The add action must open a compact inline creation form that:
  - requires a nonblank trimmed organisation name,
  - uses the existing `POST /api/v1/organisations` endpoint,
  - prevents duplicate submission while pending,
  - displays duplicate-name and other backend errors,
  - adds the returned organisation to the sorted list,
  - selects and navigates to the newly created organisation,
  - resets and closes the form after success.
- Keep the existing home-page organisation selection and creation flow.
- Extend the typed frontend organisation API client with patch and delete
  operations, reusing its API URL construction and error parsing.
- URL-encode organisation keys in patch and delete paths.
- Reuse existing design tokens and shared button, input, and alert styles where
  suitable.
- Do not add dependencies.

## Acceptance Criteria

- [ ] The workspace header Organisation control is an accessible dropdown rather
      than a read-only span.
- [ ] Scenario and Org state remain read-only context chips.
- [ ] The dropdown lists active organisations alphabetically and marks the
      current organisation.
- [ ] Selecting an organisation updates the route and displayed organisation.
- [ ] Switching organisation resets scenario and organisation-state selections
      through the existing `orgId`-keyed workspace provider behavior.
- [ ] The current tab is preserved where practical when switching organisations.
- [ ] The dropdown supports keyboard interaction and closes on selection,
      outside interaction, and `Escape`.
- [ ] The pen-icon button has the accessible name `Rename organisation` and
      opens a focused inline name editor.
- [ ] Rename Save is disabled for a blank or unchanged trimmed name.
- [ ] Successful rename uses `PATCH`, keeps the stable organisation key, and
      immediately updates all displayed and cached name values.
- [ ] Rename errors, including duplicate active names, are shown clearly and do
      not discard the entered value.
- [ ] The trash-bin button is styled as destructive, has the accessible name
      `Delete organisation`, and opens a confirmation panel.
- [ ] The delete confirmation input has the exact placeholder
      `Type DELETE to confirm`.
- [ ] `Delete organisation` remains disabled until exact uppercase `DELETE` is
      entered.
- [ ] Confirmed deletion calls the existing delete endpoint and removes the
      soft-deleted organisation from the available list.
- [ ] Deleting the selected organisation navigates to another active
      organisation when one remains.
- [ ] Deleting the final active organisation navigates to `/`.
- [ ] Failed deletion keeps the confirmation available and shows the error.
- [ ] An `Add organisation` action is present at the bottom of the dropdown.
- [ ] A newly created organisation is added, selected, and opened after a
      successful create request.
- [ ] Create errors are shown clearly without losing the entered name.
- [ ] Pending rename, delete, and create operations cannot be submitted twice.
- [ ] Existing home-page organisation behavior remains unchanged.
- [ ] Frontend tests cover switching, rename, soft-delete confirmation, deletion
      fallback, creation, errors, and accessibility-critical labels.
- [ ] No backend contract, database schema, domain rule, or dependency changes
      are introduced.

## Out Of Scope

- Changes to organisation backend routes, services, schemas, or soft-delete
  semantics.
- Database schema, migration, seed, or physical data-model changes.
- Hard deletion or cascading deletion of organisation-owned records.
- Changes to membership, authentication, or authorization behavior.
- Managing organisations other than the currently selected organisation from
  the rename and delete controls.
- Redesigning Scenario or Org state context selection.
- Removing or redesigning the home-page organisation flow.
- Adding an icon, dropdown, popover, or state-management dependency.
- Broad workspace routing or header redesign beyond the organisation control.

## Implementation Notes

Read these before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/TESTING.md
docs/domains/ORGANISATIONS.md
docs/concepts/ORGANISATION.md
tasks/TASK-003-schatten-ui-shell.md
tasks/TASK-014-users-organisations-backend-crud.md
tasks/TASK-015-organisation-defaults-frontend-flow.md
```

Likely implementation targets:

```text
frontend/src/pages/Workspace.tsx
frontend/src/components/OrganisationDropdown.tsx
frontend/src/api/organisations.ts
frontend/src/styles/app.css
frontend/src/styles/components.css
frontend/src/App.test.tsx
frontend/src/api/organisations.test.ts
```

The organisation dropdown should be a custom button and anchored menu/popover,
not a native `select`, because each current-organisation row also needs rename
and delete actions and the footer needs an inline creation flow.

Keep canonical organisation identity in the route's stable `orgId`. Use the
organisation returned by the list API as the preferred display value after
loading; retain navigation state and session storage only as the existing
display fallback during loading or request failure.

When switching or creating an organisation, derive the current tab signature
from the workspace route and navigate to the equivalent route under the new
organisation key. `WorkspaceSelectionProvider` is already keyed by `orgId`, so
changing the route key resets scenario and organisation-state context. Do not
introduce another global selection store for this task.

After rename, keep local organisation state and session storage synchronised.
If necessary, replace the current history entry's navigation state so later tab
navigation cannot restore the old name.

After deletion, choose a deterministic fallback from the remaining
alphabetically sorted organisations. If there is no remaining organisation,
navigate to the existing home page, which already contains an empty and create
flow.

The backend already implements and tests:

```text
GET    /api/v1/organisations
POST   /api/v1/organisations
PATCH  /api/v1/organisations/{organisation_key}
DELETE /api/v1/organisations/{organisation_key}
```

The existing backend enforces trimmed nonblank names, active case-insensitive
name uniqueness, and soft deletion. Frontend checks improve usability but do
not replace backend validation.

Prefer extracting the interactive organisation control from `Workspace.tsx`
into a focused component. Keep data ownership and callbacks explicit so route
navigation remains in the workspace layer if that produces a clearer boundary.

Ensure icon-only controls have visible focus treatment, accessible names, and
tooltip/title text where consistent with the existing UI. Manage focus when
opening and closing rename, create, and delete modes, and return focus to the
initiating control after cancellation where practical.

No ADR is expected because this uses existing architecture, dependencies,
routes, and domain behavior. No backend or database documentation change is
expected.

## Testing

Required:

- [ ] Frontend API-client tests
- [ ] Frontend component and routing tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck through the existing frontend build

Not applicable:

- [ ] Backend tests: the existing backend API contract and domain behavior are
      reused without changes.
- [ ] Database tests: no schema, migration, persistence, or soft-delete rule is
      changed.
- [ ] New end-to-end tooling: existing React integration-style tests and manual
      verification cover this scoped workflow.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Frontend API-client tests should cover:

- patch method, URL-encoded organisation key, JSON body, and returned DTO
- delete method, URL-encoded organisation key, and `204 No Content`
- parsed backend errors for rename and delete failures

Frontend component and routing tests should cover:

- loading, sorting, opening, closing, and current-organisation indication
- switching to another organisation and updating the route
- workspace scenario and org-state context reset after `orgId` changes
- current-tab preservation, including the existing unavailable-context state
- successful rename and immediate trigger, list, navigation-state, and storage
  update
- blank, unchanged, duplicate-name, and failed rename behavior
- delete confirmation opening, cancellation, and exact case-sensitive `DELETE`
  requirement
- successful delete with another organisation remaining
- successful delete of the final organisation
- failed deletion and repeat-submission prevention
- creating and selecting an organisation from the dropdown
- duplicate-name and failed creation behavior
- accessible names for the dropdown, pen, trash-bin, form, and confirmation
  controls
- no regressions in the existing home-page organisation flow

Manual verification should cover:

- switch between at least two organisations from each type of workspace tab
- verify scenario and organisation-state context clears after a switch
- rename the selected organisation and navigate between tabs to confirm the new
  name persists
- cancel and complete deletion, checking the exact confirmation requirement
- delete when another organisation remains and when deleting the final one
- add an organisation from the dropdown and verify its default workspace opens
- exercise dropdown, inline forms, and cancellation using only the keyboard
- check the header and dropdown at the existing narrow responsive breakpoint

## Documentation

This task file documents the approved scope. No architecture, ADR, domain,
concept, data, database, or diagram documentation update is expected because
the implementation will expose existing organisation lifecycle operations
without changing their meaning or ownership.

Update documentation only if implementation reveals that the current documented
API contract or organisation lifecycle differs from actual behavior.

## Notes For AI Agent

- Lue `AGENTS.md`, tämä task, `ARCHITECTURE.md`, relevantit organisation-domain-
  ja concept-dokumentit sekä `docs/TESTING.md` ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Säilytä `organisation_key` vakaana ulkoisena tunnisteena.
- Käytä backendin olemassa olevaa soft delete -operaatiota; älä lisää hard
  deletea tai cascade-käyttäytymistä.
- Älä muuta autentikointia tai authorizationia tässä taskissa.
- Älä lisää riippuvuuksia ilman erillistä hyväksyntää.
- Lisää testit kaikille uusille API-client- ja UI-poluille.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
