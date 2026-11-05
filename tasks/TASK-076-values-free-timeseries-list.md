# TASK-076 Values-Free Timeseries List

## Source Plan

Follow-up to AI review finding F-007 of TASK-075C, round 1
(`docs/ai-reviews/TASK-075C/review-001.json`, category `regression`, severity
`info`). The finding's summary:

> Every Timeserie panel mount reloads all of the scenario's timeseries with
> all their values.

Its rationale: the panel remounts after every link save, Unlink and
create-and-link, and each mount requests the scenario's timeseries list, which
the backend returns with every value by default. TASK-075C mandated this list,
so it was not an implementation defect, but large scenarios pay for it on every
link change. The review recommended "a follow-up for a values-free timeseries
list or for keeping the list across panel remounts".

Round 4 (`docs/ai-reviews/TASK-075C/review-004.json`) recorded F-007 as
`accepted_risk`: the developer accepted the full list reload for TASK-075C and
planned a follow-up for a values-free timeseries list, noted in the pull
request description. TASK-075C was merged as PR #133 (commit `6beb64c`).

On 2026-11-05 the developer asked for this follow-up to be written as a task
document, and then approved its implementation with option A of decision D1
below.

## Goal

The Structure page's Timeserie panel loads its link dropdown options, each
timeserie's id and name, without the backend reading or returning any
timeserie values. The Metrics, Predictions and Summary tabs keep receiving the
full list with values exactly as now.

### Background

- **Where the list is loaded:** `TimeseriePanel.tsx` calls
  `fetchTimeseries(orgId, scenarioId, signal)` when it mounts (line 339). It
  keeps only each item's `id` and `name`. These feed the link dropdown options
  and the status cards' Name row.
- **Why it is loaded often:** `StructureTab.tsx` keys the panel on the
  scenario, the node and both links (line 802). So the panel remounts, and
  reloads the list, after every link save, Unlink and create-and-link that
  changes a link. It also remounts when another node is selected.
- **What the endpoint does:**
  - `fetchTimeseries` calls
    `GET /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/timeseries`
    (`backend/app/api/v1/org_states/router.py`, `list_scenario_timeseries`);
  - the route calls `org_states_service.list_scenario_timeseries` with its
    default `include_values=True`;
  - the service then reads every active value of every active timeserie in
    the scenario (`_active_values_by_timeserie_id`) and returns them in each
    `TimeserieResponse.values`.
- **Cost:** the database read and the response grow with the scenario's total
  number of values, though the panel uses none of them. The longer load also
  widens the loading window that TASK-075C handles for timeseries created or
  deleted while the list loads (review-001 F-001).
- **The service already supports it:**
  - `list_scenario_timeseries(..., include_values=False)` returns the same rows
    with empty `values` and reads no values;
  - it was added for the MCP `list_timeseries` tool (TASK-069H) and is covered
    by `backend/tests/test_mcp_tools.py`;
  - `docs/domains/ORG_STATES.md` currently states that it has no REST route.
- **Other callers of the same endpoint.** All of them read `values` and must
  keep receiving them unchanged:
  - `MetricsTab.tsx` (line 499): the metrics table, value editing and derived
    values;
  - `PredictionsTab.tsx` (line 337): the current Reality series in the
    prediction chart (`predictionChart.ts`);
  - `SummaryTab.tsx` (line 118): the summary timeline rows
    (`summaryTimeline.ts`).

  The frontend has no other caller. The MCP tool calls the service function
  directly, not the REST route.
- **Not affected:** the panel's per-id existence checks
  (`fetchTimeserieExists`, `GET .../timeseries/{timeserie_key}/exists`) read
  no values and stay as they are.

## Decision For The Developer

**D1: a query parameter on the existing list, or a new values-free endpoint.**

**Decided 2026-11-05: option A.** The developer chose the `includeValues`
query parameter on the existing list. The options are kept below for the
record; requirements and criteria marked "option B" do not apply.

Both options stay within the existing ADRs: a REST read inside the existing
Org States domain, reusing an existing service option, with no new technology,
schema or integration. Neither needs an ADR.

**Option A: query parameter on the existing list**

- `GET .../scenarios/{scenario_key}/timeseries?includeValues=false`: a boolean
  `Query(alias="includeValues")` that defaults to `true`, like
  `includeUnscoped` in `backend/app/api/v1/ai_change_sets/router.py`. It is
  passed to the service's `include_values`.
- The response model stays `list[TimeserieResponse]`. With `false`, every
  `values` is `[]`.
- Pros:
  - the smallest change: the route, schema and service already exist;
  - mirrors the MCP tool's `include_values`.
- Cons:
  - an empty `values` does not tell "left out" from "has no values";
  - a REST client that reads `values` from such a response silently gets
    wrong data;
  - `TimeserieResponse.values` is documented as the timeserie's values.

**Option B: a new values-free endpoint**

- For example
  `GET .../scenarios/{scenario_key}/timeserie-summaries`, returning
  `list[TimeserieSummaryResponse]`: the `TimeserieResponse` fields without
  `values`. Its exact field set is part of the decision. The panel needs only
  `id` and `name`.
- The new path must not be a fixed segment under `/timeseries/`. Timeserie
  keys may be any non-blank string (`_normalise_stable_key`), so for example
  `/timeseries/summaries` would collide with `GET /timeseries/{timeserie_key}`
  for a timeserie whose key is `summaries`.
- Pros:
  - an explicit contract with no ambiguous empty `values`;
  - typed separately in the backend and the frontend.
- Cons:
  - a new route, response schema and API documentation;
  - one more list endpoint to keep consistent with the existing one.

**AI suggestion (not a decision):** option A, with a separate frontend client
function whose items have no `values` field (see Requirements). This keeps the
backend change minimal, and the frontend type keeps the panel and any later
caller from reading an empty `values` list as data. The remaining ambiguity
affects only direct REST clients, which explicitly ask for
`includeValues=false`.

## Requirements

These apply to both options unless marked.

### Backend

- The values-free list returns the same timeseries as the existing list:
  - the scenario's active timeseries, derived metrics included;
  - sorted by timeserie key, as now;
  - the same field values apart from `values` (option B: the chosen fields).
- It reads no timeserie values: the service runs with `include_values=False`.
- **Authorization:** the same as the existing list, through the
  `org_states` router's `require_business_request` dependency. An unknown or
  deleted organisation or scenario gets the same 404 as on the existing list.
- **Existing list unchanged:** `GET .../timeseries` without the new parameter
  returns exactly what it returns now, values included. Option A's default is
  `true`.
- No migration, schema change or new dependency.

### Frontend

- **Client function:** `frontend/src/api/timeseries.ts` gets a client function
  for the values-free list, for example `fetchTimeserieOptions` or
  `fetchTimeserieSummaries`. It returns items typed without `values`, under
  either option. `fetchTimeseries` and its type stay as they are.
- **Panel:** `TimeseriePanel` loads its options with the new function instead
  of `fetchTimeseries`. It keeps all TASK-075C behaviour:
  - the request is aborted on unmount;
  - the dropdowns are disabled while the list loads;
  - a failed load shows the same closable alert and leaves the create/edit
    region working;
  - timeseries created or deleted while the list loads are still applied to
    it;
  - the options, their `{id} – {name}` labels and sorting, and the Name row
    are unchanged.
- **Other tabs:** Metrics, Predictions and Summary keep calling
  `fetchTimeseries`. Their requests and behaviour are unchanged.

### MCP

- The MCP `list_timeseries` tool and its output are unchanged.

## Acceptance Criteria

- [x] D1 is recorded in this task before implementation starts (option A).
- [ ] Mounting the Timeserie panel requests the values-free list, and the
      panel never calls `fetchTimeseries`.
- [ ] For a scenario with number, string, boolean and derived timeseries,
      plus a soft-deleted timeserie and soft-deleted values, the values-free
      list returns the same timeseries in the same order as the existing list,
      with no values.
- [ ] A backend test shows that the values-free request reads no timeserie
      values. For example, it records the executed SQL statements, or checks
      that the service runs with `include_values=False`.
- [ ] The existing list is unchanged: the existing
      `test_timeseries_list_returns_sorted_rows_and_active_sorted_values`
      passes without modification.
- [ ] An unknown organisation or scenario returns the same 404 on the
      values-free list as on the existing list. Anonymous requests are rejected
      as on every business route.
- [ ] Option B only: no existing `/timeseries/{timeserie_key}` route is
      shadowed.
- [ ] Metrics, Predictions and Summary still request and show values.
- [ ] The TASK-075C panel tests still pass. Only their mocks change from
      `fetchTimeseries` to the new function.
- [ ] No migration, dependency, ADR or MCP change.

## Out Of Scope

- **Keeping the list across panel remounts:** the review's other suggestion,
  such as lifting the list into `StructureTab` or caching it. It would also
  remove the repeated request, but it changes the panel's lifecycle and
  TASK-075C's loading-window handling. If wanted, it gets a separate task.
- Changing the panel's remount key.
- Values-free lists, paging or value bounds for Metrics, Predictions or
  Summary.
- Changing the existence check endpoint.
- Changing the MCP `list_timeseries` tool, including the full value read
  behind `include_values=true`, which ADR-015's resource protection accepts.
- Server-side search or paging of the link dropdown options.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/domains/ORG_STATES.md
docs/domains/ORG_TWIN_STRUCTURE.md
docs/TESTING.md
tasks/TASK-075C-timeserie-panel-link-and-create.md
```

- Files expected to change:
  - `backend/app/api/v1/org_states/router.py`: the query parameter (A) or the
    new route (B);
  - `backend/app/api/v1/org_states/schemas.py`: option B only, the summary
    response model;
  - `backend/app/api/v1/org_states/org_states_service.py`: no change expected
    for option A. For option B, reuse
    `list_scenario_timeseries(include_values=False)` instead of a second
    query;
  - `backend/tests/test_users_organisations_api.py`: the new list tests, next
    to `test_timeseries_list_returns_sorted_rows_and_active_sorted_values`;
  - `frontend/src/api/timeseries.ts`: the new client function and type;
  - `frontend/src/api/timeseries.test.ts`: new. There is no timeseries client
    test today; follow `orgTwinStructure.test.ts`;
  - `frontend/src/features/structure/TimeseriePanel.tsx`;
  - `frontend/src/features/structure/TimeseriePanel.test.tsx` and
    `StructureTab.test.tsx`: both mock `fetchTimeseries` today.
- **Authorization tests:** `backend/tests/test_api_authorization.py` builds its
  route sweep from the OpenAPI schema. A new route (option B) is therefore
  covered by the anonymous-request sweep without editing that file. Check that
  it appears there.
- **Stale sentence:** `docs/domains/ORG_STATES.md` says the service's
  `include_values=False` list has no REST route and that the REST timeserie
  responses are unchanged. Update that sentence.
- **Size:** expect roughly 150-250 lines including tests; option A is at the
  lower end.
- **No ADR and no diagram change:**
  - no ADR, because a REST read in the existing domain that reuses an existing
    service option does not change architecture or technology;
  - no diagram change, because the PlantUML and LikeC4 diagrams do not show
    REST endpoints at this level.

## Testing

Required:

- [ ] Backend tests:
  - the values-free list's rows, order and empty or missing `values`, using
    the scenario described in the acceptance criteria;
  - no value read for the values-free request;
  - the unknown organisation and scenario 404s;
  - option A: `includeValues=true` and the parameter left out both return
    values;
  - option B: a timeserie whose key equals the new path segment is still
    reachable through `GET .../timeseries/{timeserie_key}`, if the path could
    collide.
- [ ] Frontend tests:
  - the new client function's URL (and query string for option A), its abort
    signal and the mapping of its response;
  - the panel requesting the values-free list on mount and not calling
    `fetchTimeseries`;
  - the existing TASK-075C panel tests passing with the switched mocks: the
    loading state, load failure, options, Name row, and creates and deletes
    during loading.
- [ ] Manual verification at `https://app.localhost`:
  - in the browser's network panel, a panel mount and a link save request the
    values-free list, and its response holds no values;
  - the link dropdowns and the Name row work as before;
  - Metrics, Summary and Predictions still show values.
- [ ] Format check, lint and build (frontend)
- [ ] Ruff, pytest and pyright (backend)

Not applicable:

- [ ] Migration tests. Reason: no schema change.

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

- `docs/domains/ORG_STATES.md`:
  - option A: document the `includeValues` parameter on the timeserie list
    endpoint;
  - option B: add the new endpoint to "Timeserie endpoints" with its response
    shape;
  - both: update the paragraph on `list_scenario_timeseries(include_values=False)`.
- `docs/domains/ORG_TWIN_STRUCTURE.md`: in the Timeserie panel paragraph
  (TASK-075C), note that the options come from the values-free list.
- `docs/TESTING.md`: in the Timeserie panel coverage under "Testing Structure
  Feature", mention the values-free list, and note the backend list test.
- No architecture, ADR, concept, data or diagram changes.

## Notes For AI Agent

- D1 is option A.
- Use the branch `feature/TASK-076-values-free-timeseries-list` from `main`.
- Implement only this task's scope.
- Do not add dependencies.
- Save the redacted Step 13 review records under `docs/ai-reviews/TASK-076/`.
- Report all changed files and every verification command run.
