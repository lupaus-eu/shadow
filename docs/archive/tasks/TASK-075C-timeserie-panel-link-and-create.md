# TASK-075C Timeserie Panel Link And Create

## Source Plan

Developer-approved plan (2026-11-05) for three Structure page tasks, done in
this order: TASK-075A, TASK-075B, TASK-075C (this task). This task uses
`SearchableSelect` from TASK-075B.

The developer reported:

- filling in only the Primary or Secondary link and clicking "Save links"
  shows two identical alerts, "API request failed (404).
  {"detail":"Timeserie not found."}", one above the graph and one below the
  button. There should be only one;
- the link editor is not intuitive, because a link can only be set to a
  timeserie that already exists;
- the timeserie ids below "Primary" and "Secondary" should be editable when a
  timeserie is created, keeping the current defaults `id1` and `id2`.

The developer decided:

1. Replace the free-text link inputs with dropdowns that list existing
   timeseries, with the placeholder "Select existing timeseries id". Keep the
   save button as "Save link(s)", disabled when neither dropdown has a
   selection. Rename the "Timeserie" heading to "Link to existing
   timeserie(s)" and add a "Create/edit timeserie(s)" heading above the
   Primary status card. The status cards keep reacting to the link selection
   as they do now.
2. A timeserie created with its type default id is not linked explicitly; the
   node keeps inheriting the default.
3. A slot without a type default gets a create form with an empty, required
   id.
4. Fix the duplicate alert in every Structure editor form (Create/Save node,
   Create/Save edge), not only in the timeserie panel.
5. Add an "Unlink" button, visible only on linked timeseries.
6. Show the name of an existing timeserie on its status card (added
   2026-11-05 during implementation).
7. The Structure editor panel must not scroll horizontally (added 2026-11-05
   during implementation, after the taller panel showed a horizontal
   scrollbar).
8. Each link dropdown gets a "Clear" button that removes its pending
   selection (added 2026-11-05 after AI review finding F-002).
9. The node and edge form actions clear the page-level "Structure save error"
   when they start, but never set it (added 2026-11-05 after AI review
   finding F-008).
10. A failed node or edge delete no longer causes an unhandled rejection: the
    delete confirmation catches it and stays open, and the page-level
    "Structure save error" shows it (added 2026-11-05 after AI review finding
    F-004, so that the failed delete can be tested).

## Goal

A user links a node to existing timeseries by choosing them from a list, and
creates new timeseries with an id of their choice. Every failed action in the
Structure editor shows exactly one alert, next to the control that failed.

### Background

- `TimeseriePanel.tsx` has free-text "Primary link" and "Secondary link"
  inputs and a "Save links" button that patches the node through `updateNode`
  in `StructureTab.tsx`.
- The backend resolves link keys with `_resolve_optional_timeserie_id`
  (`org_twin_structure_service.py`). It returns 404 "Timeserie not found." for
  a key that does not exist in the scenario, so typing a new id and saving
  always fails.
- **Duplicate alerts:**
  - `createNode`, `updateNode`, `createEdge` and `updateEdge` in
    `StructureTab.tsx` set `actionError`, shown above the graph as "Structure
    save error", and then rethrow;
  - `NodeForm`, `EdgeForm` and `TimeseriePanel` catch the same error and show
    it again;
  - inside the panel, `createMissingTimeserie` sets `panelError` and
    rethrows, and `MissingTimeserieForm` shows the error a second time.
- **Type defaults:** node type metadata provides default ids
  (`timeserieId`/`timeserieSecondaryId`, seeded as `id1`/`id2`). A node without
  its own link inherits them.
- **Links always point to existing timeseries:** deleting a timeserie clears
  every link to it, in the backend and in `clearDeletedTimeserieLinks`. So
  "Missing" appears only for an inherited default or a slot with no id.
- **Node patch:** a node patch may send only one slot, `timeserieId` or
  `timeserieSecondaryId`. `null` clears that slot.
- **Existing timeseries:** `fetchTimeseries(orgId, scenarioId)`
  (`frontend/src/api/timeseries.ts`) lists the scenario's active timeseries,
  derived metrics included. Creating a timeserie with an id that already
  exists returns 409 "An active timeserie with this id already exists."
- **Timeserie names:** the existence check `fetchTimeserieExists` returns the
  id, existence and short name, but not the name. The `fetchTimeseries` list
  has every active timeserie's name.
- **Remounting:** `StructureTab` keys the panel on the node id and both links,
  so the panel remounts whenever a link changes.

## Requirements

### Panel Layout

From top to bottom, the panel has two labelled regions.

1. **"Link to existing timeserie(s)" region:**
   - The heading is "Link to existing timeserie(s)" and replaces "Timeserie".
   - The "Primary link" and "Secondary link" controls are `SearchableSelect`
     components:
     - placeholder "Select existing timeseries id";
     - search labels "Search primary timeseries" and "Search secondary
       timeseries";
     - options are all active timeseries of the selected scenario, sorted by
       id, labelled `{id} – {name}`, with the id as the value;
     - the list loads with `fetchTimeseries` when the panel mounts and is
       aborted on unmount;
     - the dropdowns are disabled while the list loads;
     - if loading fails, the dropdowns stay disabled and this region shows
       one closable alert. The create/edit region still works.
   - Next to each dropdown, a secondary "Clear" button:
     - removes that dropdown's pending selection, so the dropdown shows the
       placeholder and the status card shows the saved link or type default
       again;
     - is named "Clear primary link selection" or "Clear secondary link
       selection";
     - is disabled while its dropdown has no selection or is disabled.
   - The "Save link(s)" button:
     - is disabled while neither dropdown has a selection, while saving, and
       while the panel is disabled;
     - sends only the selected slot or slots through `onUpdateLinks`;
     - on success, resets both dropdowns to the placeholder;
     - on failure, shows one alert below the button.
   - The Rule block is unchanged and shown as now.
2. **"Create/edit timeserie(s)" region:** the heading, then the Primary and
   Secondary status cards. Both headings use the same `section-title` style.

### Status Cards

- **Effective id:** each card shows the effective id of its slot, taken from
  the first of these that is set:
  1. the unsaved dropdown selection;
  2. the node's saved link;
  3. the type default.

  If none is set, the card shows "No id".
- **Preview:** the cards update as soon as a dropdown selection changes, and
  existence checks run for the effective ids, as they do today for typed
  links.
- **Source and Default rows:** the Source row shows the node label for a
  selection or saved link and "Type default" for an inherited id. The Default
  row works as now.
- **Name row:**
  - a card whose timeserie exists shows a "Name" row with the timeserie's
    name, above the Source row;
  - the name comes from the panel's `fetchTimeseries` list, so a timeserie
    created or deleted in the panel updates it without a reload;
  - while the list loads, or if it failed to load, the Name row is not shown;
  - no backend or API change: the existence check stays as it is.
- **Unchanged:** Short name editing and Delete timeserie work as now.
- **Unlink:**
  - a secondary "Unlink" button in the card's action row;
  - shown only when the slot has a saved node link and no pending dropdown
    selection for that slot;
  - not shown for an inherited type default or a "No id" slot.
- **What Unlink does:**
  - it sends `{ timeserieId: null }` or `{ timeserieSecondaryId: null }` for
    that slot only, without confirmation;
  - the timeserie is not deleted and stays in the dropdown options;
  - afterwards the card shows the type default, as Exists or as Missing with
    the create form, or "No id".

### Creating A Timeserie

- **Id field:**
  - while a slot's effective timeserie is missing, or the slot has no id, the
    id below the slot heading becomes a required text input;
  - its accessible names are "Primary timeserie id" and "Secondary timeserie
    id", and it belongs to that slot's create form;
  - it is prefilled with the effective id (`id1` or `id2` by default), or left
    empty when the slot has none;
  - "Create timeserie" is disabled while the trimmed id or name is empty.
- **Submit:**
  1. create the timeserie with the trimmed id through `createTimeserie`;
  2. if the id differs from the slot's type default, link it with
     `onUpdateLinks`, sending only that slot. If it equals the default, make
     no link call.
- **Create succeeds but linking fails:**
  - the form shows one alert: "Timeserie {id} was created but could not be
    linked: {message}";
  - the form remembers the created id, and the next submit with the same id
    retries only the link;
  - changing the id makes the next submit create again.
- **Dropdown options:** a created timeserie is added to the options and a
  deleted one is removed, without reloading.
- **Existing id:** an id that already exists shows the backend's 409 message
  once, in the form. Linking an existing timeserie is done with the dropdowns.

### One Alert Per Error

- **Form-triggered actions:** `createNode`, `updateNode`, `createEdge` and
  `updateEdge` in `StructureTab.tsx` never set `actionError` to an error. They
  still clear it when they start, so an earlier position-save or delete error
  does not stay next to a new form error. They still rethrow, and the calling
  form shows the error.
- **Page-level alert:** `actionError` ("Structure save error" above the graph)
  stays for actions without a form-level error:
  - saving node positions (`commitPendingPositions`);
  - `removeNode`;
  - `removeEdge`.
- **Inside `TimeseriePanel`:**
  - `createMissingTimeserie` stops setting `panelError`; the create form shows
    the error;
  - link-save errors appear only in the link region;
  - Unlink, short-name and delete errors appear only in the create/edit
    region.
- **Failed deletes:** `NodeForm` and `EdgeForm` catch a failed `onDelete` and
  keep their delete confirmation open, so the delete can be retried or
  cancelled. The page-level alert is the only alert for it.
- **Exactly one alert:** each of these failures shows exactly one
  `role="alert"` element.

### Editor Panel Width

- The Timeserie panel is usually taller than the editor panel, so the editor
  panel shows a vertical scrollbar. Its content is then narrower than the
  Editor mode switch with four buttons, whose shared minimum width is 92px each.
- In the Structure editor only, the mode buttons fit their labels and may wrap
  as a last resort, so the editor panel never scrolls horizontally. The shared
  switch elsewhere (Scenarios, AI panel) is unchanged.

## Acceptance Criteria

- [ ] The panel has no free-text link inputs and no "Save links" text. It
      shows the "Link to existing timeserie(s)" and "Create/edit
      timeserie(s)" headings in that order.
- [ ] Both dropdowns show "Select existing timeseries id" and list the
      scenario's active timeseries.
- [ ] "Save link(s)" is disabled with no selection and enabled with either.
      It sends only the selected slots and resets the dropdowns afterwards.
- [ ] Choosing an option updates that slot's status card before saving.
- [ ] A card whose timeserie exists shows its name in a "Name" row, also for a
      timeserie just created in the panel. No Name row is shown for a missing
      timeserie or while the timeseries list is unavailable.
- [ ] "Unlink" appears only on a card with a saved node link and no pending
      selection. Clicking it clears only that slot, and the card falls back to
      the type default.
- [ ] Creating with the default id calls `createTimeserie` only. Creating with
      another id also links that slot only.
- [ ] After a link failure following a successful create, resubmitting
      retries only the link.
- [ ] A slot with no type default shows the create form with an empty,
      required id.
- [ ] Created and deleted timeseries appear in and disappear from the
      dropdown options without a reload.
- [ ] Each link dropdown's "Clear" button removes its pending selection. The
      card shows the saved link or type default again, and Unlink reappears
      for a saved link.
- [ ] Exactly one alert is shown for a failed:
      - link save, unlink, timeserie create, and link after create;
      - Create node, Save node, Create edge and Save edge.
- [ ] Failed position saves and deletes still show "Structure save error"
      once. A node or edge form action clears it when it starts. A failed
      delete keeps its confirmation open and causes no unhandled rejection.
- [ ] The Structure editor panel has no horizontal scrollbar with four editor
      modes and a vertical scrollbar, at desktop and narrow widths.
- [ ] No backend, API, migration or dependency changes.

## Out Of Scope

- A backend endpoint that creates and links a timeserie in one transaction.
- Changing node type default ids or the sharing of inherited defaults between
  nodes.
- Checking whether a typed id exists while the user types it.
- Restricting which timeseries can be linked, for example by unit or derived
  status.
- Other tabs' alerts.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/operations/testing.md
```

- Files expected to change:
  - `frontend/src/features/structure/TimeseriePanel.tsx`;
  - `frontend/src/features/structure/StructureTab.tsx`;
  - `frontend/src/features/structure/NodeForm.tsx` and `EdgeForm.tsx` (failed
    deletes, decision 10);
  - `frontend/src/features/structure/StructureTab.test.tsx`, or a new
    `TimeseriePanel.test.tsx`;
  - `frontend/src/styles/app.css` if the layout needs it.
- **Tests to rewrite:** "saves and clears selected node timeserie links", and
  the rule-context test that types into "Primary link". They should use the
  dropdowns and Unlink.
- **Reset after saving:** the panel remounts when a link changes, which resets
  the dropdowns and reloads the options. Saving an id that equals the current
  link does not change the key, so reset the dropdowns explicitly on success.
- **Id input placement:** the id input sits in the card header but belongs to
  the create form. Use the input's `form` attribute or lift its state.
- **Error owner:** keep one error state per region or form, so each failure
  has exactly one owner.
- **Size:** expect roughly 450-550 lines including tests.
- No new dependencies, ADR or diagram changes.

## Testing

Required:

- [ ] Frontend tests:
  - layout and headings;
  - dropdown options, the loading state and the load failure;
  - "Save link(s)" enablement and payloads, for primary only, secondary only
    and both;
  - card preview from a selection;
  - the Name row for an existing, a just-created and a missing timeserie, and
    without the timeseries list;
  - Unlink: visibility rules, payload and fallback to the type default;
  - the Clear buttons: enablement and clearing a pending selection;
  - create with the default id, with a custom id, and the retry after a link
    failure;
  - the "No id" slot create form;
  - option list updates after create and delete;
  - a single `role="alert"` for each failure listed in the acceptance
    criteria, including Create/Save node and Create/Save edge.
  - a form action clearing an earlier page-level "Structure save error";
  - a failed node and edge delete: one page-level alert, and the confirmation
    stays open;
- [ ] Manual verification at `https://app.localhost`:
  - link and unlink a metric node;
  - create a timeserie with the default id and with a custom id;
  - trigger a 409 by creating with an existing id;
  - check that each failure shows one alert.
- [ ] Format check
- [ ] Lint
- [ ] Build (includes the TypeScript check, `tsc -b`)

Not applicable:

- [ ] Backend tests. Reason: frontend-only change. The API already supports
      single-slot link patches, `null` and timeserie creation.

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

- `docs/architecture/domains/ORG_TWIN_STRUCTURE.md`, next to the paragraph on
  `timeserieId`, `timeserieSecondaryId` and `timeserieIdRule`, describe the
  Structure UI:
  - a node is linked to existing timeseries by choosing them;
  - a new timeserie gets an id that defaults to the type metadata, and an
    explicit link is stored only when it differs from the default;
  - Unlink returns a slot to its type default.
- No architecture, ADR, concept, data or diagram changes.

## Notes For AI Agent

- Start after TASK-075B is merged. Use the branch
  `feature/TASK-075C-timeserie-panel-link-and-create` from `main`.
- Implement only this task's scope.
- Do not add dependencies.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-075C/`.
- Report all changed files and every verification command run.
