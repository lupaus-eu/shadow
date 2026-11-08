# Feature: Structure canvas (full-width drawing tool)

> Vocabulary renamed by ADR-0052 on 2026-11-08: event is now Change, change (a step) is now Edit.

Status: accepted

## Goal

The Structure tab of a model becomes a proper drawing tool: it uses the whole page width,
supports pan, zoom and fit, and brings back the useful features of the first Shadow attempt
(`legacy/frontend/src/features/structure/`). A person can draw and read an organisation
graph of any size without leaving the canvas.

Today the canvas is a fixed 1400x800 SVG inside a page limited to `max-w-6xl`, with a side
panel for adding and editing. It has drag, select, and "connect from" through a form, but no
zoom, no fit, no filtering and no node-type shapes.

## User

- **Member, Owner, Admin**: draw and edit nodes and connections (everything the Structure tab
  does today).
- **Read-only Organization**: sees and navigates the canvas, cannot edit.
- **Agent**: unchanged; it works through MCP, not the canvas.

## Features carried over from the first attempt

Taken from the legacy inventory; items tied to the old data model are listed under "Not in
this version" with what replaces them.

| Legacy feature | In this PRD |
| --- | --- |
| Pan, zoom, "Zoom to Fit" (also after load) | Yes, improved (see Use case) |
| Canvas follows its container size | Yes (full width and height) |
| Node shapes and colours from the node type (ellipse, diamond, hexagon, rectangle, rounded) | Yes; `node_types.shape` exists but is not drawn yet |
| Edge line style (solid, dashed, dotted) and arrowheads from the connection type | Yes; dotted added if the type allows it |
| Hover popover with name and description | Yes |
| Names over 60 characters shortened with an ellipsis in labels | Yes |
| Left list of nodes grouped by type, colour tag, counts | Yes |
| Per-type visibility checkbox, Select all, Deselect all; hidden types hide their nodes and touching edges | Yes |
| Per-type collapse; empty types start collapsed | Yes |
| "+" per type: add a node of that type | Yes |
| Click a list row: select, centre and zoom to the node | Yes (180 ms animation) |
| New node placed at the viewport centre | Yes (replaces the grid placement) |
| Two clicks on nodes fill source and target of a connection | Yes, in addition to "connect from" |
| Self-referencing connections blocked with a reason | Yes (the server already refuses them) |
| Connection types offered only when the metamodel allows them | Yes, already enforced; the picker must show only allowed types for the two nodes |
| Delete asks for confirmation | Yes |
| Dismissible save and load alerts | Yes |
| Drag saves positions with a debounce | Yes, but through the existing optimistic `expected_version` update (no bulk API unless the design shows a need) |

## Use case

1. A Member opens the Structure tab. The canvas fills the page width and the height below
   the model header. The side panels sit over or beside it and can be collapsed.
2. The graph is fitted to the view on load. The person zooms with the wheel or pinch, with
   +/- buttons and a percentage readout, pans by dragging the background or with the space
   key, and presses "Fit" or "100 %" to reset.
3. They filter by node type in the left list, search a node by name, and click a result to
   centre on it.
4. They add a node from a type's "+" button: it appears at the viewport centre and its name
   is edited at once.
5. They connect two nodes by dragging from the first node's handle to the second, or by
   clicking "Connect" and then two nodes. The type is chosen among those the metamodel allows;
   a refused connection says why.
6. They move, rename, delete and re-type elements; undo and redo step back through their own
   edits in this session.
7. They move along the timeline, see what each Change edited, start a scenario from a moment, and
   export the view as PNG or SVG. (Until the change timeline exists, they compare a forked version
   with its base as today.)

## Acceptance criteria

### Layout

- [ ] The Structure tab uses the full width of the main area (no `max-w-6xl`), including on
      wide screens; other tabs keep their current width.
- [ ] The canvas height is the viewport height minus the shell and model header; the page
      itself does not scroll while the canvas is in use.
- [ ] Side panels (types and nodes, selection details) can be collapsed and remembered
      per person in the browser; the canvas gets the freed space.
- [ ] Below 768 px the panels become a bottom sheet; the canvas remains usable by touch.

### Navigation

- [ ] Wheel/pinch zoom around the pointer, between 10 % and 400 %; +/- buttons, a percentage
      readout, "Fit to view" and "100 %".
- [ ] Pan by dragging the background; space + drag and middle-button drag also pan.
- [ ] Keyboard: arrows move the selection or pan, `+` `-` `0` zoom, `F` fits, `Delete` removes
      the selection (with confirmation), `Esc` clears selection and cancels connect mode.
- [ ] A minimap shows the whole graph and the visible area; clicking it moves the view.
- [ ] Zoom and view survive saving an element; they reset only on leaving the tab or version.
- [ ] Positions are no longer clamped to a fixed 1400x800 area.

### Drawing and editing

- [ ] Node shape follows the node type (`shape`); colour follows the type; selection and
      hover states are visible in both themes.
- [ ] Edges show label, line style and arrowheads from the connection type, and avoid sitting
      on top of other nodes' labels at default zoom (parallel connections between the same two
      nodes are offset).
- [ ] Connect by dragging from a node handle or by the two-click mode; the allowed types
      filter applies; self-connection and duplicates give a readable message.
- [ ] New nodes appear at the viewport centre and open for naming.
- [ ] Multi-select (shift-click, rubber band) moves nodes together; delete works on the set.
- [ ] Snap-to-grid toggle and align/distribute for a selection (left, centre, top, equal gaps).
- [ ] Undo and redo (Ctrl/Cmd+Z, Shift+Ctrl/Cmd+Z) for create, move, rename, delete and connect,
      limited to the current session and the current version; each step is one server write and
      an audited change, as for any other edit.
- [ ] "Auto layout" arranges the graph (hierarchical or force-directed) on request, as one undoable
      step; nothing rearranges on its own.
- [ ] Concurrent edits still give a stale-version notice and a reload, never a silent overwrite.

### Reading

- [ ] Hover shows name, type and description in a popover that stays inside the canvas.
- [ ] The node list groups by type with colour tag and count; per-type visibility, Select all,
      Deselect all, collapse; hidden types hide their nodes and touching edges.
- [ ] Search by node name highlights matches and dims the rest; Enter centres on the first.
- [ ] Clicking a list row selects, centres and zooms to the node.
- [ ] Labels longer than 60 characters are shortened with an ellipsis; the full name shows on
      hover and in the details panel.
- [ ] Selecting a node shows its attached metrics (name, latest value) with a link to the
      Metrics tab; this replaces the legacy Timeserie mode.
- [ ] In a forked version, nodes and connections that are added, removed or changed against the
      base are marked on the canvas, and the change list stays available.
- [x] Large graphs (hundreds of nodes) are the design target; performance is not measured or gated in
      this version, and is revisited if users report slowness. (The product owner decided the canvas is not performance-gated; the backend timings are in the model timeline technical design.)

### Accessibility and quality

- [ ] Every action reachable by mouse has a keyboard route; nodes are focusable and announced
      with name and type; the canvas has a text alternative (the node list). (Verified by: ticket 09, `structure-canvas-accessibility.spec.ts`, mocked API and Chromium only, no screen reader; unticked until the product owner has tried it.)
- [ ] The tool respects reduced motion (no animated centring) and contrast in both themes. (Verified by: ticket 09, a global reduced-motion rule and Playwright media emulation; `contrast.test.ts` for the light tokens. No dark theme exists, so "both themes" cannot be met yet.)
- [x] Finnish and English texts for every new label. (Verified by: `frontend/tests/canvas/messages.test.ts`, ticket 09: every key of the model, canvas and timeline message files in both languages, none empty or copied.)
- [x] Frontend unit tests for geometry, filtering, undo and layout helpers; a browser test for
      zoom, fit, add, connect and filter; typecheck and build pass.

## Time and changes (direction set by the product owner)

Every Organization has one **Base line** (nameable). It always describes what has really happened
to the company, and its goal is to describe the company's present state at all times. It is built
from a starting situation and **changes**; every change has a date, always. A change dated in the future
is a **planned change**: something already known (a team to be founded on 1 January) is recorded
in advance and becomes part of the present state when its date arrives. The Base line's present state is
the state after the last change dated today or earlier. Choosing a change from the
list on the timeline shows the situation as it was after that change, so the past can be read.

A **Scenario** is a "what could happen" model. There can be any number of them. A scenario starts
from a **branch point**, which is a state: after a chosen change of the Base line, or after a chosen
change of another scenario. The branch point may lie in the past of the Base line, to model what
would have happened if, for example, a team had not been founded a year ago and the old way had
continued. From the branch point the scenario has changes of its own.

A **Change** is a set of edits at a date: it may add or remove elements, re-route connections, rename,
re-type, or anything else the graph allows. The state after a change is the starting situation plus
all changes up to and including it, in date order (and entry order within one date), along the chain
of branch points of its scenario.

How this relates to what exists today: a Version is a full copy of the graph with no time, and the
change list is a computed difference between a version and its base. Neither records when something
happens, and neither can start from a point in the past. The change timeline replaces both; the
existing versions, merge and change list stay until the timeline feature replaces them.

For the Structure canvas this means:

- [ ] The canvas shows one scenario (or the Base line) at one change. A scenario picker and a change
      list (with dates) sit on the canvas; the default is the latest state of the Base line.
- [ ] The canvas reads a state through one function (`state after change E in scenario S`), so it
      works today with versions and later with changes without redrawing the tool.
- [ ] Drawing edits the Change that is shown: each canvas edit (add, remove, rename, re-type, re-route)
      adds to or amends that Change's Edits, as one validated write. "New change" asks for a title and a date
      (the Base line suggests today; a later date makes it a planned change), creates it at the end of that
      date and selects it. Moving a node is not an edit: it changes only the drawing.
- [ ] Edits to a change that other changes or Scenarios depend on are checked against the whole chain; a
      refusal says which change and element would break and what to do first, and the canvas keeps the
      person's work on screen.
- [ ] Edits within one change are kept tidy: adding and then removing the same element in one change leaves no
      trace; renaming twice leaves one change.
- [ ] In the change list planned changes are marked by a different colour and a "Planned" label (not
      by colour alone), and they are clickable like the others: choosing one shows the state as it
      will be after it. The list also marks "Now" between the last happened and the first planned change. Drawing on an earlier change of a line is refused with a reason: start a
      scenario from there instead (or correct history through a dated change, see open questions).
- [ ] Elements added, removed or re-routed by the shown change are marked on the canvas; this replaces
      "ends in this state" from the first attempt.
- [ ] "New scenario from here" starts a scenario at the shown state, on the Base line or on another
      scenario, in the past or the present.
- [ ] Every Change can be edited or deleted afterwards (date, content, even re-ordering), because
      records contain mistakes. The Base line's present state and all scenarios are recomputed from
      the corrected changes.
- [ ] A change that would break the chain is refused. Examples: deleting a change that adds an element
      later changes use; moving a change before the change it depends on; removing a connection type or
      node that a later change or a scenario branched after it still needs; adding a connection the
      metamodel does not allow. The check replays the whole affected chain, including scenarios that
      branch from it, and nothing is saved if any step fails.
- [ ] The refusal is a readable message that names the change and element that would break, says
      why, and tells the person what to do (for example "Change 'Team founded' 1 Jan adds 'Support';
      the later change 'Move Ada to Support' needs it. Edit or remove that change first, or move
      this change to a date before it."). No raw server text reaches the page, and the form keeps
      the person's input.
- [ ] The Base line is visibly different from scenarios (name, colour, label) so that nobody mistakes a
      what-if for what has happened.

The change store, scenarios, branching rules, permissions and the timeline UI are a feature of their
own and get their own PRD and domain model in `.scratch/model-timeline/`. This PRD covers the drawing
tool and its time control, not the change store.

## Not in this version

- **Org-state lifetimes** (`createDate`/`deleteDate`, "ends in this state"): replaced by the change
  timeline described under "Time and changes", not by Versions alone.
- **Timeserie mode and its panel** (linking, creating and deleting timeseries on a node): metrics
  are managed on the Metrics tab; the canvas only shows a node's attached metrics.
- **AI Assistant mode**: it was a placeholder; the user's own agent works through MCP (ADR-0047).
- **Node and type catalog editing on the canvas**: stays on the Types tab.
- Real-time collaboration (cursors, live updates); conflicts are detected, not merged.
- Grouping, frames, free text and image shapes (a general diagramming tool).
- Custom attributes on nodes and connections.
- Import of graphs from other tools.

## Domain terms

Defined in `CONTEXT.md`: **Node**, **Connection**, **Metamodel**, and the timeline terms **Line**, **Change** and **State** (they replaced **Version** and **Change list**).
New: **Canvas** (the drawing surface of the Structure tab), **View** (the current pan and zoom;
never stored on the server).

## Documentation effects

Criteria in the sections above stay unticked on purpose: their only evidence is Vitest and Playwright against a mocked API in Chromium (no real sign-in, backend, other browsers, touch or screen reader) or a hand check by the product owner. Ticked: the unit-test criterion (Vitest suites for geometry, filtering, undo and layout helpers pass; Playwright specs exist; typecheck and build pass; verified by ticket 08 and 09 records), the not-gated performance statement and the Finnish and English texts (a unit test of the message files). Ticket 09 added the accessibility documentation (`docs/design/ui-foundation.md`, `docs/architecture/frontend.md`) and left the keyboard, reduced-motion and contrast criteria unticked for the reasons noted on them. Documentation effects below are ticked where the file was updated (`docs/design/ui-foundation.md`, `docs/user/README.md`, `docs/architecture/frontend.md`, `stack.md`, `project-layout.md`, ADR-0051, `CONTEXT.md`).

- [x] `docs/design/` - canvas interaction guidance (navigation, shortcuts, panels, states) - at the UI ticket
- [x] `docs/user/README.md` - how to draw, navigate, filter and undo - at the last ticket
- [x] `docs/architecture/stack.md`, `project-layout.md` and a new ADR - if a canvas library is added (see below)
- [x] `docs/architecture/frontend.md` - canvas structure and state - at the design ticket
- [x] `docs/architecture/api.md` - only if a bulk-position endpoint is added
- [x] `CONTEXT.md` - Canvas and View
- [x] No effect on `.env.example`, DBML or C4 unless a new endpoint or library is added

## Open questions

- Can the Base line receive a change dated in the past (a late record of something that happened)? [Yes,
  history must be correctable; changes sort by date. Future-dated (planned) changes are allowed
  on the Base line for known changes; what-if plans stay in scenarios.]
- Does a planned change that does not happen need a way to be cancelled? [Delete or move it like any
  change; no separate "cancelled" state at first.]
- When a past change is added to a line, do scenarios branched after it change? [Yes, they follow the
  corrected history, and their owners see a notice that the start changed; a branch is a reference to an
  change, not a copy.]
- Who sees that a planned change's date has passed without anyone confirming it? [Nothing special: once the
  date arrives it is part of the present state; a person corrects it if reality differed.]
- Time granularity of changes: day or month? [Day for changes; metrics stay monthly.]
- What happens to existing versions and merge? [Versions become scenarios; whether a scenario can be
  adopted into the Base line (as changes dated today) is decided in the model-timeline domain model.]
- Who may create scenarios and who may write to the Base line? [Members write scenarios; Owners and
  Admins (or a chosen role) write the Base line, since it claims to be the truth.]
- A limit on scenarios per Organization, and deleting a scenario that others branch from? [No limit at first;
  a scenario with children cannot be deleted.]
- Keep the hand-written SVG or adopt a library? [Decided: diagram-js (ADR-0051). It brings the editor
  behaviour (zoom, lasso, align, snap, connect, undo, minimap) and so removes tickets; performance is not measured or gated
  (product owner's decision), and Cytoscape.js stays the fallback only if slowness is reported.]
- Should undo survive a page reload? [No: session only; the audit log is the durable history.]
- Bulk position endpoint for multi-node moves? [Only if the measured cost of one write per node
  is a problem; otherwise reuse the single-node update.]
- Is dotted line style needed in the metamodel (today `solid` and `dashed`)? [Only if the Types tab
  should offer it; otherwise skip.]
- Should the minimap and snap-to-grid ship in the first ticket set or later? [Later: tickets
  for layout, navigation and drawing first, then minimap, alignment, auto layout.]
