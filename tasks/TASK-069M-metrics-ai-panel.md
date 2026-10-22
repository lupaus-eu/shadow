# TASK-069M Metrics Tab AI Panel And Change-Set Review

## Source Plan

This task is part of the approved plan "AI chat via MCP for generating Schatten
model and timeseries data", accepted on 2026-10-21. See
[TASK-069A](TASK-069A-ai-mcp-architecture.md) and ADR-015.

The AI chat happens in the user's own AI client. The Metrics tab is where users
connect that client and where they review and apply what the AI proposed.

## Goal

Add a toggleable AI panel to the Metrics tab. It holds connection instructions,
the connected clients, and change-set review with apply and reject.

## Requirements

- Changes to `frontend/src/features/metrics/MetricsTab.tsx` are limited to a
  toolbar toggle and the panel slot, so the 1351-line component does not grow
  further. The panel uses the existing side-panel layout pattern from
  `StructureTab` / `.structure-workspace`.
- Add these components to `frontend/src/features/ai/`:
  - `AiPanel.tsx`: tabs or sections for Connect, Connections and Change sets.
  - `ConnectInstructions.tsx`:
    - the read and write MCP URLs (`<origin>/api/mcp/read`, `/api/mcp/write`)
      with copy buttons;
    - short steps for Claude Desktop / claude.ai (custom connector) and Claude
      Code (`claude mcp add --transport http …`).
    - Skill download links and the plugin instructions are not part of this
      task. TASK-069N adds them after this task is merged.
  - `ChangeSetList.tsx`: the organisation's change sets with status badges.
    - By default it shows change sets whose derived `scenario_key` is the
      selected scenario, plus change sets without a scenario reference
      (`includeUnscoped=true`).
    - A toggle shows all of the organisation's change sets.
  - `ChangeSetReview.tsx`:
    - readable operations (for example "Create node *Revenue* (Goal)" and
      "Edge *Revenue → Company* (MEASURED_BY)");
    - for each timeserie, a values table and an inline SVG sparkline, with no
    chart dependency;
    - validation errors;
    - a clear warning badge on every operation with `replaces_existing`,
      showing its summary of the data it replaces (patched node fields with
      their current values, or the existing value count and date range). A
      summary line before Apply counts these operations. The flags come from
      the detail endpoint, which recomputes them against current data. They
      are the reviewer's safeguard, because apply validates but does not
      otherwise detect staleness.
    - creator, and the client as its `clientId` plus the client name,
      isolated (`<bdi>` or `dir="auto"`) and labelled self-declared;
    - a "missing target" state for any operation whose target was deleted
      after submit, as reported by the detail endpoint; apply will then fail
      re-validation;
    - Apply and Reject with an optional note, both requiring confirmation.
      Apply sends the `reviewFingerprint` of the detail currently shown. On
      `409 review_stale` the panel reloads the change set, shows that the
      replaced data changed, and requires a fresh confirmation. On the
      retryable `409 apply_in_progress` or `503` it keeps the shown review,
      says the change set is busy (normally another apply is running) or the
      server was busy, and offers "Try again" without reloading or
      re-confirming. On the terminal
      not-submitted `409` it reloads and shows the change set's current
      status.
  - After Apply, the metrics grid reloads and the user is notified of the
    created keys.
- Opening `…/metrics?changeSet=<key>` (the review URL returned by
  `submit_change_set`) opens the panel on that change set.
- Reuse `ConnectionsList` from TASK-069L. Extend `frontend/src/api/ai.ts`.
- `MCP_ENABLED` handling uses the session's `features.mcp` flag from
  TASK-069E.
  - When it is false, the Connect section is hidden.
  - The panel toggle is shown only when the organisation has change sets or
    the user has connections. Review, apply and reject keep working, because
    the review API stays registered.
- The existing Structure tab "AI Assistant" placeholder mode
  (`GraphEditorToolbar.tsx`, `StructureTab.tsx`) is unrelated to this panel
  and stays unchanged. Removing or repurposing it is a separate decision.
- Add CSS to `frontend/src/styles/app.css` under the `.ai-panel*` names.

## Acceptance Criteria

- [ ] Vitest tests cover:
      - panel toggle and deep link;
      - list and review rendering for every operation type;
      - apply success and the grid reload;
      - apply conflict (409), reject, and validation-error display;
      - the default scenario filter with unscoped change sets, and the
        "all" toggle;
      - the `replaces_existing` warning badges and the summary count;
      - the client shown as `clientId` plus the isolated, self-declared name;
      - the "missing target" state for a target deleted after submit;
      - apply sending the shown `reviewFingerprint`, and the
        `review_stale` reload with re-confirmation;
      - the retryable `409 apply_in_progress` and `503` keeping the review
        and offering "Try again", distinct from the terminal 409 reload;
      - hiding the Connect section when `features.mcp` is false.
- [ ] Existing `MetricsTab.test.tsx` tests pass unchanged.
- [ ] No new frontend dependency is added.
- [ ] The layout works at the existing desktop widths and degrades to a stacked
      layout on narrow screens.

## Out Of Scope

- An in-app LLM chat or calling an LLM.
- Editing change-set operations in the UI. AI clients do that through MCP.
- Skills content (TASK-069N).

## Implementation Notes

Read before implementation:

```text
AGENTS.md
docs/decisions/ADR-015-ai-via-mcp.md
docs/domains/AI.md
docs/concepts/AI_CHANGE_SET.md
docs/TESTING.md
frontend/src/features/metrics/MetricsTab.tsx
frontend/src/features/structure/StructureTab.tsx
frontend/src/workspace/WorkspaceSelectionContext.tsx
tasks/TASK-069K-change-set-review-api.md
tasks/TASK-069L-mcp-consent-connections-ui.md
```

## Testing

Required:

- [ ] Frontend tests
- [ ] Manual verification (review and apply a change set staged from Claude
      Code; verify the grid and graph)
- [ ] Format check
- [ ] Lint
- [ ] Build

```bash
cd frontend
pnpm format:check
pnpm lint
pnpm test
pnpm build
python3 ../scripts/ai_review_records.py validate
```

## Documentation

Update `ARCHITECTURE.md` (Metrics tab), `docs/domains/AI.md`, and the LikeC4
model if the UI responsibilities change.

## Notes For AI Agent

- Branch: `feature/TASK-069M-metrics-ai-panel`.
- Do not start until TASK-069K and TASK-069L are merged.
- Save each Step 13 review record under `docs/ai-reviews/TASK-069M/`.
- Report all changed files and every verification command run.
