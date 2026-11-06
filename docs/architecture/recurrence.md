# Recurrence

## Supported rules

- V1 presents weekly, monthly, and yearly recurrence patterns.
- Each pattern supports an interval, such as every two weeks.
- A weekly Series is anchored to one weekday and produces one Occurrence per interval; selecting multiple weekdays in one Series is not supported.
- A Series may continue indefinitely, end on a date, or end after a specified number of Occurrences.
- A monthly day-of-month rule uses the selected day as its persistent anchor. When a month lacks that day, the Occurrence falls on that month's final calendar date; later months return to the anchored day when it exists.
- “Last day of the month” is a separate monthly rule and always selects that month's final calendar date, starting with the end of the starting month even when the Series starts earlier in that month.
- Monthly recurrence therefore produces one Occurrence in every selected month, and an occurrence-count limit counts those generated dates.
- A yearly rule for February 29 produces an Occurrence only in leap years; it is not moved to February 28 in other years.
- The application stores the schedule as structured fields (`frequency`, `interval`, `until`, `occurrence_count`, `last_day`, and the anchor `starts_on`) that map one-to-one to an RFC 5545 rule; `SeriesResponse.rrule` returns it, for example `FREQ=WEEKLY;INTERVAL=2;BYDAY=TU` or `FREQ=MONTHLY;INTERVAL=1;BYMONTHDAY=-1;COUNT=12`. An anchored monthly day's shorter-month fallback is a product rule on top of `BYMONTHDAY`.
- `until` and `occurrence_count` are mutually exclusive, and `last_day` applies only to monthly Series.
- The UI exposes only the supported patterns even though the storage format can represent more complex schedules.
- Unsupported recurrence-rule combinations are rejected rather than accepted without a corresponding editing experience.
- Recurrence is intentionally a simple planning cadence rather than a general-purpose calendar scheduler.
- Daily recurrence is outside v1 because its volume conflicts with the Yearclock's glanceable annual-planning purpose.

## Source and materialization

- A Series stores the recurrence definition and may continue indefinitely.
- Individual Occurrences are persisted for requested Planning Windows and a configurable forward buffer.
- A Python worker keeps the forward buffer populated with one `recurrence.materialize` job per Organization per day (`docs/architecture/workers.md`). The buffer is the Organization's today plus `RECURRENCE_BUFFER_DAYS` (default 366).
- Requesting a Planning Window beyond the buffer materializes missing Occurrences before returning the complete view.
- The recurrence operation is idempotent and protected against duplicate Occurrences by database constraints; concurrent materializations serialize on the Series row.

## Exceptions and history

- An Occurrence may diverge from its Series date or content.
- Each Occurrence retains its generated Series Date even when its displayed date is overridden.
- Exception data records overridden fields individually rather than copying and detaching the entire Event: `series_occurrences.overrides` is a JSON object whose keys are the overridden fields (`title`, `description`, `description_format`, `location`, `links`, `starts_at`, `ends_at`, `lane_id`, `category_id`, `starts_on`, and `label_ids`). A missing key means the field inherits; `label_ids: []` means "no Labels" for that Occurrence.
- Labels (Yearclock V2): each Series segment carries its own set in `series_labels`. The effective Labels of an Occurrence (its override, else its segment's set) are written to `event_labels` of its Event whenever the Occurrence is materialized, overridden, restored, or moved to a successor segment, so Event lists, filters, and search read one table. A "this and future" split copies the segment's Labels to the successor unless the change sets new ones. Merging or deleting a Label also rewrites `label_ids` inside overrides.
- A Series row is one segment. `starts_on` is the rule's anchor and `effective_from` the first Series Date the segment owns; a successor keeps the anchor, so a monthly Series anchored on the 31st still returns to the 31st after a split in April.
- When a Series changes or is split, explicitly overridden fields remain unchanged and all other fields inherit from the applicable Series.
- **Restore Series values** clears an Occurrence's date and content overrides so those fields inherit from its Series again.
- **Skip Occurrence** creates a retained exclusion, hides that Occurrence from the normal Yearclock view, and allows it to be restored.
- Modified and Skipped Occurrences remain persisted as exceptions.
- Historical Occurrences are retained until the owning Organization is deleted and its retention window expires.

## Editing and ending recurrence

- **This occurrence only** creates or updates an exception without changing the Series.
- **This and future occurrences** ends the original Series immediately before the selected Occurrence and creates a successor Series beginning with the selected Occurrence.
- The split preserves prior Occurrences and their history under the original Series.
- Series splits and successor ownership use each Occurrence's stable Series Date, not an overridden displayed date.
- Moving an Occurrence across a split boundary therefore does not move it to another Series segment.
- Ending a Series removes its future Occurrences from the active plan while preserving historical Occurrences.
- These operations must retain an auditable record of the Series change and affected Occurrences.

## Boundaries

- The Series rule is not expanded into an unbounded future.
- Materialization respects the Organization time zone while producing all-day dates.
- Materialized Occurrences carry the owning Organization identifier and remain protected by row-level security.

## Presentation

- Every Occurrence remains individually selectable in the Yearclock view.
- A dense Series uses compact repeated markers and displays its label once rather than repeating the full label on every Occurrence.
- Exceptions are visually emphasized over unchanged Occurrences.
