# TASK-075B Searchable Edge Node Dropdowns

## Source Plan

Developer-approved plan (2026-11-05) for three Structure page tasks, done in
this order: TASK-075A, TASK-075B (this task), TASK-075C. They edit some of the
same files, so they land one after another. TASK-075C reuses the component
added here.

The developer asked to update the edge Source and Target dropdowns on the
Structure page so that the options can be searched (filtered) in the
dropdown, with an "×" on the right of the search field that clears the entered
query.

## Goal

The Source and Target dropdowns of the Create edge and Edit edge forms let the
user filter the node list by typing. The control is a small reusable
component, built without new dependencies.

### Background

- `frontend/src/features/structure/EdgeForm.tsx` renders Source and Target as
  native `<select>` elements. Their options are all nodes of the selected org
  state, labelled by node name.
- In create mode the selects start with "Select source node" and "Select
  target node". Clicking two nodes in the graph fills Source and Target,
  through `createEdgeDraft` in `StructureTab.tsx`. In edit mode the values are
  always set.
- The app has no searchable dropdown or combobox component, and new
  dependencies need approval.
- `.structure-editor-panel` (`frontend/src/styles/app.css`) has
  `overflow: auto`, so an absolutely positioned popover inside it can be
  clipped.

## Requirements

### Component

Add `frontend/src/components/SearchableSelect.tsx`.

- **Props:**
  - `id`;
  - `options: { value: string; label: string }[]`;
  - `value` and `onChange(value: string)`;
  - `placeholder`, shown when `value` is empty or not among the options;
  - `searchLabel`, the accessible name of the search field, for example
    "Search source nodes";
  - optional `searchPlaceholder`, default "Search…";
  - optional `noMatchesText`, default "No matches";
  - optional `disabled`.
- **Closed:**
  - a `<button type="button">` with the given `id`, so an existing
    `<label htmlFor>` names it;
  - it looks like the current `.select`, caret included;
  - it shows the selected option's label or the placeholder, and has
    `aria-haspopup="listbox"` and `aria-expanded`.
- **Opening:** click, Enter, Space or ArrowDown on the trigger opens a panel
  with a search field at the top and the option list below it. Focus moves to
  the search field.
- **Search field:**
  - a text input with `role="combobox"`, `aria-expanded="true"`,
    `aria-controls` pointing at the list, `aria-autocomplete="list"` and
    `aria-activedescendant` for the highlighted option;
  - while the query is not empty, an "×" button on the right of the field,
    with the accessible name "Clear search";
  - the "×" button clears the query, keeps the current selection and returns
    focus to the search field.
- **Filtering:** a case-insensitive substring match of the trimmed query
  against the option label. An empty query shows every option. The option
  order does not change.
- **List:**
  - `role="listbox"` with `role="option"` items, and `aria-selected` on the
    current value;
  - the current value is highlighted when the list opens;
  - when nothing matches, the list shows `noMatchesText` as a plain row, not
    an option;
  - the list scrolls past a maximum height of about 240px.
- **Keyboard:**
  - ArrowDown and ArrowUp move the highlight and stop at the ends;
  - Enter selects the highlighted option;
  - Escape closes without a change and returns focus to the trigger;
  - Tab closes.
- **Mouse:** clicking an option selects it. Clicking outside the component
  closes it.
- **After selecting:** the component calls `onChange`, closes, clears the
  query and returns focus to the trigger.
- **Disabled:** the trigger is disabled and the panel cannot open.
- **Clipping:** the open panel must not be clipped by the scrollable editor
  panel. An in-flow panel that pushes the content below it down is
  acceptable.
- **Styles:** in `frontend/src/styles/components.css`, using the existing
  tokens and the same focus-visible treatment as `.select`.

### Edge Form

- Replace the Source and Target `<select>` elements in `EdgeForm.tsx` with
  `SearchableSelect`. The options are `props.nodes` as
  `{ value: node.id, label: node.name }`.
- The labels "Source" and "Target" stay unchanged and still name the
  controls.
- Create mode uses the placeholders "Select source node" and "Select target
  node", and the search labels "Search source nodes" and "Search target
  nodes".
- The list has no empty option. Today the create-mode placeholder can be
  chosen again to clear a selection. This task drops that, because picking
  another node or clicking the graph replaces the selection.
- Graph clicks still fill Source and Target. The controlled and uncontrolled
  logic, the self-reference check and its tooltip, and the disabled states are
  unchanged.
- The Type select stays a native `<select>`.

## Acceptance Criteria

- [ ] Opening Source or Target in Create edge or Edit edge shows a search
      field and every node.
- [ ] Typing filters the list case-insensitively. "No matches" appears when
      nothing matches.
- [ ] The "×" button appears only while the query is not empty, clears the
      query and keeps the selected node.
- [ ] A node can be chosen with the mouse, and with ArrowDown/ArrowUp and
      Enter. Escape closes without a change.
- [ ] Clicking two nodes in the graph still fills Source and Target in Create
      edge.
- [ ] Self-referencing create edges are still blocked with the same tooltip.
- [ ] The open list is not clipped by the editor panel at 1280px and 700px
      widths.
- [ ] No new dependencies.

## Out Of Scope

- The Type select and other dropdowns in the application.
- Showing the node type next to the node name in the options.
- Grouping, sorting or virtualising the option list.
- Backend or API changes.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/TESTING.md
```

- Files expected to change:
  - `frontend/src/components/SearchableSelect.tsx` (new) and
    `SearchableSelect.test.tsx` (new);
  - `frontend/src/features/structure/EdgeForm.tsx`;
  - `frontend/src/styles/components.css`;
  - `frontend/src/features/structure/StructureTab.test.tsx`.
- Some existing Structure tests read Source and Target with `toHaveValue` or
  set them with `fireEvent.change`, around lines 509-580 and 878-890. Rewrite
  them with a small helper that opens the control and clicks an option, and
  assert on the trigger text instead of a value.
- Keep the component generic. TASK-075C uses it for the timeserie link
  dropdowns.
- No new dependencies, ADR or diagram changes.

## Testing

Required:

- [ ] Frontend tests:
  - `SearchableSelect.test.tsx`:
    - placeholder and selected label;
    - opening and closing;
    - filtering and "No matches";
    - "×" visibility and behaviour;
    - keyboard selection, Escape and outside click;
    - the controlled `value`;
    - the disabled state;
  - `StructureTab.test.tsx`:
    - Create edge with nodes chosen through the dropdowns;
    - graph clicks filling Source and Target;
    - the self-reference block;
    - Edit edge changing the target.
- [ ] Manual verification at `https://app.localhost`: create and edit an edge
      by searching, check keyboard use and the "×" button at 1280px and
      700px.
- [ ] Format check
- [ ] Lint
- [ ] Build (includes the TypeScript check, `tsc -b`)

Not applicable:

- [ ] Backend tests. Reason: frontend-only change.

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

- No documentation changes. The domain documents do not describe the form
  controls.

## Notes For AI Agent

- Start after TASK-075A is merged. Use the branch
  `feature/TASK-075B-searchable-edge-node-dropdowns` from `main`.
- Implement only this task's scope.
- Do not add dependencies.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-075B/`.
- Report all changed files and every verification command run.
