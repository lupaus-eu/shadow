# Frontend

## Primary Yearclock view

The primary Yearclock view is a responsive SVG rendered by React.

Each Yearclock in the Organization workspace is a `YearclockPlanner`
(`frontend/src/yearclock/`): Planning Window navigation, the SVG view, the
synchronized semantic summary, a details panel, the Event form, and the Lane
and Category structure editor. `geometry.ts` holds the pure date-to-angle,
range, month-scale, Lane-band, and today calculations and is unit tested with
`npm run test:unit` (Node's test runner, no extra dependency). Interaction and
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

