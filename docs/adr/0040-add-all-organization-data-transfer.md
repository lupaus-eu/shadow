---
status: accepted
---

# Add a data transfer of all administered Organizations

## Context

ADR-0030 gave Yearclock a spreadsheet export and import of one Yearclock's Events and a JSON Organization
Export for Owners. The Organization Export cannot be imported, and the Events import cannot carry Yearclocks,
Lanes, Categories, Labels, or Series. Owners and Admins who run several Organizations asked for one file that
holds everything they administer and that can be put back into the database.

## Decision

- Add a **Data transfer**: one CSV file (`yearclock-data/1`) of every Organization where the user is Owner or
  Admin, and an import of the same file. The Yearclock export and import and the Organization Export stay as
  they are.
- The file is one table with a `type` column (`organization`, `label`, `yearclock`, `lane`, `category`,
  `series`, `event`, `series_exception`) and parent ids. It holds Yearclocks (also archived), Lanes, Categories,
  Labels, Events, and Series with their changed or skipped Occurrences. It holds no people, Groups, access
  rights, deleted Events, History, Audit Log, or billing data, so an Admin may use it.
- Import updates a row whose id exists and creates a row whose id does not; it never deletes, never creates an
  Organization, and never changes an Organization's settings. The file wins over newer changes; changed Events
  get an Event Revision with reason `import`, and the preview counts Events changed after the export.
- The import runs the whole file inside a savepoint: a preview rolls it back, a save commits only when no row
  has an error. Rows are validated with the request models of the ordinary routes, and Organization access
  comes from `access.py`, so there is no second rule.
- Limits: `LIMIT_TRANSFER_ROWS`, `TRANSFER_MAX_BYTES`, and `LIMIT_TRANSFERS_PER_HOUR`, counted from the Audit
  Log (`data.export`, `data.import_preview`, `data.import`, one entry per Organization).
- The page lives in the user menu, because a transfer spans Organizations.

## Consequences

- No new table, service, or port. A new module, `data_transfer.py`, and `/api/v1/data-transfer/*` routes.
- A restore is possible for content that still exists as a row or can be created from the file; a deleted
  Event or Yearclock in the database is reported, not revived.
- The repeat rule of an existing Series cannot be changed by import; its content and exceptions can.
- Refines ADR-0030 and ADR-0014.
