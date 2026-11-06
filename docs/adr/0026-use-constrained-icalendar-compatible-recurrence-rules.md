---
status: accepted
---

# Use constrained iCalendar-compatible recurrence rules

V1 exposes only weekly, monthly, and yearly recurrence patterns with an interval and an optional end date or occurrence count. Daily recurrence is excluded because hundreds of Occurrences conflict with the product's glanceable annual-planning purpose. The application stores supported schedules as iCalendar-compatible recurrence rules, retaining a standard representation that can support richer patterns later without exposing their complexity in the initial user interface. Rules outside the supported subset are rejected so every stored schedule remains editable through the product.

Each Series produces at most one Occurrence per recurrence interval. In particular, a weekly Series is anchored to one weekday and cannot combine several weekdays; Yearclock recurrence is a planning cadence, not a general-purpose calendar scheduler.

Monthly recurrence distinguishes an anchored calendar day from the last day of the month. An anchored-day rule normally selects its original day number but falls back to the month's final date when that day is absent, returning to the anchored day in later months where it exists. A last-day rule always selects the month's actual final date. Both produce one Occurrence per selected month, so an occurrence-count limit measures generated Occurrences rather than attempted dates.

The same exact-date rule applies to yearly recurrence: February 29 produces an Occurrence only in leap years and is never silently moved to February 28.
