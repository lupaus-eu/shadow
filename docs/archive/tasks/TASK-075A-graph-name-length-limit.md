# TASK-075A Graph Name Length Limit

## Source Plan

Developer-approved plan (2026-11-05) for three Structure page tasks, done in
this order: TASK-075A (this task), TASK-075B, TASK-075C. They are independent
in behaviour but edit some of the same files (`EdgeForm.tsx`,
`StructureTab.test.tsx`), so they land one after another.

The developer reported: a node saved with a very long name causes an error,
and after navigating away and back the Structure graph renders empty because
its content cannot be loaded. Edge names are probably affected too. The
developer asked whether a 60-character limit on the form name fields is a good
fix.

The developer approved:

- a maximum of 60 characters for node and edge names;
- enforcing the limit in the backend as well as in the forms, because the REST
  API and MCP change sets do not go through the forms;
- a graph display that copes with long names already stored;
- no migration and no database constraint. Existing longer names stay
  readable and must be shortened when they are edited.

## Goal

Node and edge names can no longer exceed 60 characters, whichever way they are
written. A long name that is already stored can no longer make the Structure
graph look empty.

### Background

Findings on 2026-11-05 in the local development environment:

- The local database holds a node in the `reality` scenario whose name is a
  single 27,300-character word without spaces ("Loremipsum…"). Its key,
  derived from the name by `uniqueGraphKey` in `StructureTab.tsx`, is 27,305
  characters.
- The backend accepted and served it without errors. The create request
  returned 201 and every later graph load returned 200 (about 60 KB). The Caddy
  and backend logs show no failed request around that save, so the failure
  is in the frontend.
- Cytoscape node and edge labels use `text-wrap: wrap` with `text-max-width`
  120 and 140 (`GRAPH_STYLES` in `GraphViewer.tsx`). This wraps only at
  whitespace, so the label is one line of roughly 190,000 px. `GraphViewer`
  calls `cy.fit()`, which includes labels, and sets no `minZoom`. The graph
  therefore zooms out until every node is invisible.
- This was inferred from the code and the stored data, not seen on screen: the
  built-in browser does not trust the local Caddy certificate. Reproduce it
  before fixing it.
- Nothing limits name length:
  - the forms have no `maxLength`;
  - the API schemas `GraphNodeCreateRequest`, `GraphNodePatchRequest`,
    `GraphEdgeCreateRequest` and `GraphEdgePatchRequest`
    (`backend/app/api/v1/org_twin_structure/schemas.py`) only set
    `min_length=1`;
  - the database columns are `TEXT`.
- The REST create `id` has no maximum length either. Keys appear in URL paths
  such as `PATCH /graph/nodes/{key}`. AI change-set keys are already limited
  to 128 characters (`MAX_KEY_LENGTH` in
  `backend/app/api/v1/ai_change_sets/schemas.py`).
- AI change-set node and edge create operations reuse `GraphNodeCreateRequest`
  and `GraphEdgeCreateRequest`, so a limit there also applies to MCP.

## Requirements

### Backend

- Add `GRAPH_NAME_MAX_LENGTH = 60` to
  `backend/app/api/v1/org_twin_structure/schemas.py`.
- Reject a `name` longer than 60 characters in `GraphNodeCreateRequest`,
  `GraphNodePatchRequest`, `GraphEdgeCreateRequest` and
  `GraphEdgePatchRequest`, with a 422 validation error and the message
  "Name must be at most 60 characters."
- Count the length after trimming, the same way the existing blank-check
  validators strip the value, so a 60-character name with surrounding spaces
  is accepted.
- Limit `id` in `GraphNodeCreateRequest` and `GraphEdgeCreateRequest` to 128
  characters, matching the change-set key limit. Use one shared constant
  rather than two separate numbers.
- AI change-set operations reuse `GraphNodeCreateRequest`,
  `GraphNodePatchRequest` and `GraphEdgeCreateRequest`, so an operation with a
  too-long name or key is rejected when it is added.
- Stored change-set operations are re-parsed with the same schemas whenever a
  change set is read, validated, submitted or applied, applied ones included.
  Re-read them without the name and key limits (a validation context set by
  `engine._staged`), so change sets staged before this task keep working. This
  was found in AI review round 1.
- Responses and reads do not validate name length. Existing longer names keep
  loading.
- No migration and no database constraint.

### Forms

- Add a frontend constant for the 60-character limit and use it in
  `NodeForm.tsx` and `EdgeForm.tsx`.
- The Name inputs get `maxLength={60}` and the hint "Max 60 characters.",
  linked with `aria-describedby`. Pasted text is cut to 60 characters by the
  browser.
- When an edit form opens on a stored name longer than 60 characters, the
  input shows the full name. The submit button stays disabled and the form
  shows "Name must be at most 60 characters." until the trimmed name is short
  enough.

### Graph Display

- In `GraphViewer.tsx`, node and edge labels show at most 60 characters of the
  name. A longer name shows its first 60 characters followed by "…". The type
  line of the label is unchanged.
- Add `"text-overflow-wrap": "anywhere"` to the node and edge label styles, so
  a word wider than the label wraps instead of growing the label.
- The hover popover title shows the same shortened name, and long words wrap
  in it (`overflow-wrap: anywhere`). Without shortening, a 27,300-character
  name would make the popover thousands of lines tall.
- In the node list (`NodeList.tsx`), long names stay inside the side panel
  without horizontal overflow. The existing one-line ellipsis of
  `.entity-row__title` already does this, so no change is needed there.

## Acceptance Criteria

- [ ] Creating or renaming a node or edge through the REST API returns 422
      with "Name must be at most 60 characters." for a 61-character name and
      succeeds for a 60-character name.
- [ ] A 60-character name with leading and trailing spaces is accepted and
      stored trimmed.
- [ ] Creating a node or edge with an `id` longer than 128 characters returns
      422.
- [ ] An AI change-set operation with a 61-character node or edge name is
      rejected with the name error when it is added.
- [ ] The Name inputs in Create node, Edit node, Create edge and Edit edge do
      not accept more than 60 characters.
- [ ] An edit form opened on a stored name longer than 60 characters cannot be
      saved until the name is shortened, and says why.
- [ ] With the 27,300-character node present, the graph loads and shows the
      other nodes. The long node's label is truncated with "…", and the node
      can be selected, renamed and deleted.
- [ ] Long names are shortened in the hover popover and stay inside the node
      list.
- [ ] A change set staged with a name longer than 60 characters before this
      task can still be read and applied.
- [ ] No migration, database constraint or new dependency.

## Out Of Scope

- Cleaning up names longer than 60 characters in any database. Existing
  names stay until someone edits them.
- Limits on descriptions, attributes, type names or timeserie names.
- MCP skill text or plugin version changes.
- Changing how node and edge keys are generated.
- A minimum zoom level for the graph.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/architecture/overview.md
docs/architecture/domains/ORG_TWIN_STRUCTURE.md
docs/architecture/domains/AI.md
docs/operations/testing.md
```

- Files expected to change:
  - `backend/app/api/v1/org_twin_structure/schemas.py`;
  - `backend/tests/test_org_twin_structure_api.py`;
  - `backend/tests/test_ai_change_set_engine.py` or
    `backend/tests/test_ai_change_sets_api.py` for the change-set case;
  - `frontend/src/features/structure/NodeForm.tsx` and `EdgeForm.tsx`;
  - `frontend/src/features/structure/GraphViewer.tsx` and
    `GraphViewer.test.tsx`;
  - `frontend/src/features/structure/NodeList.tsx` or
    `frontend/src/styles/app.css` for wrapping;
  - `frontend/src/features/structure/StructureTab.test.tsx`.
- Reproduce the empty graph first. The local `reality` scenario already holds
  the long node. Use it for the manual check, then delete it through the UI.
  Do not edit the database by hand.
- `GraphViewer.test.tsx` mocks Cytoscape. Assert on the label data and the
  styles passed to the mock.
- No new dependencies, ADR or diagram changes.

## Testing

Required:

- [ ] Backend tests:
  - nodes and edges, create and patch: 60 characters accepted, 61 rejected
    with the message, trimming counted correctly;
  - create with a 129-character `id` rejected;
  - change-set operations with a 61-character node or edge name, or a
    129-character key, are rejected.
- [ ] Frontend tests:
  - Name inputs have `maxLength` 60 and the hint;
  - an edit form with a stored long name blocks saving and shows the message;
  - `GraphViewer` truncates long node and edge names with "…" and keeps
    shorter names unchanged;
  - the label styles include `text-overflow-wrap: anywhere`.
- [ ] Manual verification at `https://app.localhost`: the graph with the long
      node loads and fits, the node can be selected and deleted, and a pasted
      long name is cut to 60 characters.
- [ ] Format check
- [ ] Lint
- [ ] Build (includes the TypeScript check, `tsc -b`)
- [ ] Backend lint and typecheck

Commands:

```bash
cd frontend
pnpm format:check
pnpm lint
pnpm test
pnpm build
cd ../backend
uv run ruff check .
uv run pytest
uv run pyright
cd ..
python3 scripts/ai_review_records.py validate
```

## Documentation

- `docs/architecture/domains/ORG_TWIN_STRUCTURE.md`: in the API contract section, state
  that node and edge names are 1-60 characters after trimming, create keys are
  at most 128 characters, and existing longer names stay readable but must be
  shortened when edited.
- `docs/architecture/domains/AI.md`: only if it lists graph payload constraints for change
  sets.
- No architecture, ADR, concept, data or diagram changes.

## Notes For AI Agent

- Use the branch `fix/TASK-075A-graph-name-length-limit` from `main`.
- Implement only this task's scope.
- Do not add dependencies.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-075A/`.
- Report all changed files and every verification command run.
