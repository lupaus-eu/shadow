# Events

## Content

Every Event has:

- a required title
- an optional description
- one required Lane
- at most one optional Category
- an optional location (free text, up to 200 characters)
- up to ten optional titled links (`http` or `https`; Yearclock V2 P11)
- an optional start time and end time (`HH:MM`, in the Organization's time zone; Yearclock V2 P11)
- a required all-day start date
- an optional inclusive all-day end date

Descriptions are plain text unless an Event's `description_format` is `markdown` (Yearclock V2 P11, ADR-0033). Plain descriptions keep their line breaks and show detected web addresses as safe links, and they are never interpreted. A `markdown` description uses a small subset: `**bold**`, `*italic*`, `- ` and `1. ` lists, `[text](https://…)` links, bare addresses, paragraphs, and line breaks; backslash before punctuation shows that character, and everything else is literal text. No HTML is stored or rendered. The parser is `backend/app/rich_text.py`, matched by `frontend/src/yearclock/rich-text.ts`, and both run the same cases (`frontend/tests/unit/rich-text-cases.json`). Search, exports, the calendar file, email, and print use `plain_text`, which removes the markers and writes links as "text (address)". New Events from the interface are `markdown`; existing ones stay `plain` until an Editor chooses **Use text formatting**; the API default is `plain` on create and "keep" on update.

## Planning boundary

- An Event may represent a milestone, period, meeting, obligation, or expected
  piece of work.
- An Event remains planning intent. It has no assignee, due-date field,
  completion state, overdue state, or execution history.
- An Event may belong to a Series.
- Categories classify Events across Lanes without changing access.
- The optional links may point to related material or work in another
  system, but Yearclock does not define a Task integration contract in v1.

## V1 boundaries

Events do not have attendees, attachments, conferencing
details, invitations, reminders, notifications, or Task-specific behavior in
v1. The product uses familiar calendar-entry conventions for creating dated
Events without becoming a meeting calendar, task manager, or document
management system.
