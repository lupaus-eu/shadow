---
status: accepted
---

# Separate all-day dates from UTC timestamps

Event scheduling uses all-day PostgreSQL `date` values that never shift across
time zones. Each Organization has an IANA time zone that defines its current
date, default Planning Window, and recurrence boundaries. Audit and integration
timestamps are stored as UTC instants and displayed in the viewer's browser
time zone.

A per-user display time zone preference is out of scope for V1 (product
decision, 2026-09-23). It was originally planned as the display zone, with the
Organization time zone as the fallback. Users are expected to work mostly in
their Organization's time zone, where the browser zone gives the same result.
A later preference can be added without changing stored data, because every
timestamp is already a UTC instant.
