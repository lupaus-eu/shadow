# Design documentation

Keep durable Yearclock UI and UX principles, interaction patterns,
accessibility decisions, and visual-system guidance here. Feature-specific UI
exploration belongs in its `.scratch/<feature>/technical-design.md` until the
decision is stable enough to guide future work. Technical boundaries are in
[`docs/architecture/frontend.md`](../architecture/frontend.md).

The visual system (tokens, contrast, type, components, layouts) is in
[`ui-foundation.md`](ui-foundation.md). Follow it for every new or changed
screen.

## Circular Yearclock

Code: `frontend/src/yearclock/` (`geometry.ts`, `YearclockView.tsx`,
`YearclockPlanner.tsx`).

- **Time runs clockwise from 12 o'clock.** One full turn is exactly the
  12-month Planning Window. Each day gets an equal slice, so month segments
  follow their real length (February is visibly shorter than January).
- **Lanes are concentric bands.** The first Lane in Lane order is the
  outermost band. Lane order is changed with Up/Down controls, never by drag.
- **Point and range Events have different shapes.** A single-day Event is a
  circle in the middle of its Lane band; an inclusive date range is an arc.
  A range that starts or ends outside the window is clipped and described as
  continuing from or into the neighbouring window.
- **Category colour is never the only signal.** Markers use the Category
  colour, but the accessible name, the semantic summary, and the legend always
  name the Category.
- **Changed Occurrences stand out without colour.** A changed single-day
  Occurrence is a diamond instead of a circle, and a changed range is dashed.
- **Dense Series stay readable.** A Series with 13 or more visible
  Occurrences draws small markers and one Series label; the summary groups it
  as one expandable entry.
- **Today and elapsed time appear only when today is in the window.** A red
  radial line marks today, a light wash covers the elapsed share, and the
  centre and a text line state the date and the elapsed percentage.

## Interaction

- Every marker is focusable in chronological, then Lane, order. Enter or
  Space selects it. Focus and selection add a dark outline, not only a colour
  change.
- The semantic summary lists the same Events as the circle, in the same
  order, with dates, Lane, Category, and state. Selecting either one selects
  the same Event.
- The planner is one toolbar card above a two-column area (V2 redesign,
  ticket 06):
  - the toolbar holds the **Length** segmented control (a radio group with
    arrow keys), previous/next period and month as icon buttons with names,
    **Start month**, **Current period**, the changes badge, **New Event**,
    the search, and the window range;
  - the circle card takes the remaining width and at most the screen height
    less the toolbar (`.yc-view`);
  - the side panel (380 px, sticky on wide screens) has the tabs **Events**
    (with **Select Events** docked on top), **Details** (only while an Event
    is selected, with its History), and **Filters** (the tab says how many
    Events are hidden);
  - below 1024 px the panel follows the circle.
- Creating and editing happen in the Event drawer (`Drawer`, 480 px from the
  right, full width on phones). It is modal: focus stays inside, Escape and
  **Cancel** close it, and focus returns to **New Event** or **Edit**. Save
  errors appear at the top of the drawer.
- Layout, Lanes, Categories, **Plan a season again**, and copying or linking
  Lanes live on **Yearclock settings**
  (`/organizations/:org/yearclocks/:id/settings`), linked from the toolbar
  for Editors, as cards in two columns on wide screens.
- Selecting an Event, on the circle, in the list, or from search, opens the
  **Details** tab; **Close** returns to **Events**. Viewers see the same
  details as Editors, without mutation controls.
- Editors can select an empty point on a Lane band to open the Event form
  with that Lane and date filled in. The **New Event** button offers the same
  form for keyboard and assistive-technology users.
- Forms use explicit **Save** and **Cancel**. Validation mirrors the API
  limits: title up to 200 characters, description up to 10,000, an `http(s)`
  link up to 2,048, and an end date on or after the start date.
- A stale save reloads the latest version into the form and explains that
  someone else changed the Event.
- Accessibility is verified automatically with axe (WCAG 2.1 A and AA rules)
  on the planner, the details panel, the Event form, and the phone layout
  (`frontend/tests/browser/yearclock-accessibility.spec.ts`), together with a
  keyboard journey through every marker. Automated checks do not replace a
  manual screen-reader review before release (ticket 23).
- Descriptions are plain text: line breaks are kept and `http(s)` addresses
  become links that open in a new tab with `noopener`.

## Displays (Yearclock V2 P5)

- A **Display** radio group in the planner toolbar (arrow keys move and
  select) chooses how the Planning Window is drawn: **Circle** (the default),
  and, as they are added, **Timeline**, **List**, and **Agenda**. It sits
  after the window controls and is hidden while only the circle exists.
- The choice is personal and remembered per Yearclock in the browser. Every
  display shows the same Events under the same Filters, and selecting an
  Event opens **Details** whichever display it was chosen in.
- The **Events** tab shows for the circle only; the list, the agenda, and the
  timeline show the Events themselves.
- **Timeline:** a card holding a horizontally scrolling grid (at least 64 px
  per month and 720 px wide) with a sticky 168 px Lane column. The axis rows
  are decorative (`aria-hidden`): months (short, with a two-digit year when
  the window crosses a year end; the long month for 1 month), ISO weeks for
  windows up to 3 months or when the week ring is on, days for 1 month, and
  quarters when that ring is on. Each Lane is a `group` named with the Lane;
  tint, tall height (76 px minimum), the read-only style (italic name) and an
  empty "Lane not available" row follow the circle. Events are buttons named
  like circle markers. A single-day Event is a dot with its title, a range
  a bar with a 22 % Category tint and a 4 px Category edge (title in ink, so
  contrast never depends on the Category colour), a dense Series dots with one
  title, exceptions are diamonds, and clipped ends show a triangle and a square
  edge. Overlaps stack into tracks (28 px, 48 px on touch screens). The
  selected Event has an ink outline and a changed one a warning outline. A red
  line marks today. Choosing an empty point on an editable Lane starts a new
  Event for that date.
- **Agenda:** the circle card, then a card that lists the window's Events by
  month (a sticky level 3 heading) and day (a level 4 heading with the weekday
  name from `Intl`, uppercase by style only). Each Event is a button named
  like a circle marker, with Category colour, Lane, and change mark. The
  selected row has the accent-soft background and scrolls into view inside the
  card (at most 28 rem high) without moving the page. Events that began
  before the window are on its first day and say so. There is no bulk
  selection in the agenda.
- **List:** a card with a table. Columns: Date, Title (a button named like a
  circle marker), Lane, Category with its colour, and Labels. Date, Title, and
  Lane are sortable: the header holds a button, `aria-sort` states the order,
  and a triangle shows it; a second choice reverses. A dense Series is one
  row with a chevron button (`aria-expanded`) that opens its Occurrences,
  indented. The selected row has the accent-soft background, and change marks
  show next to the title. **Select Events** and its actions sit in a card
  above the table, and the checkbox column appears while selecting. Below
  640 px the header is hidden, each row is a card with labelled lines, and a
  **Sort by** select shows above; targets are 44 px on touch screens.

## Export menu and printing (Yearclock V2 P7)

- **Export** is a small button with a download icon in the planner toolbar,
  before **Yearclock settings**. It opens a menu: **Print**, and **Download
  image (PNG)** while the circle is the display. Later tickets add Excel, CSV,
  and Import.
- The printout hides the sidebar, top bar, toolbar, side panel, notices, and
  overlays (`print:hidden`) and uses A4 landscape with 12 mm margins on a white
  background with colours kept. A print-only header (Yearclock name, window,
  print time from the `beforeprint` event) comes first, then the chosen display,
  then a legend (Lanes, Categories with colour swatches), then the Event list
  on a new page for the circle and the timeline (a Series is one row).
- The PNG draws the circle (its computed styles written inline, because a
  standalone SVG loses the stylesheet) on a white canvas at 2×, with a title
  and subtitle above and the legend below. The font is a system sans-serif.

### Export dialog (P7)

- **Export to Excel…**, **Export to CSV…**, and **Export to calendar (.ics)…** (after a separator in the Export
  menu) open a dialog titled "Export Events" with a short note that the file
  holds only what the user may see and that the export is logged. Two radio
  groups: *What to export* (the current window with its dates, with the note
  "Your Filters are applied." while Filters are on; the whole Yearclock) and
  *File format* (Excel, CSV, calendar file). **Export** downloads the file, closes the dialog,
  and shows the "Export saved." toast; a refusal or failure stays in the dialog
  as an alert, and a 429 states the minutes to wait.

### Organization Export (P7)

- On **Organization settings**, a card "Organization Export" sits between the
  details and the danger zone: a sentence on who may do it, one line of what is
  included and one of what is left out, an alert for failures and rate limits,
  and **Download Organization Export** (a button with a download icon) that
  shows "Preparing the file…" while it works and the toast "Organization Export
  saved." when done.

### Import dialog (P7)

- **Import from Excel or CSV…** shows in the Export menu for Editors, after a
  separator. The wide dialog (880 px) holds a file field, **Download template**,
  and, once a file is chosen, the preview as a live region: a success alert
  ("N Events will be created, M skipped.") with a table of the Events to create
  (row, title as the row header, dates, Lane, Category, Labels; the first 50),
  and a list of skipped rows with reasons; or, when there are problems, a danger
  alert with a table of row, column, and problem (the first 50). **Import N
  Events** is disabled until a preview without problems exists. A refused file,
  a rate limit, or an unsupported type shows as an alert under the file field.
  Saving closes the dialog and shows the "N Events imported." toast.

## Time-scale rings (Yearclock V2)

- The month ring is always outermost. Optional quarter and week rings, each
  14 units wide, sit just inside it (quarters outside weeks), and the Lane
  bands narrow to make room, so nothing is drawn beyond the month labels.
- Rings are decorative (`aria-hidden`): the window range is in the circle's
  accessible name and in the range text. Week numbers are shown for every
  week up to 6 months, every second week up to 12, and every fourth beyond.

## Centre preview (Yearclock V2)

- Pointer enter and keyboard focus on a marker show its title (shortened to
  22 characters), date, and Lane in the circle centre, replacing the Today
  text while shown; leaving or blurring the marker clears it.
- The preview is `aria-hidden`: the focused marker's accessible name already
  carries the same information. It never selects the Event or moves focus.

## Lane tints and heights (Yearclock V2)

- A Lane tint is one of the 12 Label palette colours drawn at 14 % opacity as
  the Lane band's background, so Category colours on markers keep their
  contrast (checked by axe). A tall Lane gets two shares of the ring width.
- Tints never carry meaning alone: the Lane name is in every marker's
  accessible name and in the list.

## Search (Yearclock V2)

- A `search` landmark above the Planning Window controls holds one labelled
  field and a **Search** button that stays disabled below two characters.
- A polite status reports the number of matches or that none matched.
  Results are buttons in date order with date, title, Lane, Category, and
  Labels; **Load more** appends the next 50.
- Choosing a result moves the Planning Window to the Event's year when the
  Event is outside the window, then opens its details. When recurring
  Occurrences match, a note explains they are found about a year ahead.

## Filters (Yearclock V2)

- The **Filters** panel replaces the Category legend below the planner. It has
  one fieldset per dimension (Lanes, Categories with **No Category**, Labels)
  of "show only" checkboxes; nothing ticked means everything shows.
- Each option shows its facet count, `Name (N)`: the Events in the window it
  would show given the other dimensions' choices. Category and Label options
  carry their colour swatch beside the name, never instead of it.
- A polite live status states how many Events are hidden and holds the only
  **Show all** action, so the effect of every change is announced.
- Hidden Events leave both the circle and **Events in this window**. Filters
  are personal, stored per Yearclock in `localStorage`, and forget values that
  no longer exist.
- Categories of Linked Lanes' source Yearclocks get their own fieldset per
  source, "Categories from <Yearclock>", after the Yearclock's own Categories.
  They filter and count like own Categories.

## Selection mode (Yearclock V2)

- Editors turn on **Select Events** (a toggle button with `aria-pressed`)
  above the circle. **Events in this window** then shows a checkbox before
  each Event, named "Select <title>, <date>".
- Recurring occurrences show a disabled checkbox described by the visible
  note that they change through their Series.
- **Select all shown** selects the Events that the Filters show. A polite
  status states the number selected.
- Each action (move to a Lane, set a Category, add or remove a Label, delete)
  asks for confirmation with the count. A refusal leaves everything unchanged
  and says why in an alert: a stale selection, the bulk size, or the Label
  limit.

## Preview before a batch (Yearclock V2)

- Changes that create many Events, such as **Plan a season again**, have two
  steps. **Preview** states what will happen in a status message: how many
  Events will be created and in which date range, how many already exist and
  will be skipped, or that a limit would be exceeded. Only then does a
  primary **Create N Events** button appear, carrying the number.
- Changing any choice clears the preview, so the confirmation always matches
  what is shown.

## Linked Lanes (Yearclock V2)

- A Linked Lane is drawn like an own Lane, with its own tint and height. Its
  name everywhere (summary list, accessible names, Filters, details) is
  "<source Lane> (from <source Yearclock>)", so the origin is always stated
  in text.
- It has no create target on the circle, and new Event forms and batch
  actions never offer it.
- A Lane the viewer may not read keeps its place as an empty, dashed band
  named "Lane not available"; a source in recoverable deletion says "Lane no
  longer available". Neither reveals source names.
- Linked Event details are read only: a note says where the Event belongs, and
  **Open in <Yearclock>** is a plain link to that Yearclock's page.
- In **Lanes**, a Linked Lane row has no name field and shows "Linked: …"
  beside its tint and height controls.

## Event history (Yearclock V2)

- **History** is a closed `details` disclosure at the end of Event details.
  It loads when opened and shows a polite status while loading, when empty,
  or when it fails.
- Each entry has a headline (the reason, such as "Label Draft merged into
  Final", or the kind of change), then time · actor, then one line per
  changed field in the form "Field: old → new". Description and link only say
  "… changed".
- Removed Lanes, Categories, and Labels read "(removed)". A former member
  reads "Former member", and Support Access reads "Support".
- **Show older changes** pages by 50.
- Editors see **Restore this version** on every entry except the newest
  (named "Restore the version from <time>"). It opens an inline group titled
  the same, listing "Field: current → restored", notes for left-out
  Category and Labels, and a Lane select when the Lane is gone. **Restore**
  and **Cancel** follow. A conflict appears as the page alert; success
  appears as the page status.

## Changes since the last visit (Yearclock V2)

- Events that others created or changed since the Previous Visit carry a
  **New** or **Changed** badge in **Events in this window**. On the circle
  the word is part of the marker's accessible name, and a darker outline
  adds a visual cue that never stands alone.
- A badge in the toolbar ("N changes") toggles a panel, "Changes since your
  last visit (N)", between the toolbar and the circle; it is open when the
  page loads. It lists each change newest first: title — kind · time · actor.
  A Series change appears once with its number of occurrences. Deleted
  Events have **Restore** for Editors.
- **Mark as seen** removes the panel and all badges for the rest of the
  visit. A first visit, or no changes, shows nothing.

## Notifications (Yearclock V2 P8)

- A bell icon button at the right of the top bar, before the account menu,
  inside an Organization. Its accessible name is "Notifications" or
  "Notifications, N unread"; a small accent badge shows the count (99+ at most)
  and is hidden from assistive technology because the name already says it.
  It is a link to `/organizations/:id/notifications`.
- The page "Notifications" has one card: the description, an **Unread only**
  checkbox and **Mark all as read**, then an ordered list. A row shows an
  "Unread" badge, the sentence (bold while unread), the date and time, an
  **Open** link when the Yearclock can still be opened, and **Mark as read**.
  **Load more** pages the list. The empty state says "No notifications."

### Notification settings (P8)

- `/organizations/:id/notification-settings`, reached from **Settings** on the
  Notifications page. One card with a list of kinds in a group "Your access and
  role" and, for Owners and Admins, "Organization notices". A row has the
  name, a one-line hint, and two checkboxes ("In the app", "By email") whose
  accessible names include the kind. **Save settings** saves all rows and shows
  the "Settings saved." toast; a failure stays in the card as an alert.

- Below the notification kinds, a group "Summary of upcoming Events" with a
  radio group (Off, Weekly on Mondays, Every day) and a short description. When
  it is not off, a second radio group chooses all readable Yearclocks or only
  those picked from a checkbox list of the Organization's Yearclocks.

## Subscription card (Yearclock V2 P14)

- On **Billing and seats**, the card "Subscription" shows one status sentence
  (active with the next payment date, cancellation scheduled with the end date,
  grace with its deadline, or read-only), **Manage billing**, and **Cancel
  subscription** (a danger button) or **Undo cancellation**. Cancel opens a
  dialog with the end date, what happens afterwards, the seat-decrease note, an
  optional reason select, **Cancel subscription** and **Keep subscription**; a
  failure stays in the dialog as an alert. Success closes it and shows a toast.

- When the subscription has ended the card says so, hides the cancel controls,
  and shows **Subscribe again**: a short explanation, a **Seats** number field
  with the minimum in its hint, and **Continue to payment**. Back from Checkout
  the card says it is waiting for confirmation and reloads the state every few
  seconds; a cancelled Checkout says the payment was not completed.

## Billing contact (Yearclock V2 P14)

- Below the seat card on **Billing and seats**, a card "Billing contact" with a
  one-paragraph explanation, **Billing name** and **Billing email** fields on one
  row and **Save billing contact** (disabled until something valid has changed).
  Success shows the "Billing contact saved." toast; a failure or the daily limit
  stays in the card as an alert, with the hours to wait for the limit.

## Ownership (Yearclock V2 P14)

- **People** has a **Transfer ownership** button in its heading (Owners, not
  while read-only). Its dialog explains an Owner's powers, has a **New Owner**
  select of active Administrators and Members, **Keep me as an Owner** with
  a hint, a reminder that the billing contact is unchanged, and
  **Transfer ownership**; without candidates it says to invite someone.
- Choosing Owner in a person's role select opens a confirmation first; declining
  restores the list.
- A **Leave** button sits on the signed-in person's own row. The only Owner gets
  a dialog with a **New Owner** select and **Transfer and leave**; the only
  person in the Organization gets a notice instead. Others confirm and leave.

## Location and links (Yearclock V2 P11)

- The Event editor has a **Location** text field and, in place of the single
  link field, a **Links** group: each row is a "Link N" group with a **Link
  text** and an **Address** field and icon buttons to move it up or down or to
  remove it; **Add link** adds a row (disabled at ten). Problems are listed
  above **Save**, which stays disabled until they are fixed.
- The panel shows the location in its definition list and the links as a list of
  titled anchors that open in a new tab. The list display shows the location
  under the title, the agenda after the lane and category, and the print list
  under the title with each link as "text: address".

## Formatted description (Yearclock V2 P11)

- Under the **Description** field: a **Use text formatting** checkbox (on for new
  Events, off for older ones). When on, a toolbar "Formatting" with icon buttons
  **Bold**, **Italic**, **Bulleted list**, **Link**, and **Preview** (a toggle
  button) sits beside it, with a one-line hint about the syntax. Pressing a
  button wraps or prefixes the selection and keeps focus in the field; the link
  button selects the address placeholder. **Preview** shows the formatted text in
  a labelled region below. The panel renders formatting as bold, italic, lists,
  and links that open in a new tab with `noopener noreferrer`; markup that is not
  part of the subset shows as text.

## Time of day (Yearclock V2 P11)

- The Event editor has **Start time (optional)** and **End time (optional)** time
  fields after the dates; the end field is disabled until a start time is set,
  and clearing the start clears the end. A problem (an end that is not after
  the start on a one-day Event) is listed above **Save**.
- The date shows with the times everywhere it appears: "10 Mar 2026,
  14:00–16:00" for one day and "10 Mar 2026 14:00 – 12 Mar 2026 10:00" for a
  range. The agenda puts the time before the title; same-day Events are ordered
  all-day first, then by start time. The circle is unchanged.

## Change notice (Yearclock V2)

- When others change the open Yearclock, a bordered polite status above the
  circle says so, with **Refresh**. It appears at most about a minute after
  the change and never interrupts typing or moves focus. It stays until the
  user refreshes.

## Organization-wide Access (Yearclock V2)

- The Yearclock **Access** section starts with a labelled select, "Everyone
  in the Organization", with the options No access, Viewer, and Editor. A
  note below it explains that it applies to current and future members, and
  that stronger access still wins.
- Changing it to Editor opens a confirmation that states how many members
  gain edit access. Cancelling keeps the previous choice.

## Groups (Yearclock V2)

- **Groups** is a collapsible panel on the Organization page, like
  **Classification**. Each Group is a labelled region with its name, its
  member count, rename and delete controls, its members with **Remove
  <name>**, and an **Add member: <Group>** select with **Add**.
- Deleting a Group always states its impact in the confirmation.
- **My groups** appears near the Yearclock list only for members who belong
  to a Group. It shows each Group's Yearclock access, or a note that the
  Group gives none.
- In a Yearclock's **Access**, a **Groups** subsection lists the Groups with
  access. Each has a role select named "Role for Group <name>" and a remove
  button named "Remove access for Group <name>". Below it, a Group select, a
  role select, and **Grant** add a Group. The subsection appears only once
  the Organization has Groups.

## Bulk invitations (Yearclock V2)

- **Invite several people** is a disclosure inside **Invite people**. It has a
  labelled textarea with a described hint, a role select, and a **Groups to
  join** fieldset. The single invitation form offers the same fieldset.
- **Preview** always comes first. Its status lists how many people will be
  invited and the skipped addresses with reasons, or the number of seats
  still needed. Only a preview without a seat shortfall shows **Send N
  invitations**.

## Access overview (Yearclock V2)

- **Access** in **People** is a toggle button (`aria-expanded`) named "Access
  for <person>". It opens a region of the same name, where each Yearclock
  shows its role and a nested list of readable sources, such as "Group Board:
  Editor", "Direct: Viewer", "Everyone in the Organization: Viewer", or
  "Administrator (sees every Yearclock)".
- **Who has access** in a Yearclock's **Access** works the same way per
  person.
- **Remove** confirms first and names the Yearclocks that will be lost.

## Data transfer page

Code: `frontend/src/data-transfer/`. A page reached from the account menu (it is not in an Organization): the
Organizations in scope, a *Download CSV* action, and an import in three steps: choose a file, read the preview
(a table of new, changed, and unchanged rows per Organization and kind, a warning when Events changed after the
export, and a problem table with row numbers), then an explicit *Save import* that stays disabled while any
problem remains. Messages are plain language and never show ids except as the offending value.

## Model lines, change list and change editor (model timeline ticket 09)

Code: `frontend/src/models/ModelShell.tsx`, `timeline.ts` (pure rules and refusal wording), `timeline-messages.ts`, `timeline/`
(`LineBar`, `ChangePanel`, `ChangeEditor`, `refusals.ts`). A model has one **Base line** (what has really happened) and any
number of **Scenarios** (what-if copies of a line). The shown line is `?line=` (the Base line when absent), the shown change
`?change=` (the line's last change when absent); both are carried by the tab links.

- **Line bar.** A select lists the Base line first and each Scenario right under the line it starts from (indented, with
  an arrow). The kind is always a word and a colour: the bar and badge are teal for the Base line and blue for a Scenario.
  Buttons appear only when the person may use them: *New scenario from here* (any Member; starts from the shown change and
  asks a name in a dialog that keeps the typed name when the name is taken), *Rename* (Base line: Owner or Admin; Scenario:
  its creator, an Owner or an Admin), *Adopt into parent line* (the parent's write rule, confirmed first), *Delete scenario*
  (confirmed first). A 403 from the server is still handled and says the role does not allow it.
- **Start changed.** A Scenario whose starting state changed shows a warning with *I have checked it* (acknowledge).
- **Structure canvas guidance** lives in `ui-foundation.md` ("Full-width canvas pages": layout, drawing, keyboard map, accessibility, contrast, reduced motion, phones); this file covers the model page around it (line bar, change list, change editor).
- **Change list** (Structure tab). A column beside the canvas, oldest first, opened with the *Changes (n)* button in the line bar (open by itself only on screens at least 1600 px wide, so it never squeezes the drawing). Each change shows date, title, number of
  edits and, for a Scenario that starts from it, a small badge that opens the Scenario. A **planned** change (dated after
  today) has the word *Planned*, a dashed amber frame and an amber fill: never colour alone. A *Now* divider sits between the
  last change that has happened and the first planned one (at the end when nothing is planned). Choosing a change shows the
  state after it on the canvas (`useGraphState` with that change id); the chosen change is `aria-current`.
- **Past changes are read-only.** While a change other than the line's last is shown the canvas is read-only and says so,
  with *Show the latest change*. A planned change shows a notice that it is not part of the present state.
- **Start row.** A Scenario's change list begins with a fixed row **Start** (Finnish *Lähtötilanne*) before the first Change: it names the parent line and the Change the Scenario starts after (with its date) and links to both. It is a button that is `aria-current` when chosen; the canvas then shows the parent's state after that Change read-only with the caption "Start state, not editable. Change it in the parent line.", and drawing, undo, delete and the Change editor are unavailable. It is not a Change: no date edit, no delete, not counted in *Changes (n)*, and no marks. The Base line has no Start row.
- **Change editor** (dialog, labelled): title, date, note, and for an existing change the ordered edits in words with element
  names resolved (read-only here; edits are drawn on the canvas), *Delete change* (confirmed), and for a new change a date
  that suggests today; a later date makes it planned and the dialog says so. The form keeps what was typed when a write
  is refused.
- **Refusals** are built from the structured answer, never the server's text, in Finnish and English (`chainBrokenMessage`):
  where it breaks (change, date, Scenario when it is in another line), which element, type or ends, why, and what to do
  first, for each of the nine causes; a delete of a branch point names the Scenario; adopt says why (`parent_moved_on`,
  `dates_precede`, `nothing_to_adopt`) and suggests recreating the differences in a new Scenario from the parent's latest state;
  delete of a line with Scenarios says to delete them first.
- The **Types** tab says the types are shared by every line. Metrics, Simulations and Analysis follow the selected line.
