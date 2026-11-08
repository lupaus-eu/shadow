---
status: accepted
---

# Draw the Structure canvas with diagram-js

## Context

The Structure tab draws the graph with a hand-written SVG of fixed size. The product owner wants a full-width drawing tool with zoom, pan, fit, shapes, filtering, multi-select, alignment, snapping, undo and redo, a minimap, auto layout and graphs of several hundred nodes. This ADR first chose Cytoscape.js, a graph visualisation library that has no editing behaviour of its own (connecting, undo, alignment and minimap would each be a separate extension or our own code). The alternatives were extending the SVG by hand, Cytoscape.js and React Flow. The product owner then chose diagram-js, the toolkit behind bpmn-js, because it already provides the editor behaviour and so removes tickets. Nothing had been built on Cytoscape, so the change cost only documents.

## Decision

- Use **diagram-js** (MIT, no watermark; a generic toolkit also used by archimate-js and object-diagram-js) for the canvas. We write a small modeling domain on it: node and connection element types, a renderer that draws shape and colour from the node type and line style and ends from the connection type, and a rules provider that encodes the Metamodel's allowed connections and refuses self-connections and duplicates. diagram-js renders SVG in the DOM and is driven imperatively through its own module system; React renders the surrounding panels, forms and popovers and mounts the canvas in one component.
- Take its editor modules rather than rebuilding them: canvas zoom and scroll, selection, lasso, move, create and connect with context pad and palette, align and distribute, grid snapping, keyboard bindings, overlays and the command stack, plus `diagram-js-minimap`. The exact module names and what each gives are verified in the first canvas ticket before anything relies on them.
- Not provided, so ours or added: auto layout (`elkjs`, loaded lazily), export to PNG and SVG, the panels and lists, the Finnish and English texts and the accessibility layer. The DOM elements make the accessibility layer easier than a canvas element would.
- diagram-js is the view, not the source of truth. The state after an event of a line (ADR-0048) is loaded by a hook that returns plain graph data; an importer turns it into shapes and connections. The canvas never reads versions or events directly, so it works with the present model and with the event timeline.
- Every modeling command runs optimistically in the command stack and is sent as the validated write. If the server refuses it (ADR-0049, a stale version), the command is undone and the person gets a readable message. The command stack is the person's session history, so undo and redo issue the inverse write.
- Performance is not measured or gated; the product owner decided it needs no confirmation. If users later report slowness with large graphs, this ADR is reopened and Cytoscape.js is the fallback.

## Consequences

- Several tickets shrink or merge: undo and redo come with drawing, and alignment, snapping, lasso and the minimap are configuration of existing modules.
- SVG in the DOM is slower than a canvas renderer at large sizes; nothing guards that risk now beyond the reopening rule above. diagram-js has no layout, and its documentation is thinner than a general-purpose library's.
- A change of library later is contained by the importer and the hook, as before.

## Verification (structure-canvas ticket 02)

Done against the installed package, with the code in `frontend/tests/canvas/modules.test.ts` (each module is loaded under a `Diagram` and its service is checked).

- **Installed:** `diagram-js` 15.28.1 (MIT, ESM, types shipped as `lib/**/*.d.ts`, CSS at `assets/diagram-js.css`; no licence or watermark issue; works with React 19 and Vite 6 as a plain import). Its dependencies are `didi` 11, `min-dom` 5.3, `min-dash`, `tiny-svg` 4.1, `inherits-browser`, `object-refs` and `path-intersection`; Shadow uses `tiny-svg` directly and lists it. Node's own test runner cannot load diagram-js (extensionless ESM imports), so its tests run in Vitest with jsdom.
- **Present, verified to load and to provide their service:** `selection`, `move`, `lasso-tool`, `create`, `connect`, `context-pad`, `palette`, `rules`, `modeling`, `align-elements`, `distribute-elements`, `grid-snapping`, `snapping`, `keyboard`, `editor-actions`, `overlays`, `outline`, `hand-tool` (all under `diagram-js/lib/features/`), the command stack (`diagram-js/lib/command`) and the two navigation modules, which live under `diagram-js/lib/navigation/` and are spelled `movecanvas` and `zoomscroll`. Also present and possibly useful later: `keyboard-move`, `keyboard-move-selection`, `search`, `hover-tooltip`, `auto-place`, `space-tool`, and `CroppingConnectionDocking` (used by Shadow to end a connection on a shape's outline).
- **Findings that change how later tickets use them:** (1) `modeling` is not brought in by `distribute-elements`, `grid-snapping` and several others; a Diagram that uses them must include `modeling` itself. (2) `keyboard` binds to the diagram's own `<svg>` and the old `keyboard.bindTo` option is removed (it logs an error), which is the "canvas container, not document" behaviour the design wants; keys fire only while focus is inside the drawing, so text fields in the panels are naturally excluded. (3) The library toggles a selected element off when it is clicked again; Shadow keeps it selected (a click on the background clears). (4) `canvas.removeConnection` alone leaves the connection in its shapes' `incoming` and `outgoing`; the importer detaches both ends. (5) A dragged shape is reparented into the shape under the pointer unless the drop target is forced to the root; `GraphMoveTarget` does that. (6) `RuleProvider.addRule` needs an explicit priority.
- **Minimap:** the package is `diagram-js-minimap` 5.6.0 (MIT; depends on `min-dom`, `min-dash`, `tiny-svg`; not installed yet, ticket 07).
- **Missing, and who builds it:** automatic layout (`elkjs`, lazy loaded, ticket 07), PNG and SVG export (ticket 07, serialising the canvas SVG), all React panels, the type list and search (ticket 04), the visually hidden node list and live region (ticket 09), the hover popover content (ticket 06, on `overlays`), and the server-synchronised undo and redo (ticket 05, on the command stack and `GraphModeling.applyEdit`). Nothing the design relies on is missing from the library, so the decision stands.

Adds dependencies to `docs/architecture/stack.md`: `diagram-js`, `diagram-js-minimap`, `elkjs`. Replaces the earlier Cytoscape.js decision of this ADR.
