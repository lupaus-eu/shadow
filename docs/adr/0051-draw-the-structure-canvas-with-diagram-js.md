---
status: accepted
---

# Draw the Structure canvas with Cytoscape.js

## Context

The Structure tab draws the graph with a hand-written SVG of fixed size. The product owner wants a full-width drawing tool with zoom, pan, fit, shapes, filtering, multi-select, a minimap, auto layout and graphs of several hundred nodes. The first Shadow attempt used Cytoscape.js. The alternatives are extending the SVG by hand, and React Flow (a React library for node editors).

## Decision

- Use **Cytoscape.js** (MIT) for the canvas, with its canvas renderer, and add a layout extension (a hierarchical layout) when auto layout is built. React renders the surrounding panels, popovers and forms; the graph is not rendered by React.
- Cytoscape is the view, not the source of truth. The server state (the state after an event of a line) is loaded by a hook that returns plain graph data; an adapter turns it into Cytoscape elements and back into API calls. The canvas never reads versions or events directly, so it works with the present model and with the event timeline.
- Selection, hover, filtering, search highlight and the "changed in this event" marks are Cytoscape classes, not state in the DOM.
- Positions are saved through the existing node update with `expected_version` until ADR-0048 moves them to the positions endpoint.
- Keyboard routes and a text alternative (the node list) are built beside the canvas, because the canvas element is not accessible by itself.

## Consequences

- Pan, zoom, shapes, hit testing and 500-node performance come from the library. The cost is a dependency (about 400 kB minified before compression) and an accessibility layer we write ourselves.
- React Flow was not chosen: it renders every node as a DOM element, which is easy to style and accessible but slower at the sizes asked for, and it has no built-in layouts.
- A change of library later is contained by the adapter.

Adds a dependency to `docs/architecture/stack.md`.
