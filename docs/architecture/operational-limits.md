# Operational limits

Yearclock refuses to create content beyond configured ceilings rather than
degrading silently. A refused create returns `409` with
`{"detail": {"reason": "limit_reached", "limit": "<name>", "maximum": N}}`; the
planner shows the limit and what to do. Ceilings apply when content is
created; restoring deleted content and materializing existing Series are not
refused. The parent row is locked while counting, so concurrent requests
cannot overshoot (tested with 12 parallel creates against a limit of 5).

| Limit | Variable | Default | Counts |
| --- | --- | --- | --- |
| `yearclocks_per_organization` | `LIMIT_YEARCLOCKS_PER_ORGANIZATION` | 50 | Non-deleted Yearclocks |
| `lanes_per_yearclock` | `LIMIT_LANES_PER_YEARCLOCK` | 12 | Lanes |
| `categories_per_yearclock` | `LIMIT_CATEGORIES_PER_YEARCLOCK` | 40 | Categories |
| `events_per_yearclock` | `LIMIT_EVENTS_PER_YEARCLOCK` | 3000 | Non-deleted Events, including materialized Occurrences |
| `series_per_yearclock` | `LIMIT_SERIES_PER_YEARCLOCK` | 100 | Series (a new Series also needs Event capacity) |
| `labels_per_organization` | `LIMIT_LABELS_PER_ORGANIZATION` | 200 | Labels of the Organization |
| `labels_per_event` | `LIMIT_LABELS_PER_EVENT` | 10 | Labels on one Event (refused on create and update) |
| `organization_categories` | `LIMIT_ORGANIZATION_CATEGORIES` | 40 | Organization Categories |
| `bulk_events` | `LIMIT_BULK_EVENTS` | 200 | Events changed by one Bulk Edit (refused before any change) |
| `groups_per_organization` | `LIMIT_GROUPS_PER_ORGANIZATION` | 100 | Groups of the Organization |
| `exports_per_hour` | `LIMIT_EXPORTS_PER_HOUR` | 20 | Exports, imports, and import previews per user and Organization in one hour (refused with 429; counted from the Audit Log) |
| `organization_exports_per_hour` | `LIMIT_ORGANIZATION_EXPORTS_PER_HOUR` | 3 | Organization Exports per Owner and hour (refused with 429) |
| `transfer_rows` | `LIMIT_TRANSFER_ROWS` | 200000 | Data rows in one Data transfer file (refused with 422) |
| `transfers_per_hour` | `LIMIT_TRANSFERS_PER_HOUR` | 3 | Data transfer exports, previews, and saves per user and hour (refused with 429) |
| — | `TRANSFER_MAX_BYTES` | 104857600 | Size of a Data transfer file (refused with 413) |
| `import_rows` | `LIMIT_IMPORT_ROWS` | 1000 | Data rows in one import file (refused with 422) |
| — | `IMPORT_MAX_BYTES` | 2097152 | Size of an import file (refused with 413) |
| `billing_contact_changes_per_day` | `LIMIT_BILLING_CONTACT_CHANGES_PER_DAY` | 5 | Billing contact changes per Organization in 24 hours (refused with 429; counted from the Audit Log) |
| `notification_emails_per_day` | `LIMIT_NOTIFICATION_EMAILS_PER_DAY` | 10 | Notification emails per recipient in 24 hours; further notifications stay in the app |
| — | `NOTIFICATION_RETENTION_DAYS` | 90 | Age at which the daily cleanup job deletes notifications |
| — | `LIMIT_REVISIONS_PER_EVENT` | 100 | Event Revisions kept per Event; older ones are pruned, nothing is refused |

Other fixed ceilings: Support Access at most 24 hours, Invitations valid for
seven days, email retried three times, and background jobs retried five times.

## Load check

`backend/tests/test_operational_limits.py` loads a Yearclock with 12 Lanes
and 2,999 Events and checks that the planning-window API returns every Event
in under three seconds, that the 3,000th Event is accepted, and that the next
one is refused with `limit_reached`. It runs against the development
PostgreSQL, so it shows that the ceiling is reachable, not how production
hardware performs. Repeat it on production hardware before launch
(`docs/runbooks/launch-checklist.md`).
