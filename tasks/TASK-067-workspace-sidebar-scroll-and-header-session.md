# TASK-067 Workspace Sidebar Scroll And Header Session Controls

## Source Plan

Developer-approved plan (2026-10-19) for two workspace layout issues:

1. The Users, Events and Scenarios tab sidebars (`aside.main-detail-sidebar`)
   do not scroll when their content does not fit. The overflow is clipped.
2. The signed-in user's name and the Sign out button should be shown inside
   `.workspace-header__top`, to the right of the Org state dropdown, instead
   of in the separate session bar above the workspace.

The developer decided to:

- keep the role (Admin / Consultant) shown under the user name as it is now,
  with the two lines fitting on the same row as the Sign out button;
- include detail-pane scrolling. Once the tab has a fixed height, long detail
  content would otherwise be clipped.

## Goal

In the Users, Events and Scenarios tabs, the sidebar and the detail pane each
scroll on their own when their content is taller than the available space. The
tab toolbar and workspace header stay in place. In the workspace, the user
identity and Sign out are part of the workspace header, which gives the tab
content back the vertical space of the separate session bar. Pages without a
workspace header keep the current session bar.

### Cause

- `.workspace-content` has `overflow: hidden`.
- `.management-tab` only has `min-height: 100%`, so it grows taller than
  `.workspace-content` and the overflow is clipped instead of scrolled.
- `.main-detail-sidebar` has `min-height: 100%` and no `overflow`, and
  `.detail-workspace` has no `overflow` either.
- Customers already scrolls correctly through its own overrides
  (`.customers-tab`, `.customer-layout`, `.customer-sidebar`,
  `.customer-workspace`). This task applies the same pattern to the shared
  classes.

## Requirements

### Sidebar And Detail Pane Scrolling

- `.management-tab` fills the height of `.workspace-content` and does not grow
  beyond it: `height: 100%`, `min-height: 0`, `overflow: hidden`. Its grid rows
  (`auto minmax(0, 1fr)`) stay as they are.
- `.main-detail-layout` clips to its grid row (`overflow: hidden`).
- `.main-detail-sidebar` scrolls vertically when its content does not fit:
  `min-height: 0` (replacing `min-height: 100%`) and `overflow-y: auto`. The
  sidebar still fills the full height of the layout row and keeps its
  background and border when its content is short.
- `.detail-workspace` scrolls vertically when its content does not fit:
  `min-height: 0` and `overflow-y: auto`.
- The tab toolbar (`.tab-toolbar`) does not scroll with either pane.
- In the existing `@media (max-width: 760px)` block, where the layout becomes
  one column, the whole layout scrolls as one: `.main-detail-layout` gets
  `overflow-y: auto` and `align-content: start`, and the sidebar and detail
  pane get `overflow: visible`. This matches the Customers rule at 900px.
- Customers keeps its current behaviour. Its overrides have the same
  specificity as the shared rules and come later in the stylesheet. Verify that
  this still holds after the change.

### Session Controls In The Workspace Header

- `SessionControls` (`frontend/src/auth/SessionControls.tsx`) gets a
  `variant` prop: `"bar"` (default, the current look and markup) or
  `"header"`.
- The `"header"` variant:
  - shows the user name with the role (`Admin` / `Consultant`) on a second
    line under it, as the bar does now, and the Sign out button to the right
    of them on the same row;
  - keeps the identity block no taller than the 32px workspace dropdowns
    (two lines of `--text-meta-size` with `--text-meta-lh`), so
    `.workspace-header__top` does not get taller;
  - truncates a long name with an ellipsis instead of wrapping it;
  - uses `<div role="group" aria-label="Current user session">` as its root
    instead of `<aside>`, so it does not create a complementary landmark
    inside the banner;
  - is separated from the dropdowns by a subtle left divider;
  - still shows `authError` in small error text, without pushing the Sign out
    button off its row;
  - keeps the "Signing out..." disabled state.
- In `WorkspaceShell` (`frontend/src/pages/Workspace.tsx`), the right side of
  `.workspace-header__top` becomes a new `.workspace-header__actions` wrapper
  containing `WorkspaceIndicators` followed by
  `<SessionControls variant="header" />`. The session controls sit outside
  `.workspace-indicators`, whose aria-label is "Current workspace context".
- `App.tsx` does not render the separate session bar on workspace routes
  (`/schatten/:orgId/*`, matched with `useMatch`). The home page and the 404
  page keep the `"bar"` variant, since they have no workspace header.
- Developer decision after AI review round 1 (finding F-001): while the
  workspace route is loading, or after it fails to load, the workspace header
  does not exist yet. In those states the workspace route's Suspense fallback
  and error fallback show the `"bar"` variant above the loading or error
  panel, so Sign out stays available. `RouteErrorBoundary` gets an optional
  `errorPrefix` prop for content shown before its error panel.
- Under 760px, where `.workspace-header__top` becomes a column,
  `.workspace-header__actions` wraps: the dropdowns come first and the session
  controls follow, aligned to the start.
- Do not set `overflow` on the header or the actions wrapper, because the
  dropdown panels must not be clipped.

## Acceptance Criteria

- [ ] In the Users, Events and Scenarios tabs, a sidebar whose content is
      taller than the available height scrolls vertically on its own. The tab
      toolbar and workspace header stay in place.
- [ ] A detail pane whose content is taller than the available height scrolls
      vertically on its own.
- [ ] A sidebar with short content still fills the full height of the layout.
- [ ] Under 760px, the stacked sidebar and detail pane scroll together as one
      column.
- [ ] Customers layout and scrolling are unchanged.
- [ ] On workspace routes, the user name, role and Sign out button are shown
      in `.workspace-header__top` to the right of the Org state dropdown, on a
      single row, and the header is no taller than before.
- [ ] On workspace routes there is exactly one Sign out button, and the
      separate session bar is not rendered.
- [ ] On the home page and the 404 page, the separate session bar is shown as
      before.
- [ ] While a workspace route is loading or has failed to load, the separate
      session bar is shown with the only Sign out button.
- [ ] Sign out works from the workspace header: it shows the
      "Signing out..." state and logs out exactly as before.
- [ ] The workspace dropdown panels open and are not clipped.

## Out Of Scope

- Changing the Customers, Structure, Metrics, Summary or Predictions tab
  layouts.
- A user menu, avatar or other new session features.
- Changing logout behaviour, authentication or the session API.
- Redesigning the workspace header, the tabs or the dropdowns beyond adding
  the session controls.
- Backend, API or migration changes.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/TESTING.md
```

- Files expected to change:
  - `frontend/src/styles/app.css`: `.management-tab`, `.main-detail-layout`,
    `.main-detail-sidebar`, `.detail-workspace`, the 760px media block, the
    new `.workspace-header__actions` and the header variant styles next to
    the existing `.session-controls` rules.
  - `frontend/src/auth/SessionControls.tsx`: the `variant` prop.
  - `frontend/src/pages/Workspace.tsx`: `.workspace-header__actions` and the
    header session controls.
  - `frontend/src/App.tsx`: hide the bar on workspace routes.
  - `frontend/src/App.test.tsx`: new tests.
  - `frontend/src/components/DeferredRoute.tsx`: the `errorPrefix` prop.
  - `frontend/src/App.workspace-fallback.test.tsx`: loading and error
    fallback tests with a stand-in Workspace module.
- Only Users, Events, Scenarios and Customers use `management-tab` and
  `main-detail-*`. None of the sidebars contains an absolutely positioned
  popover, so the new `overflow` rules do not clip menus.
- `.main-detail-sidebar` shares the base rule with `.detail-card`. Change only
  the sidebar-specific rule.
- `.workspace-header__top` already uses `justify-content: space-between`, so
  `.workspace-header__actions` replaces `WorkspaceIndicators` as its second
  child and needs `min-width: 0` for the existing truncation to keep working.
- Expect roughly 150 changed lines. No new dependencies, no ADR and no diagram
  changes.

## Testing

Required:

- [ ] Frontend tests (`frontend/src/App.test.tsx`):
  - on a workspace route, the banner contains the user name, the role and the
    Sign out button, and the page has exactly one Sign out button;
  - on `/`, the separate session bar ("Current user session") with the Sign
    out button is shown;
  - signing out from the workspace header calls the logout endpoint with CSRF,
    as the existing test does from `/`;
  - the existing logout tests, which render `/`, still pass unchanged.
- [ ] Frontend tests (`frontend/src/App.workspace-fallback.test.tsx`): while
      the workspace route is loading, and after it fails to load, the session
      bar with the only Sign out button is shown, and sign out works from the
      error state.
- [ ] Manual verification at `https://app.localhost`:
  - with enough users, events or scenarios to overflow the sidebar, check that
    the sidebar scrolls on its own in Users, Events and Scenarios;
  - with a long detail pane (for example a scenario with many org states),
    check that the detail pane scrolls on its own;
  - check widths of 1280px, 900px and 700px;
  - check that the header shows name, role and Sign out on one row at the same
    height as before, that a long name is truncated, and that all three
    dropdown panels open without being clipped;
  - check that the home page still shows the session bar;
  - check that Customers is unchanged.
- [ ] Format check
- [ ] Lint
- [ ] Build (includes the TypeScript check, `tsc -b`)

Not applicable:

- [ ] Backend tests. Reason: frontend-only change.
- [ ] Automated scroll tests. Reason: jsdom does not compute layout, so
      overflow and scrolling are verified manually.

Commands:

```bash
cd frontend
pnpm format:check
pnpm lint
pnpm test
pnpm build
cd ..
python3 scripts/ai_review_records.py validate
```

## Documentation

- `docs/TESTING.md`: add the workspace-header session-controls coverage to the
  frontend authentication UI tests paragraph in "Authentication Harness".
- No architecture, ADR, domain or diagram changes.

## Notes For AI Agent

- Use the branch `fix/TASK-067-workspace-sidebar-scroll-and-header-session`.
- Implement only this task's scope.
- Do not add dependencies.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-067/`.
- Report all changed files and every verification command run.
