---
status: accepted
---

# Use a continuous Yearclock timeline

A Yearclock stores Events on one continuous past-and-future timeline rather than dividing them into calendar-year containers. Users view that timeline through a Planning Window, initially a selected 12-month calendar year, so future rolling periods and other views can be added without migrating the event model.

Yearclock V2 (2026-09-24) uses this freedom: a Planning Window can cover 1, 3,
6, 12, 18, or 24 whole months, and each Yearclock has a start month that sets
its default window. Events stay on the same continuous timeline.

All Yearclock V2 displays (circle, timeline, list, and agenda; ADR-0029) read
this same timeline through the Planning Window.
