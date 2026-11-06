---
status: accepted
---

# Add secondary displays to the circle

## Context

Yearclock V1 showed one display, the circle (ADR-0017), and its PRD excluded
"list, traditional calendar" views so that Yearclock would not turn into a
general-purpose calendar. Teams still need to see overlaps and lengths,
sort and change many Events, and read a month day by day. The review of
2026-10-05 (V2 P5) weighed four Plandisc views against that principle.

## Decision

- The circle stays the default and primary display. Three displays are
  added: **Timeline** (Lanes as rows), **List** (a sortable table), and
  **Agenda** (the circle beside a day-by-day list).
- A **Display** is a personal choice kept in the browser, per Yearclock. All
  displays show the same Events of the same Planning Window under the same
  Filters, and share selection, Details, History, change marks, and the Event
  drawer.
- Events are changed only through the drawer. Dragging and resizing stay out.
- A traditional month or week calendar display stays excluded. The V1 PRD
  entry now reads: list views are included as Display; traditional calendar,
  embedded, print, and export-oriented views remain out (the last three are
  reviewed in P6 and P7).
- Every marker, bar, and row is a button with the circle's accessible name;
  the list is the text equivalent of the timeline.

## Consequences

- No API or database change: displays are different renderings of the loaded
  Events, bounded by the existing 3000-Event ceiling.
- The planner keeps one set of state, so a new filter, mark, or action works
  in every display. `placeEvents` becomes shared code.
- Tests and visual baselines grow per display, and the timeline needs a
  measurement with 3000 Events.
- Refines ADR-0017, which keeps the circle as the primary SVG display, and
  ADR-0001, whose continuous timeline all displays read.
