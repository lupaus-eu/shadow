---
status: accepted
---

# Add richer Event content

## Context

The V1 PRD excluded time-of-day scheduling, rich text, attachments, and
locations, and ADR-0026 left out daily recurrence. The review of 2026-10-05 (V2
P11) weighed Plandisc's richer activity content against the product's purpose:
a glanceable annual plan whose unit is the day (ADR-0015).

## Decision

- **Time of Day** is optional extra information: a start and an end time with no
  time zone of their own, read in the Organization's time zone. Dates stay the
  source of truth, so ADR-0015 holds: the all-day date never shifts, and the
  circle keeps its day resolution.
- **Location** is optional free text. **Links** replace the single `external_url`:
  up to 10 titled `http(s)` addresses.
- **Formatted description** uses a small Markdown subset (bold, italic, lists, links)
  stored in the existing description with a per-Event format flag. No HTML is
  stored or rendered. Existing descriptions stay plain until an Editor opts in.
  Search, exports, `.ics`, email, and print use the plain-text form.
- **Out:** daily recurrence (a daily activity is a date range, and a daily Series
  would break the 3000-Event ceiling and the annual view), several weekdays in
  one Series, and file attachments (they would need object storage, malware
  scanning, and a new processing purpose; links to files cover the need).
- `.ics` carries timed Events as UTC instants computed from the Organization's
  time zone; untimed Events stay all-day.

## Consequences

- One migration adds `location`, `links`, `description_format`, `starts_at`, and
  `ends_at` to Events and Series and converts each `external_url` into a one-link
  list. The Organization Export version rises to `yearclock-export/2`.
- Every place that carries `description` and `external_url` carries the new
  fields: History, Series and Occurrence overrides, Plan Again, Lane copying,
  Linked Lanes, Support Access edits, import and export, search, and the summary.
- Refines ADR-0015 (optional time of day on top of all-day dates) and ADR-0030 and
  ADR-0031 (formats and `.ics`). ADR-0026 stands: daily recurrence stays excluded.
