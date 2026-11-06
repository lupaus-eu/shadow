# TASK-046 Metrics CSV File Picker

## Source Plan

Approved plan: remove the Metrics row CSV text input and make its `Import CSV`
button open a file picker that imports the selected CSV using the existing
client-side validation and draft-update flow.

## Goal

Replace the typed CSV import field in the Metrics grid with a row-specific
file-selection flow. A user should select a local CSV file by using the
existing `Import CSV` button, after which the selected file's contents are
validated and applied to that Timeserie's unsaved draft values.

This changes only how CSV content enters the existing import workflow. The
supported two-column `date,value` CSV format, validation rules, draft behavior
and persistence flow remain unchanged.

## Requirements

- Remove the per-row CSV textarea from the Metrics grid.
- Remove CSV textarea state, props and styling that become unused.
- Add a row-specific native file input that selects one CSV file and is not
  presented as a separate visible form field.
- Configure the picker to accept CSV files (`.csv` and `text/csv`). Treat this
  as a picker hint; continue to validate the file contents with the existing
  CSV parser.
- Make the existing `Import CSV` button open the corresponding row's file
  picker. It must no longer depend on typed CSV draft content to become
  enabled.
- Read the selected file in the browser and pass its text to the existing CSV
  import parsing and validation logic for that row's Timeserie.
- Preserve the current successful-import behavior: valid values update only
  the selected row's drafts, add their dates as grid columns, mark the row as
  changed and show the existing success notice.
- Preserve the current validation behavior for malformed rows, invalid dates,
  invalid time-unit start dates and invalid typed values.
- Allow choosing the same file again after an import attempt by resetting the
  file input value after its selection has been handled.
- Keep both the Import CSV button and its associated file input unavailable
  while any row or bulk save is in progress.
- Do not add dependencies, upload files to the backend, or change existing API
  endpoints or payloads.

## Acceptance Criteria

- [ ] The Metrics grid no longer renders a CSV textarea or another visible CSV
      text-entry field for a Timeserie row.
- [ ] Each Timeserie row provides an `Import CSV` button that opens a
      CSV-restricted native file picker for that row.
- [ ] Selecting a valid CSV file imports its `date,value` rows into only the
      selected Timeserie's unsaved draft values and adds the imported dates to
      the grid.
- [ ] Valid comma- and semicolon-separated CSV rows retain their current
      import behavior.
- [ ] A selected CSV with an invalid date, an invalid time-unit start date, an
      invalid typed value or any row that does not contain exactly date and
      value shows the current user-visible validation error and does not apply
      a partial import.
- [ ] Cancelling the picker changes no draft values and shows no import error.
- [ ] The same selected file can be imported again after a previous selection.
- [ ] Import controls are disabled while saving, consistent with the rest of
      the Metrics editing controls.
- [ ] Existing Metrics save, refresh, manual-date and cell-editing behavior is
      unchanged.
- [ ] No new dependency, backend endpoint, API contract, database schema or
      migration is introduced.
- [ ] Relevant frontend tests, lint and build/type checking pass.

## Out Of Scope

- Changing the accepted CSV structure, adding header support, quoted-field
  parsing, multi-row imports or a CSV preview.
- Persisting imported values automatically; users continue to save imported
  drafts through the existing row or bulk-save controls.
- Backend file upload, server-side parsing, API changes, database migrations or
  changes to Timeserie value validation rules.
- Changes to Timeserie metadata, authorization, authentication or workspace
  navigation.

## Implementation Notes

Relevant sources:

```text
frontend/src/features/metrics/MetricsTab.tsx
frontend/src/features/metrics/MetricsTab.test.tsx
frontend/src/styles/app.css
docs/architecture/domains/ORG_STATES.md
docs/operations/testing.md
```

- Keep the CSV parsing function as the single source of the existing format
  and validation rules. Adapt its caller to receive selected file text instead
  of textarea state.
- Associate the button and native input with the correct Timeserie row so a
  file selected for one row cannot affect another row.
- Use the browser File API available in the current React/TypeScript frontend;
  do not add a parsing or upload library.
- The file input's `accept` attribute improves picker filtering but must not be
  treated as content validation or a security boundary.
- Reset the input's selection after handling both successful and rejected
  imports so a change event fires when the user selects the same file again.
- The `Import CSV` button should be accessible by name and continue to be
  operable by keyboard. Keep the native input available to assistive technology
  in a semantically appropriate way while avoiding an additional visible input
  control.

## Testing

Required:

- [ ] Frontend component tests for the button-to-picker interaction, valid file
      import, each existing CSV validation failure, cancel behavior, repeated
      selection of the same file and save-time disabling.
- [ ] Manual verification in Metrics with a selected scenario and a CSV file
      containing valid `date,value` data.
- [ ] Lint.
- [ ] Build and TypeScript type checking.

Not applicable:

- [ ] Backend tests: no backend behavior changes.
- [ ] Integration tests: existing frontend component tests cover this local
      browser-file interaction; no external service is introduced.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Manual verification:

1. Select a scenario and open Metrics.
2. Click `Import CSV` on a Timeserie row and select a valid local `.csv` file
   containing `date,value` rows.
3. Confirm values and date columns appear as unsaved changes only on that row.
4. Select a malformed or invalid-value CSV and confirm the existing validation
   notice appears without partially changing the row.
5. Cancel the picker and confirm no state changes.
6. Import the same valid file a second time, then save the changed row and
   refresh to confirm the normal persistence flow remains intact.

## Documentation

No documentation update is expected because the public API, Timeserie data
model and CSV content contract do not change. Update `docs/architecture/domains/ORG_STATES.md`
or `docs/operations/testing.md` only if implementation changes those documented contracts
or adds reusable file-import testing guidance.

## Notes For AI Agent

- Read `AGENTS.md`, `docs/architecture/overview.md`, this task, `docs/operations/testing.md`,
  `docs/architecture/domains/ORG_STATES.md` and `docs/adr/0001-tech-stack.md`
  before implementation.
- Implement only this frontend interaction change; do not alter the CSV
  format, API, persistence semantics or validation rules beyond connecting the
  file picker to the existing parser.
- Do not add dependencies.
- Add or update frontend tests for every changed user-visible behavior.
- Report the changed files and exact verification results when finished.
