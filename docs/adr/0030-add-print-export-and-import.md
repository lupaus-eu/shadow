---
status: accepted
---

# Add print, export, and import

## Context

The V1 PRD excluded "import/export" and "print and export-oriented views" so
that Yearclock would stay a focused planning tool. Teams still need to put a
Yearclock in a meeting, hand dates to a spreadsheet, load an existing plan,
and take their data with them when they leave. The GDPR guide also lists an
undefined export process as an open item. The review of 2026-10-05 (V2 P7)
weighed five Plandisc features against that scope.

## Decision

- **In:** printing and PNG (in the browser), Excel and CSV export, Excel and
  CSV import, and an Organization Export for Owners.
- **Out:** PowerPoint export, server-rendered PDF, importing Series or
  History, creating Lanes, Categories, or Labels from an import, and a
  per-person export of a user's own data (a documented manual process).
- **Who:** anyone who may read a Yearclock exports it, limited to what they may
  see; Editors, Admins, and Owners import into it; Owners download the
  Organization Export. Support Access never exports or imports.
- **Where:** printing and the image stay in the browser. Files and imports are
  handled by the backend, in one place that applies the access rule, the
  limits, and the Audit Log. The import is previewed first and saved all or
  nothing, parsed again on save so that the server stores no upload.
- **Safety:** every export and import is audited without content; hourly limits
  per user come from the Audit Log; exported text cells that look like
  formulas are neutralized; imported files are read as values only.

## Consequences

- The backend gains two pure-Python dependencies (`openpyxl` and
  `defusedxml`) and a Data exchange component, but no new service, table,
  or port.
- The V1 PRD's out-of-scope entries now read: calendar synchronization,
  conferencing, attendees, locations, and attachments remain out; import,
  export, and print are in (P8 reviews synchronization).
- A strict import trades convenience for predictability: a typo in a Lane
  name stops the import until the sheet is fixed.
- Refines ADR-0014 (the Audit Log records exchange actions) and ADR-0029
  (every display can be printed).
