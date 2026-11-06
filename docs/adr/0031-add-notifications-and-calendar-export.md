---
status: accepted
---

# Add notifications and calendar export

## Context

The V1 PRD excluded calendar synchronization, reminders, and date-based
notifications. The review of 2026-10-05 (V2 P8) weighed Plandisc's Outlook
sync, invitation import, reminders, and notifications against the platform:
Scaleway Transactional Email only sends (ADR-0023), Authentik is the only
identity provider so there are no Microsoft tokens (ADR-0003), anonymous
access is forbidden (ADR-0004, which rules out secret-URL feeds), and Events
have no attendees or assignees.

## Decision

- **Calendar:** a one-off `.ics` download from the Export menu. No
  synchronization, no feed, no inbound email.
- **Notifications** tell a person what changed for them: their effective role
  on a Yearclock, their Organization role, accepted invitations, ownership
  transfer, and (for Owners and Admins) Support Access, billing, and deletion.
  They never carry Event content.
- **Storage:** one `notifications` table, written in the same transaction as
  the cause, holding a type and parameters; text is built at read time in the
  reader's language. Row-level security limits a row to its recipient inside
  one Organization. The worker deletes rows after 90 days.
- **Channels:** an in-app inbox and email through the existing outbox. The
  person switches each type per channel. Notification email is capped at 10
  per recipient per 24 hours; the rest stay in-app.
- **Reminders** are replaced by an opt-in Summary of upcoming Events, weekly or
  daily at 08:00 Organization time, per Organization, from Yearclocks the
  person picks. It is the only message that contains Event content.

## Consequences

- One new table, one new worker job (cleanup) and one scheduled job (summary),
  new email templates; no new service or port.
- Notifications on bulk access changes rely on computing the effective role
  before and after, using the single access rule.
- Email limits count outbox rows, so no counter store is added.
- The V1 PRD's out-of-scope entries now read: synchronization, conferencing,
  attendees, locations, and attachments remain out; reminders are replaced by
  the opt-in Summary.
- Refines ADR-0023 (notification email types), ADR-0024 (new outbox
  messages), and ADR-0030 (`.ics` joins the Export formats).
