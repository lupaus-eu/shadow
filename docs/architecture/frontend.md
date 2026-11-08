# Frontend

## Primary Yearclock view

The primary Yearclock view is a responsive SVG rendered by React.

Each Yearclock in the Organization workspace is a `YearclockPlanner`
(`frontend/src/yearclock/`): Planning Window navigation, the SVG view, the
synchronized semantic summary, a details panel, the Event form, and the Lane
and Category structure editor. `geometry.ts` holds the pure date-to-angle,
range, month-scale, Lane-band, and today calculations and is unit tested with
`npm run test:unit` (Node's test runner, no extra dependency; code that needs a DOM runs in Vitest with jsdom, in the same command). Interaction and
visual rules are in `docs/design/README.md`.

- Months form the outer temporal scale.
- Lanes form concentric rings.
- Events render as date markers or date-range arcs.
- Every recurring Occurrence remains individually selectable.
- Dense Series, including weekly recurrence, use compact repeated markers and show the Series label once rather than repeating the full label at every Occurrence.
- Exceptions receive a stronger visual treatment than unchanged Occurrences.
- Categories provide color without making color the only carrier of meaning.
- Focus, selection, and interaction are managed by React.
- Geometry utilities calculate angles, positions, and arcs independently from presentation components.
- `planningWindow(start, months)` spans 1, 3, 6, 12, 18, or 24 whole months (Yearclock V2). `currentPeriod` picks the window containing today, `dayTicks` adds day marks to one-month windows, and the month ring has one segment per month. The planner stores the chosen length under `yearclock.length.{yearclockId}`. `isoWeek`, `weekScale`, and `quarterScale(window, startMonth)` produce the optional time-scale rings.
- Filtering (`src/yearclock/filters.ts`) is pure: `applyFilters` combines values with OR within a dimension and AND across dimensions, and `facetCounts` counts each option under the other dimensions. The planner filters the loaded window client-side before drawing the circle and the summary, and stores the choice under `yearclock.filters.{yearclockId}` (read and written inside try/catch).

## Accessibility

- Every interactive SVG element is keyboard reachable.
- Focus and selection have visible non-color indicators.
- Labels and state are exposed to assistive technology.
- A semantic Event summary remains synchronized with the SVG.
- Event ranges, Categories, and exception state never rely on color alone.

## Editing

- Selecting an empty Lane/date position opens a creation panel with context prefilled.
- Creating an Event uses familiar calendar-entry conventions: choose a date or date range, title, and optional recurrence.
- Event content is limited to a title, optional description, Lane, optional Category, optional location, and up to ten titled links (the editor is `LinksEditor`; start and end times are plain `time` inputs, shown by `displays/format.ts` (`dateLabel`, `timeLabel`) and ordered by `starts_at` in the list and agenda; the rules are in `yearclock/event-links.ts`) and a description that may be formatted (`DescriptionEditor` with its toolbar and preview, `description-format.ts` for the text edits, `rich-text.ts` and `RichText.tsx` to render it as React elements, never as HTML).
- Descriptions use plain text with preserved line breaks and safe URL auto-linking; Markdown and rich-text editing are outside v1.
- Product language and interfaces call these records Events, Series, and Occurrences rather than “calendar markings.”
- Selecting an Event opens a side panel for details and editing.
- On small screens, the side panel becomes a full-screen sheet.
- Forms use explicit validation, Save, and Cancel actions.
- Yearclock Viewers receive the same detail presentation in read-only mode.
- Drag-to-move and drag-to-resize are outside the first release.

## Organization routing

Authenticated application routes include the Organization identifier explicitly:

```text
/                                                     Organization list (one active Organization opens directly)
/organizations/{organization_id}                      overview
/organizations/{organization_id}/yearclocks/{yearclock_id}
/organizations/{organization_id}/yearclocks/{yearclock_id}/settings   Layout, Lanes, Categories, Plan a season again (Editors)
/organizations/{organization_id}/admin/{section}      people, groups, yearclocks, classification,
                                                      activity, support; billing and settings for Owners
/organization-signups/new
/organization-signups/{organization_id}
/invitations/{token}
/platform/*                                           operator console
```

Routing is React Router v7 in declarative mode (`BrowserRouter` in `App.tsx`,
customer `Routes` in `components/AuthenticatedShell.tsx`). There are no data
loaders; `OrganizationLayout` loads the Organization workspace once and hands it
to its nested pages through the outlet context, and `reload()` refreshes it
(and the sidebar) after structure changes. Onboarding and invitation acceptance
render in `SignedOutLayout`; every other signed-in page renders in `AppShell`
(`src/shell/`):

- a sidebar (`OrganizationSidebar`) with the Organization switcher, Overview,
  the Yearclocks (recent first, searchable above six), and the administration
  sections that `src/shell/nav.ts` allows the role (unit-tested). `NavLink`
  marks the current page with `aria-current="page"`;
- a top bar with the page title, which is the page's only `h1`
  (`usePageTitle`, also sets `document.title`), and the user menu (who is
  signed in, language, sign out as a form post to the backend);
- a skip link to `main#main-content`, and below 1024 px a navigation drawer
  that closes on navigation.

An unknown section or address inside an Organization shows a not-found alert.

Administration pages live in `src/admin/` (one module per area, rendered by
`AdministrationPage`), built from `Section` cards, row lists, tables, and empty
states; `SubscriptionNotice` is shared by the overview, the planner, and the
administration pages. The overview (`OrganizationHome`) keeps the Yearclocks,
recently opened ones, and My groups.

The Organization page is an overview: the accessible Yearclocks as links with a
name search (case- and accent-insensitive, `src/text-match.ts`), the five
recently opened Yearclocks, and My groups; administration is on its own pages
(below). Each Yearclock has
its own page with the planner; opening it records a visit
(`POST .../visit`). A Yearclock the user cannot open shows a not-found message
(Yearclock V2, P2 ticket 01).

The UI does not rely on one mutable active-Organization session value. Different browser tabs may safely display different Organizations.

## Platform console

`frontend/src/platform/` implements the console at `/platform`: platform
sign-in, service health, Organizations (Platform Admin), and failed jobs with
replay (Platform Admin), and Support Access requests with read-only views of approved content (Support Agent). The customer workspace shows a Support Access panel to Owners and Administrators. A customer account at `/platform`, or a platform
account in the customer application, is told to use the other application.

- The first-release operator console uses the same React and FastAPI deployment.
- Operator UI routes live under `/platform/`.
- Operator API routes live under `/api/v1/platform/`.
- The operator console uses the shared `ShellFrame` (`src/shell/AppShell.tsx`)
  with its own sidebar and a **Platform** badge, nested routes
  (`/platform`, `/platform/organizations`, `/platform/jobs`,
  `/platform/support`) filtered by platform role, and no active Organization
  context.
- Customer accounts are rejected at both UI and API boundaries.
- Organization lifecycle, subscription projections, support cases, Support Access, and audit information are visible according to platform roles.
- Customer content remains unavailable without an active approved Support Access grant.

## Deferred rendering modes

Calendar, list, embedded, and export-oriented views are outside the first release. The continuous timeline and view-model boundary must allow those modes later.

## Deferred Event features

- Event reminders and date-based notifications are outside the first release.
- V1 does not schedule email or in-product alerts from Event dates or recurring Occurrences.
- Task creation, assignment, execution state, and integrations are outside the
  first release and intentionally undefined.

## History and awareness (Yearclock V2)

- `src/yearclock/history.ts` formats Event history entries and computes the
  New and Changed marks (`changeMarks`). Both are pure and unit-tested.
- The Yearclock page records the visit and passes the returned Previous Visit
  to the planner. The planner loads `changes?since=` once per visit, and
  **Mark as seen** is local state.
- `src/yearclock/change-poll.ts` polls `changes?since=<loaded at>&limit=1`
  every 60 seconds while `document.visibilityState` is visible. It pauses
  while hidden and stops at the first change, which shows the notice.
  **Refresh** reloads the data and restarts polling from that moment. The
  baseline is the browser's clock at load time.
- There is no WebSocket or other real-time transport, and nothing merges
  automatically (V1 PRD Out of Scope).

## Displays (Yearclock V2 P5, ADR-0029)

`YearclockPlanner` renders one of several displays of the same Planning
Window from the same visible Events. The display (`circle`, `timeline`,
`list`, `agenda`) is local state, stored per Yearclock in `localStorage`
(`yearclock.display.<id>`, `src/yearclock/displays/display-mode.ts`; an
unknown or blocked value means the circle). Switching keeps the selection,
window, Filters, and any open Event drawer. The side panel (Details,
Filters, and Events for the circle) is shared; the agenda is the circle
card followed by a day-by-day list (`displays/agenda.ts` groups it).
The timeline lays Events out with the pure helpers in
`displays/timeline.ts` (track packing at the window's content width, click
position to date, axis rows) and the scale functions of `geometry.ts`; it renders
DOM buttons, not SVG, so every Event keeps a native focus target and name.
`src/yearclock/displays/` holds `placement.ts` (`placeEvents`, shared by every
display), `display-mode.ts`, `DisplaySwitch.tsx` (a radio group that is
hidden while only the circle exists), and one module per display.

## Notifications (Yearclock V2 P8, ADR-0031)

`frontend/src/notifications/` holds the bell (`NotificationBell`, polled every
minute and refreshed when the page marks notifications read), the inbox page
(`NotificationsPage`, route `/organizations/:id/notifications`), the API
client, and `text.ts`, which turns a notification's type and parameters into
a sentence and a link in the reader's language. `NotificationSettingsPage` (`/organizations/:id/notification-settings`) edits the per-kind in-app and email switches and the Summary choice (frequency and Yearclocks). The shell takes an `actions`
slot next to the account menu for the bell.

## Print and image export (Yearclock V2 P7, ADR-0030)

`src/exchange/` holds the browser-only part of P7: `ExportMenu` (a `Menu` in
the planner toolbar), `PrintSheet.tsx` (the print-only header, legend, and Event
list), `image.ts` and `png.ts` (the circle's PNG: computed styles inlined into
a copy of the SVG, drawn on a canvas at 2×, with pure size, legend, and file
name helpers). Printing uses `print:hidden` on the chrome, an `@page` rule in
`theme.css` (A4 landscape), and `@media print` rules in its components layer.
Nothing is sent to the server for printing or the image. File export posts
the window, Filters, and language to the export route
(`exchange/client.ts`, `ExportDialog.tsx`) and saves the response; import (`ImportDialog.tsx`, `import-file.ts`) previews and saves a file through the
import route; both dialogs are in the same menu. The Owner's Organization Export button is on
the Organization settings page (`admin/SettingsPage.tsx`, `exportOrganization`).

## Data transfer (ADR-0040)

- The route `/data-transfer` (`frontend/src/data-transfer/`) is in the shell outside any Organization, because a
  transfer spans Organizations. The account menu shows its entry only when
  `GET /api/v1/data-transfer/organizations` returns something.
- The page lists the scope, downloads the CSV, and previews an import (counts per Organization and kind, and
  the problems with row numbers) before the explicit save. Its Finnish and English text is in
  `data-transfer/messages.ts`, not in `i18n.ts`.

## Styling and components (Yearclock V2 redesign, ADR-0028)

- `src/theme.css` is the only stylesheet. It imports Tailwind's theme and
  utilities (no preflight reset), declares the semantic tokens with `@theme`,
  and has a base layer (page font, focus ring) and a components layer with
  the circle's SVG styles (`.yc-*`, on `--color-circle-*` tokens) and the
  `.ui-native` bridge. Layers: `theme, base, components, utilities`.
  Markup is styled with utilities and `src/ui` components; the only colour
  literals outside `theme.css` are user-chosen Category and Label colours.
- `src/ui/` holds presentational components (Button, Field, SegmentedControl,
  Card, Alert, Table…). They never fetch data. `src/shell/` holds layouts
  (`SignedOutLayout`, `AppShell`, `OrganizationSidebar`, and the nav model).
- `@fontsource-variable/inter` bundles the font into the build, so CSP keeps
  `font-src 'self'`.


## Structure canvas (model Structure tab)

The graph is drawn by diagram-js (ADR-0051) in `frontend/src/models/canvas/`. React renders the panels and forms; the
canvas is one `Diagram` created once in `ShadowCanvas.tsx` and never recreated on a render.

- `useGraphState(source)` is the only code that knows lines and events. It reads the state route
  (`GET .../lines/{line}/state`, with `?event_id=` for a chosen event, otherwise the line's last event) and returns plain
  `GraphData` (nodes, connections, types, allowed connections and the change markers `added`, `updated`, `removed`), the event,
  a status and `reload`. Nothing under `canvas/` imports line, event or version types.
- `diagram/GraphImporter` turns the data into shapes and connections and diffs against what is drawn: new elements are
  added, gone ones removed, only changed ones redrawn, so zoom, scroll and selection survive every load.
- `diagram/GraphRenderer` draws a node's shape from `node_types.shape` (rectangle, round rectangle, ellipse, diamond,
  hexagon; anything else is a round rectangle), its fill from the type colour with text in the more contrasting of dark and
  white, and a connection as a solid or dashed line with arrowheads from `source_end` and `target_end` and the type name as
  label. Names over 60 code points are shortened with an ellipsis in labels. Changed elements get a "+" or "~" badge and a
  CSS class, never colour alone.
- `diagram/GraphRules` encodes the Metamodel: a connection needs an allowed (connection type, source node type, target
  node type), may not join a node to itself and may not repeat a type between the same two nodes (the refusal cause is
  `self`, `not_allowed` or `duplicate`); a read-only Organization has no editing rules at all.
- `diagram/GraphModeling.applyEdit(edit)` is the one seam to the server. The change runs on the command stack at once,
  the sender (in `ModelCanvas.tsx`, using the existing event edit routes and the positions route) writes it, and when the
  server refuses (stale version, `chain_broken`, a rule, a network error) the change is undone with
  `commandStack.undo()` and the person gets the readable notice. Moves made with the mouse are collected and saved in
  one positions write 400 ms after the last one. Edits are sent one after the other, each against the event's freshly
  loaded version. After every write the state is loaded again, which replaces optimistic elements with the real ones.
- Navigation (ticket 03): `diagram/GraphNavigation` is the one place that moves the view (`setView` clamps the zoom to
  10 %-400 %): wheel and pinch (ctrl + wheel) zoom around the pointer, touch pan (one finger on the background) and pinch,
  space + drag, Fit (whole graph with 48 px padding, never past 100 %), 100 % around the centre, zoom steps of 1.25, and
  animation (160 ms) that is skipped under `prefers-reduced-motion`. It replaces the wheel handler of the library's
  `zoomScroll` (which stops at 20 % and scrolls on a plain wheel) and keeps Space away from the library's hand tool.
  `view.ts` holds the arithmetic and `ViewMemory`; `useCanvasView(key)` holds one memory per organization, model and line
  in React state (not browser storage): saves and reloads keep the view, `?line=` switching or leaving the tab starts a
  new one, and only the first load of a line is fitted automatically. `CanvasToolbar` (zoom out and in, readout, Fit,
  100 %) sits over the canvas inside `ShadowCanvas`. `keymap.ts` is the key map (`Keymap.register`, reachable as
  `ShadowCanvasHandle.registerKey`); `diagram/GraphKeys` connects it to the library's `keyboard` service, which fires only
  while focus is inside the drawing, and the keymap ignores text fields as well.
- Drawing and undo (ticket 05): `diagram/GraphDrawing` is the pointer drawing (the library's `connect` whose end it takes over, lasso mode,
  naming in place as an overlay input, a draft node that is neither on the command stack nor sent until named) and `GraphContextPad` the pad's
  Connect and Delete; they only ask the parent through handlers, and `ModelCanvas` applies the rules (`draw.ts`: `planConnection` gives create,
  choose or one of three refusals; `deleteSummary`; `freeSpot` for the centre placement), confirms deletes and sends. `applyEdit` gained
  `elements.delete` (one command, one write, nodes and loose connections; the connections touching a node leave with it, as on the server),
  `connection.reroute` and a created element's id coming back from the sender. The session history is `canvas/history.ts` (`GraphHistory`,
  owned by `GraphModeling`), **not** the diagram-js command stack: that stack still draws the optimistic change and is cleared on every load,
  because a load replaces optimistic elements and ids change (a deleted node brought back is a new element). Each entry holds plain steps
  (create, delete, rename, move, connect, delete connection, re-route) in both directions keyed by element id with an alias map for re-created
  ids; before running, the state is read afresh and the steps are checked against it (the element exists and is as the entry left it);
  then each step is one ordinary write. A refusal, a 409 or a 422 drops the entry; a network failure before the first write keeps it.
  Ctrl/Cmd+Z chords are on the library's `keyboard` service (`GraphKeys`); the single-key bindings (`C`, `L`, `Delete`, `F2`) come from
  `ModelCanvas` through the `keyBindings` prop. Positions are not event edits: a move is a positions write without a version, so only
  event edits can be stale.
- **Reading (ticket 06).** `diagram/GraphPopover.ts` is the hover and focus popover, an `overlays` overlay placed by `canvas/popover.ts` (`placePopover`, pure
  screen-pixel arithmetic: right, left, below, above, then clamped into the drawing area); it listens to `element.hover` and `element.out`,
  `focusin` and `focusout` on the diagram container, `drag.init`, `canvas.viewbox.changing` (a pan, meaning an unchanged scale, closes it) and
  `canvas.viewbox.changed` (a zoom puts it again). `shortenName` (`diagram/shapes.ts`) keeps 59 code points and an ellipsis over 60, and the
  type list uses it too. `GraphLayouter` offsets connections between the same pair of nodes (`parallelShift`), and `GraphImporter` lays a
  pair's connections out again when one is added or removed. The metrics of the selected node are read by `models/useNodeMetrics.ts` (it is outside
  `canvas/` because it calls the server; `canvas/node-metrics.ts` holds the pure selection and formatting): the line's metric list and each
  series once, kept in a ref for the life of the page, nothing read without a selected node, a failed read not cached.
- **Tidying, minimap and export (ticket 07).** `diagram/GraphTools.ts` is the service behind the toolbar's snap toggle, align buttons (library `align-elements`), distribute buttons (our `arrange.ts`) and Arrange (`layout.ts`, `elkjs` imported only when called). Each ends in `GraphModeling.arrange` or a flush, so it is one command, one `positions` write and one journal entry. Snapping is the library's `grid-snapping` for state and grid size, finished by `GraphTools.snapMove`; the choice is the per-person key `shadow.canvas.snap` (`canvas/snap.ts`, read by `ModelCanvas`, which passes `snap` and `onSnapChange`). `canvas/minimap.ts` attaches `diagram-js-minimap` after the first opening (the button's `aria-pressed` follows `minimapOpen` in `ShadowCanvas`; a failed load pops the button out and shows a notice); its view moves go through `GraphNavigation.setView`, and it leaves hidden types out. `canvas/export.ts` builds the SVG and PNG (`ShadowCanvasHandle.exportImage`), and the file name comes from `exportName` (model and line). A tool's outcome reaches `ModelCanvas` through `onToolResult` and is announced in the live region; a failure is a notice. The initial bundle does not contain `elkjs` or the minimap (build output in the ticket).
- diagram-js modules in use: `modeling`, `selection`, `move`, `outline`, `movecanvas`, `zoomscroll`, `keyboard`, `hand-tool`, `connect`, `connection-preview`, `context-pad`, `lasso-tool`, `overlays`, `align-elements` and `grid-snapping`; its CSS is imported
  into `theme.css` (layer `components`) and its `--bio-*` variables are defined from Shadow's colour tokens, so the canvas
  follows the theme. The remaining modules the design expects were verified to exist (ADR-0051).

## Model lines and events (model timeline ticket 09)

`ModelShell` reads the model, its lines (`GET .../lines`) and the events of the selected line (`GET .../lines/{line}/events`), and hands
them to the pages through the outlet context: `line`, `lines`, `events`, `event` (the shown event: `?event=`, else the line's last),
`eventIsLast`, `reloadEvents`, `role` and `canWriteLine`. `ModelCanvas` passes `event.id` to `useGraphState` and is read-only while
`eventIsLast` is false (ticket 08 of the structure canvas enables drawing into the shown event; until then edits go into the last event as
before) and calls `reloadEvents` after each write so the list's counts stay current. The line and event are URL parameters, so a reload and a shared
link show the same thing; no browser storage is used. `models/timeline.ts` holds the pure rules (line tree order, who may rename, delete,
adopt and write, event rows with the Now divider, `chainBrokenMessage` and the adopt and delete messages); `client.ts` keeps the structured
answer of a refusal on `RuleError.detail` and `ChainBrokenError.hint`, and answers 403 as `ForbiddenError`.
