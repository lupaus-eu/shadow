---
status: accepted
---

# Materialize recurring Occurrences in a rolling window

A Series stores its recurrence definition while individual Occurrences are persisted only for requested Planning Windows and a configurable forward buffer. Python workers keep the normal buffer populated, and distant window requests idempotently materialize missing Occurrences before returning a complete view. Modified and Skipped Occurrences remain stored as historical exceptions, avoiding infinite future rows without sacrificing per-Occurrence changes.

Editing one Occurrence creates an exception. Editing that Occurrence and all future Occurrences ends the original Series immediately before the selected Occurrence and creates a successor Series, preserving prior history. Ending a Series removes future Occurrences from the active plan while retaining historical Occurrences.

Exceptions retain their generated Series Date and record overrides field by field. When the Series changes or splits, explicit overrides remain fixed while non-overridden values inherit from the applicable Series. This preserves deliberate one-off changes without freezing unrelated Series values.

Series splits classify Occurrences by their stable Series Date rather than an overridden displayed date. An Occurrence moved across the split boundary therefore remains attached to its original Series segment.

Users may restore an exception's Series values by clearing its explicit date and content overrides.

Removing one recurring Event uses a reversible Skip Occurrence exclusion: the
Event is hidden from the normal view but its identity and history remain.
