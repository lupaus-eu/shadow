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

Adds dependencies to `docs/architecture/stack.md`: `diagram-js`, `diagram-js-minimap`, `elkjs`. Replaces the earlier Cytoscape.js decision of this ADR.
