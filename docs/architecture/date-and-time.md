# Date and time

## Event dates

- Event start and end values use PostgreSQL `date`.
- Event dates are all-day values and never shift between time zones.
- Date ranges are inclusive in the domain and API contracts.

## Time of Day (Yearclock V2 P11, ADR-0033)

An Event or Series may carry an optional start and end time (`time` columns,
no time zone), read in the Organization's time zone. Dates stay the source of
truth and are never shifted; the times only add detail. They are stored to the minute, shown as `HH:MM`, and on a one-day Event the end is after the start; on a longer Event the start time belongs to the first day and the end time to the last. Same-day Events list all-day first and then by start time. A Series keeps one time for all Occurrences, and an Occurrence may override it. The `.ics` export turns a
timed Event into UTC instants using the Organization's zone (correct across daylight-saving changes). A start time alone is a point in time (`DTEND` equals `DTSTART`) on a one-day Event and runs through the end of the last day on a longer one, so no duration is invented; an untimed Event stays all-day.

## Organization time zone

Each Organization has one IANA time-zone identifier. It determines:

- the Organization's current date
- the default current-year Planning Window
- recurrence generation boundaries

## Timestamps

- Audit, integration, billing-projection, and lifecycle timestamps are stored as UTC instants.
- User interfaces display timestamps in the viewer's browser time zone.
- V1 has no per-user display time zone preference (ADR-0015, decision of
  2026-09-23).
