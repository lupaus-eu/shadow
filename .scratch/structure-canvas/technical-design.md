# Technical design: Structure canvas

Status: accepted

## Current and target state

- **Current state:** `frontend/src/models/ModelCanvas.tsx` draws the graph in a hand-written SVG of fixed size 1400x800 (`viewBox`, `minWidth: 900`) inside a page limited to `max-w-6xl` (`ShellFrame` in `shell/AppShell.tsx` has a `wide` option that no route uses). It has select, drag with a debounce-free `updateNode` write (`expected_version`), "connect from" through a side-panel form, delete, an add-node form that places nodes on a grid, and the change list of a forked version. `node_types.shape` and the connection `style`, `source_end`, `target_end` exist in the API but only `style` and the ends are drawn.
- **Target state:** a full-width drawing tool (diagram-js, ADR-0051) with pan, zoom, fit, shapes, type list and filter, search, multi-select (lasso), undo/redo, hover popovers, snap/align/auto layout, minimap and PNG/SVG export, that reads its graph through one hook (`useGraphState`) so it works with versions today and with the state after an event of a line later (ADR-0048, `.scratch/model-timeline/`).
- No database or API change is required by this design; positions keep using the node update until `.scratch/model-timeline/` provides the positions endpoint.

## Domain

- Concepts: Node, Connection, Metamodel, Version (now) and Line, Event, State (later). The canvas needs only "a graph to draw" and "a write that changes it"; it does not know how the server stores history (`.scratch/model-timeline/domain-model.md`).
- Owning domain: Shadow models (`docs/architecture/`); no new domain.

## Database

No change. No migration. Layout preferences (panel widths, collapsed state, last view) are per-person browser storage, not server data, and never leave the browser.

## API

No new routes in this design. The canvas uses the existing model routes (`loadGraph`, `createNode`, `updateNode`, `deleteNode`, `createConnection`, `deleteConnection`, metrics read) through `models/client.ts`. Two later dependencies, both owned by `.scratch/model-timeline/`:

- state read: `GET .../lines/{line}/state?event_id=` (replaces `loadGraph` behind `useGraphState`);
- edit writes into the selected event, answering 422 `chain_broken` (ADR-0049), which the canvas shows as a readable refusal.

## Frontend

**Layout.** The Structure route renders its own full-bleed layout: `AppShell` gets `wide` for the model routes through a route handle or an outlet context flag, and `ModelShell` lets the Structure tab drop the tab-wide column. Only the Structure tab is wide; Types, Metrics, Simulations and Analysis keep `max-w-6xl`. The canvas height is `100dvh` minus the shell header and the model header, measured with a `ResizeObserver`; the page does not scroll while the canvas has focus. Panels (type list left, details right) sit beside the canvas in a CSS grid, are collapsible, and below 768 px become a bottom sheet.

**Library.** diagram-js (bpmn.io, MIT, no watermark) is an imperative, SVG-DOM toolkit for diagram editors. It is built from modules wired by a small dependency-injection container (`didi`). It is generic: bpmn-js, archimate-js and object-diagram-js are domain layers on top of it. We write a small domain layer for Shadow graphs and take the editing behaviour from its modules. The module and package names below are the expected ones; **ticket 02 verifies each against the installed package before relying on it and records the verified list in the ticket** (the product owner has not seen them confirmed). Any module that does not exist or does not behave as assumed becomes our own code and is noted in the ticket's completion record.

**Structure of `frontend/src/models/canvas/`:**

- `useGraphState.ts` - hook `useGraphState(source)` returning `{ graph, event, status, reload, error }` with plain data (`nodes`, `connections`, `nodeTypes`, `connectionTypes`, `allowedConnections`, `markers`). Implemented as `source = { organizationId, modelId, lineId, eventId? }` reading `GET .../lines/{line}/state` (`?event_id=` for the chosen event, otherwise the line's last event, which is where canvas edits go); the markers are the route's `added`, `updated` and `removed`. `reload()` resolves with the loaded graph. The hook is the one file that may know lines and events (a unit test checks that nothing else under `canvas/` imports them).
- `diagram/` - our diagram-js domain layer, a custom module `shadowGraph`:
  - `GraphImporter.ts` - turns plain graph data into shapes and connections with `canvas.addShape` and `canvas.addConnection`, diffing against `elementRegistry` so the diagram is updated in place and never recreated on a render; labels shortened to 60 code points (59 and an ellipsis, `shortenName`).
  - `GraphRenderer.ts` - a `BaseRenderer` subclass (implemented; the parallel-connection offset is in `GraphLayouter`, ticket 06): shape by `node_types.shape` (rectangle, round-rectangle, ellipse, diamond, hexagon; unknown falls back to round-rectangle), colour from the type with a contrasting text colour, selection, hover, dimmed, hidden and "changed in this event" marks (CSS classes and markers, never colour alone); connection line style (solid or dashed), arrowheads from `source_end`/`target_end`, label, parallel-connection offset between the same two nodes.
  - `GraphRules.ts` - a `RuleProvider` that encodes the metamodel: `connection.create` and `connection.reconnect` are allowed only when `allowedConnections` has the triple (connection type, source node type, target node type) and refuse self-connection and duplicates; the refusal cause is kept so the interface can word it (three distinct messages); `shape.create` and `elements.delete` are refused for a read-only Organization.
  - `GraphModeling.ts` - `applyEdit(edit)`, the single seam to the server (below). Implemented with diagram-js's own commands (`shape.create`, `elements.move`, `elements.delete`, `connection.create`) and one Shadow command, `shadow.node.update` (rename and describe); `connection.reroute` comes with ticket 05 if reconnecting is wanted. Moves made with the mouse are collected and saved 400 ms after the last one.
  - `index.ts` - the module declaration and the list of diagram-js modules used.
- `ShadowCanvas.tsx` - creates one `Diagram` in a ref (React never renders shapes), passes the module list, subscribes to `elements.changed`, `selection.changed`, `commandStack.changed` and `canvas.viewbox.changed`, and exposes an imperative handle (`fit`, `zoomTo`, `centreOn`, `exportPng`, `exportSvg`, `getViewbox`, `undo`, `redo`).
- `useCanvasView.ts` - pan/zoom state kept across saves and reloads of the same line/version; reset on leaving the tab or switching version/line. Zoom range 10 % to 400 % (`zoomScroll` is configured with those limits; our toolbar clamps the same).
- `CanvasToolbar.tsx` - zoom in/out, readout, Fit, 100 %, snap toggle, align/distribute, auto layout, export, undo/redo.
- `TypePanel.tsx` - nodes grouped by type, colour tag, counts, visibility checkbox, Select all / Deselect all, collapse, "+" per type, search box.
- `DetailsPanel.tsx` - the existing node, connection and changes panels, plus a node's attached metrics (name, latest value, link to the Metrics tab).
- `keymap.ts` - our keys on top of diagram-js `keyboard` bindings. `a11y/NodeList.tsx` - the text alternative.

**diagram-js modules expected to be used** (all verified present in 15.28.1 by ticket 02, see ADR-0051; `moveCanvas` and `zoomScroll` live under `lib/navigation/` as `movecanvas` and `zoomscroll`; `keyboard` binds to the diagram's own `<svg>` and `modeling` must be included by whoever uses `distribute-elements` or `grid-snapping`): `diagram-js/lib/features/selection`, `move`, `moveCanvas`, `zoomScroll`, `lasso-tool`, `create`, `connect`, `context-pad`, `palette`, `rules`, `modeling`, `align-elements`, `distribute-elements`, `grid-snapping`, `snapping`, `keyboard`, `editor-actions`, `overlays`, `outline`, `hand-tool`, `space-tool` (not needed), `command` (the command stack), plus the separate `diagram-js-minimap`. Not provided and therefore ours or from another package: automatic layout (`elkjs`, lazy loaded, ticket 07), PNG and SVG export (serialise the canvas SVG; PNG by drawing the serialised SVG onto a canvas), all React panels, and the accessibility layer (DOM shapes help; they are not enough on their own).

**Server stays the source of truth.** Every modeling command runs optimistically on the command stack, the same user gesture is sent to the server as one validated write (the existing model routes now; the event write routes later, ADR-0049), and the answer decides:

- accepted: the entry stays on the stack, and the local element receives the server's id and version (stored on the element's `businessObject`);
- refused (422 `chain_broken` or a rule, 409 stale version, 403): `commandStack.undo()` reverts the optimistic change, the entry is dropped from the redo side, and a readable notice names what was refused and what to do. The person's other work stays on the canvas.
- a failed network call is handled the same way.

All edits go through one function, `applyEdit(command)`, which wraps `modeling` and the server write. Ticket 08 redirects the write into the selected event by changing only that function's target.

**Undo and redo.** The person's session history is the diagram-js command stack, one stack per line/version, kept in memory, cleared when the version, line or event changes and on reload. Each stack entry has a server counterpart: undo issues the inverse write (a created node is undone by deleting it; a delete by recreating it with the same name, type and position and a note that it receives a new id; rename, re-type, re-route and connect likewise; a move writes the old position). Because writes carry `expected_version`, undo reads the fresh row first; if the server rejects the inverse (409 or 422) the entry is dropped from the stack and the person gets a readable notice. A multi-node move or delete is one stack entry (one `commandStack` transaction). With events (ADR-0048) each undo is a further write into the same selected event, not a hidden rollback. `Ctrl/Cmd+Z` and `Shift+Ctrl/Cmd+Z` come from diagram-js `keyboard` and `editor-actions`.

**Undo and redo as built (ticket 05).** The session history is a journal of plain steps (`canvas/history.ts`, owned by `GraphModeling`), not the diagram-js command stack: the stack is cleared on every load (a load replaces optimistic elements, and a node brought back by an undo is a new server element with a new id), so its entries cannot outlive a write. The journal follows ids through an alias map, reads the state afresh before each undo or redo, checks that the element is still as the entry left it (refusing with a notice otherwise), then writes each step through the same sender as any edit; a 409, 422 or refusal drops the entry. The command stack still draws the optimistic change of the edit itself. Ctrl/Cmd+Z is on the library `keyboard` service, without `editor-actions`.

**Keyboard map.** diagram-js `keyboard` supplies undo/redo, select all, copy/paste is disabled, `Delete`/`Backspace`, and `+`/`-` zoom bindings as configured; ours add `0` 100 %, `F` fit, arrows (move the selection, or pan with nothing selected; shift = larger step), `Tab` between canvas, toolbar and panels, `Enter` opens the selected element's details, `C` starts connect mode, `Esc` clears selection and cancels connect mode, `/` focuses search, space + drag pans (hand tool). Shortcuts are ignored while a text field has focus (`keyboard` is bound to the canvas container, not `document`).

**Layout and navigation.** `moveCanvas` and `zoomScroll` provide background-drag pan and wheel/pinch zoom around the pointer; our toolbar reads and sets `canvas.viewbox()` and `canvas.zoom()`. Reduced motion: `zoomScroll`/`canvas` animations and our centring use no transition under `prefers-reduced-motion`.

**Lasso, move, align, snap.** Selection by shift-click and the lasso tool; `move` moves a selection together as one command; `align-elements` and `distribute-elements` are configuration plus toolbar buttons; `grid-snapping` is toggled by our `shadow.canvas.snap` key. Each is one command-stack entry.

**Hover popovers (as built, ticket 06).** `diagram/GraphPopover.ts` adds the popover (name, type, description) as an `overlays` overlay beside the shape, on the side with room (`canvas/popover.ts`); the layer follows pan and zoom, the popover is removed on leave, on focus loss, on Esc, on a pan and while dragging, and opens on keyboard focus. The draft node and the naming input are ignored. **Node metrics** are read by `models/useNodeMetrics.ts` (outside `canvas/`, which may not call the server) when a node is selected: the line's metric list and each series once per page, latest non-empty month shown with the unit in the details panel, with a link to `.../metrics?line=`.

**Minimap.** `diagram-js-minimap` (a separate package; ticket 07), collapsible, with our CSS.

**Auto layout.** `elkjs` (layered algorithm), loaded only when the person asks; the result is applied as one `elements.move` command and therefore one undo step; nothing rearranges on its own.

**Export.** SVG: serialise the canvas `<svg>` with inlined styles and the current visibility (hidden types stay hidden); PNG: draw that SVG onto a `<canvas>` at scale 2. Both are our code (ticket 07).

**Browser storage.** New per-person keys, each registered in `backend/legal/browser-storage.json` and the storage notice (`backend/legal/storage.*.md`) in the ticket that adds it, so `frontend/tests/unit/browser-storage.test.ts` and `backend/tests/test_browser_storage.py` stay green: `shadow.canvas.panels` (left/right collapsed, widths), `shadow.canvas.typeCollapse` (collapsed type ids per model), `shadow.canvas.snap` (snap-to-grid on/off). Every read and write is wrapped in try/catch and the page works without it.

**Accessibility layer.** Shapes are DOM elements, which helps, but the SVG is not an accessible structure by itself, so a visually hidden but focusable node list (`a11y/NodeList.tsx`, also the visible left list) exposes every node with name, type, description and connections; selecting a row selects and centres the node. A live region announces selection, connect mode and refusals. Focus returns to the canvas after a dialog. Reduced motion disables animated centring and zoom. Selection and "planned"/"changed" marks never rely on colour alone.

**Performance.** diagram-js renders every shape and connection as SVG DOM. The product owner decided not to measure or gate performance; no threshold is set and the library is not re-decided on speed. If users later report slowness with large graphs, the first mitigations are to hide labels of unselected nodes and of connections below 40 % zoom and to skip the outline and hover layers while dragging.

## Authentication and authorization

Unchanged. Write controls are shown only for a writable Organization (`workspace.subscription.writable`); on the Base line later only Owners and Admins write (`.scratch/model-timeline/domain-model.md`). The server enforces every rule; the canvas only hides what the server would refuse and shows its refusal otherwise.

## Testing

- Backend/API tests: not applicable; no backend change in this design.
- Frontend/UI tests (vitest, `npm --prefix frontend run test:unit`): `GraphImporter` diffing and `GraphRules` (allowed types, self-connection, duplicates, read-only) with a headless diagram-js instance, label shortening at 60 code points, parallel connection offsets, hidden types remove touching connections, `useCanvasView` (zoom limits, view kept across reload), filter and search helpers, the server seam in `applyEdit` (accepted keeps, refused reverts, inverse write on undo, drop on 409), `keymap.ts` (ignored in text fields), align/distribute/snap configuration, browser-storage wrappers.
- Browser/E2E validation (Playwright, `npm --prefix frontend run test:browser`): open a model, canvas fills the width, zoom/fit/100 %, add a node from a type "+", connect two nodes, filter a type, search and centre, undo and redo, export PNG; keyboard-only path for selecting a node and starting a connection; mobile viewport check.
- Migration, integration or architecture validation: `npm --prefix frontend run typecheck && npm --prefix frontend run build`; `backend/tests/test_browser_storage.py` after every storage key.

Select checks using [`docs/agents/testing.md`](../../docs/agents/testing.md). Every implementation ticket records its executed commands and results.

## Configuration

No new environment variables.

## Architecture effects

- New frontend dependencies: `diagram-js` 15.28 (MIT) and `tiny-svg` 4.1 (its drawing helper, used directly), confirmed in ticket 02 (its other dependencies come with it); dev: `vitest` and `jsdom` for the canvas tests, `diagram-js-minimap` (MIT, ticket 07) and `elkjs` (EPL-2.0, lazy loaded, ticket 07; licence confirmed in ticket 07 before adding), and their types where they exist (otherwise a local declaration file). `docs/architecture/stack.md` and `project-layout.md` list them (ADR-0051).
- No service, port, data ownership or integration change. LikeC4 and DBML are unaffected.

## Documentation effects

- [ ] Update `docs/user/` - drawing, navigating, filtering, undo, export (ticket 09)
- [ ] Update `docs/admin/` - no effect
- [ ] Update `docs/operations/` or `docs/runbooks/` - no effect
- [ ] Update `docs/gdpr/` - evaluated with the browser-storage keys (tickets 01, 04, 07)
- [ ] Update `docs/legal/` - `backend/legal/storage.*.md` for each new key (same tickets)
- [ ] Update `docs/architecture/` - `stack.md`, `project-layout.md`, `frontend.md` (tickets 02 and 09)
- [ ] Update `docs/design/` - canvas interaction guidance (ticket 09)
- [ ] Add or update `docs/adr/` - ADR-0051 accepted at ticket 02
- [ ] Update `CONTEXT.md` - Canvas and View (ticket 09)
- [ ] Update `.env.example` - no effect

## Options and decision

- **Extend the hand-written SVG:** no new dependency, but zoom, hit testing, shapes, layouts, minimap, snapping, alignment and undo would all be written and maintained by us.
- **React Flow:** good DOM accessibility and styling, but one React component per node and edge is slower at the target size, and it has no built-in layouts.
- **Cytoscape.js (the earlier choice of ADR-0051):** canvas rendering, shapes, layouts and speed at 500 nodes, but it is a graph visualisation library: editing behaviour (connect by drag, undo, align, snap, minimap) comes from separate extensions of varying maintenance, and the accessibility layer is wholly ours. It remains the fallback if diagram-js fails the performance threshold in ticket 02.
- **diagram-js (chosen, ADR-0051):** a toolkit for diagram editors whose modules already give selection, lasso, move, connect, context pad, alignment, snapping, keyboard bindings, overlays and a command stack with undo and redo. Costs: SVG DOM rendering (performance must be measured), no automatic layout (`elkjs`), imperative code with its own DI and sparse documentation, and a server-synchronised command stack that we build. The `useGraphState` hook and the `diagram/` module contain the library, so a later change stays local. The choice saves one ticket (undo and redo merge into drawing) and shrinks navigation and layout tools.
- **Full width only on the Structure tab:** other tabs are reading and form pages where a narrow column is better.
- **Undo as the command stack with inverse API writes:** durable history is the server's (audit log, and events later); the session stack is the person's convenience and needs no server change.
