---
status: accepted
---

# Render the primary Yearclock as SVG

The first-release Yearclock is a responsive SVG rendered by React, with months
as the temporal scale, Lanes as concentric rings, and Events as accessible
markers or arcs. React owns interaction while isolated geometry utilities
calculate positions. SVG is preferred over Canvas because it better supports
text, focus, keyboard interaction, assistive semantics, responsive layout, and
future printing or export.

Yearclock V2 (2026-10-05) adds secondary displays in ADR-0029; the SVG circle stays the primary display.
