# User guide

This guide is for Organization Users who plan, view, or maintain a Yearclock.
Terms follow [`CONTEXT.md`](../../CONTEXT.md). Features marked *not yet
available* are specified for V1 but not implemented; see
[`.scratch/_PORTFOLIO.md`](../../.scratch/_PORTFOLIO.md).

A step-by-step acceptance walkthrough is in
[`docs/end-user-tutorial/yearclock-v1-testing.md`](../end-user-tutorial/yearclock-v1-testing.md).

## Terms and privacy

The footer of the sign-in page and the bottom of the sidebar link to **Terms and privacy**, where the terms,
privacy notice, sub-processors, and the other documents are published in English and Finnish. You can read them
without signing in. Invitation and notification emails link to the privacy notice.

## Using an AI agent

If an Owner or Admin has given you the connection details, you can connect an AI agent (for
example Claude, with a custom connector) to read and change your Yearclocks. Sign in to Yearclock at
least once first. The agent sees and changes only what you could yourself; every change it makes is
saved at once and shows in the Event history as made by an agent through MCP. Yearclock asks nothing
extra, so use your agent's own confirmation settings, especially for deleting. Stored text such as
Event descriptions is passed to the agent as data. If an Owner or Admin turns agent access off,
your agent stops working for that Organization.

## Billing notices

If the workspace says the Organization is read-only, you can still view every
Yearclock, but changes are blocked until an Owner resolves billing.

## Signing in

- Every Yearclock view requires sign-in. Select **Continue with Authentik**.
- Use a passkey when you can. A password sign-in always requires a second
  factor (TOTP or a security key).
- Account registration, email verification, and recovery happen in Authentik,
  not in Yearclock.
- Open the account menu (your initials, top right) to see who is signed in,
  choose **English** or **Suomi**, or **Sign out**. Your language choice is
  remembered. Content that people in your Organization enter is never
  translated.

## Choosing an Organization

- If you belong to one Organization, Yearclock opens it directly.
- If you belong to several, choose one under **Choose an organization**.
- The Organization is part of the address (`/organizations/{id}`), so separate
  browser tabs can show different Organizations safely.
- The Organization page lists the Yearclocks you can open. Type in **Find a
  Yearclock** to narrow the list by name (capital letters and accents do not
  matter). **Recently opened** shows your five latest Yearclocks, on every
  device; only you see this list.
- Each Yearclock opens on its own page (`/organizations/{id}/yearclocks/{id}`).
  You can share the link, but it works only for people who have access to that
  Yearclock. **Back to …** returns to the Organization page.
- The sidebar is on every page: the Organization switcher (with **All
  organizations** and **Create another organization**), **Overview**, your
  Yearclocks with the recently opened ones first (and a search when there are
  many), and, for Owners and Administrators, **Administration**. Owners also
  see **Billing and seats** and **Organization settings**. The current page is
  highlighted.
- Every page has its own address, so browser Back and Forward work and a link
  opens the same page. On a small screen, open the sidebar with the menu
  button at top left. **Skip to content** is the first stop for keyboard users.

## What you can do

Your permissions come from your role:

| Role | You can |
| --- | --- |
| Yearclock Viewer | Read the Yearclocks you have been granted. |
| Yearclock Editor | Also change Lanes, Categories, and Events in those Yearclocks. |
| Organization Admin | Manage every Yearclock and the Organization's people. |
| Organization Owner | Everything an Admin can, plus billing, seats, ownership, and deletion. |

An Organization User without a Yearclock grant sees no Yearclock content. Ask
an Owner or Admin for access.

## Yearclocks, Lanes, and Categories

- A **Yearclock** is one continuous timeline shown as a circle of 12 months.
- **Lanes** are its concentric rings, for example a process or a team. Every
  Event belongs to one Lane. Editors add, rename, reorder, and delete Lanes
  under **Yearclock settings**. A Lane that still has Events, including
  recently deleted ones, can be deleted only after you move its Events to
  another Lane; the last Lane cannot be deleted.
- **Copy from another Yearclock** copies a Lane from any Yearclock you can
  open, including the current one, with or without its Events and recurring
  Series. The copy keeps the Lane's tint and height and each Event's
  Category, Labels, description, and link. A Yearclock's own Categories are
  matched by name, and missing ones are created. The copy is independent:
  later changes to the original do not reach it. If the copy would exceed a
  limit, nothing is copied.
- **Link from another Yearclock** adds a Linked Lane. It shows a Lane of
  another Yearclock here, live and read only, named "<Lane> (from
  <Yearclock>)". You change its Events in their own Yearclock (**Open in …**
  in the details). A Linked Lane never gives anyone access: people who may
  not open the source Yearclock see "Lane not available" in its place. You
  can give a Linked Lane its own tint and height, move it, or remove it. A
  Yearclock made only of Linked Lanes works as an overview of several
  Yearclocks.
  Filters list the source Yearclocks' Categories under "Categories from
  <Yearclock>", and search also finds the Linked Lanes' Events you may see.
- **Categories** are optional named colors that classify Events across Lanes.
  Editors create, rename, recolor, reorder, and delete them. Deleting a
  Category asks for confirmation and leaves its Events uncategorized.

## Reading the circle

- Time runs clockwise from 12 o'clock through exactly 12 months. Each Lane is
  a ring; the first Lane is the outermost ring.
- A dot is a single-day Event, an arc is a date range, and a diamond or dashed
  arc is a changed recurring Occurrence. Colours come from Categories, which
  are also named under **Filters** and in the list.
- When today is inside the window, a red line marks it and the elapsed part of
  the window is shaded.
- **Events in this window** lists the same Events in the same order. Select an
  Event on the circle or in the list to see its details.
- Point at an Event, or move to it with Tab, to preview its title, date, and
  Lane in the middle of the circle without opening it.
- **Filters** narrows a busy Yearclock. Tick Lanes, Categories (including **No
  Category**), or Labels to show only those Events. Ticks in one group add
  Events (this Lane *or* that Lane); ticks in different groups narrow them
  (this Lane *and* this Label). The number after each choice tells how many
  Events in the window it would show. While a filter is on, the page says how
  many Events are hidden; **Show all** clears every filter.
- Filters affect only your own view. They are remembered for each Yearclock in
  this browser and never change what others see.
- **Search this Yearclock** finds Events in every year, not only the window
  shown. Type at least two characters; capital letters and accents do not
  matter (`kasittely` finds *käsittely*). It looks in titles, descriptions,
  Category names, and Label names. Choose a result to move the Planning Window
  there and open the Event. Recurring Events are found up to about a year
  ahead, as far as their occurrences exist.

## Displays

- **Display** in the toolbar chooses how the Planning Window is drawn. The
  choice is yours, remembered for each Yearclock in this browser, and never
  changes what others see. **Circle** is the default.
- **List** shows the window's Events as a table with Date, Title, Lane,
  Category, and Labels. Choose a column title to sort by it and again to
  reverse it. A dense recurring Series is one row with its number of
  occurrences; open it to see them. Choose a title to see the Event's
  **Details**.
- Editors can press **Select Events** above the table and tick rows to change
  many Events at once, with the same rules and confirmations as in the
  circle.
- On a phone, each row is a card, and **Sort by** replaces the column titles.
- **Timeline** draws each Lane as a row over the window, with the Lane
  names fixed at the left. A single-day Event is a marker and a range a bar,
  both in the Category's colour; a dense weekly Series is a row of small dots
  with one title. A line shows today, the top shows months (with the year when
  the window crosses a year end), and 1- and 3-month windows add week numbers
  (1 month also days). Choose a marker or bar to see its **Details**. Editors
  can choose an empty day on a Lane to start a new Event there, or use **New
  Event**; Events cannot be dragged. A wide window scrolls sideways inside the
  timeline. Linked Lanes are read only. Use Tab to move through the Events
  Lane by Lane.
- **Agenda** shows the circle with the window's Events listed below it day by
  day, grouped by month, each day with its weekday name. Choosing a row
  selects the Event on the circle and opens its **Details**; choosing an
  Event on the circle marks its row. Set the length to 1 month for a
  single-month agenda.
- Every display shows the same Events under the same Filters and keeps the
  Event you selected when you switch.

## Exporting Events to a spreadsheet

- **Export → Export to Excel…** or **Export to CSV…** opens a dialog. Choose
  **The current window** (your Filters are applied) or **The whole Yearclock**,
  and the file format, then **Export**.
- The file has one row for each Event and each occurrence of a recurring Series,
  with the columns Title, Starts, Ends, Start time, End time, Lane, Category, Labels, Location,
  Description, Links (one `Title | address` per line), Series, and Source (the
  Yearclock a Linked Lane comes from). Dates are
  written as `2026-03-10`, and the column titles follow your language. Skipped
  and deleted Events are left out. The file contains only what you may see.
- **Export → Export to calendar (.ics)…** saves the same Events as a calendar
  file that Outlook, Google Calendar, and Apple Calendar can open. Each Event
  and each occurrence is its own entry (all-day, or at its start and end time
  when it has them) with its title, description,
  location, links (the first as the entry's address, the rest in its
  description), Category, and Labels; recurring Series are written out as separate
  entries without a repeat rule. Each entry keeps the same identifier, so
  opening a newer file usually updates the entries you already added. Yearclock
  does not keep your calendar in sync: download the file again after changes.
- CSV files use a semicolon in Finnish and a comma in English, so they open
  correctly in a spreadsheet of that language.
- Text that begins with `=`, `+`, `-`, or `@` is saved with a leading `'`, so
  opening the file never runs it as a formula.
- Each export is recorded in the Activity log (without its content), and a
  person can make 20 exports and imports an hour (a preview counts); after that
  the dialog says how long to wait.

## Importing Events from a spreadsheet

- Editors choose **Export → Import from Excel or CSV…**. Press **Download
  template** for an Excel file with the column titles (in your language) and a
  second sheet that lists the Lanes, Categories, and Labels that exist. Fill in
  one Event per row: **Title**, **Starts**, and **Lane** are required; **Ends**,
  **Start time** and **End time** (`14:00` or `14.00`),
  **Category**, **Labels** (separated by commas), **Location**, **Description**,
  and **Links** (one `Title | address` per line; a bare address gets its host
  name as the title, and an older file's single **Link** column still works)
  are optional. Dates are written `2026-03-10` (or `10.3.2026`).
- Choose the file (`.xlsx` or `.csv`, up to 2 MB and 1000 rows). The dialog
  shows a preview: how many Events will be created, which rows are skipped, and
  every problem with its row and column. Nothing is saved yet.
- Lanes, Categories, and Labels must already exist and are matched by name,
  ignoring capital letters and accents; the import never creates them. Rows
  that match an existing Event (same Lane, title, and dates) are skipped, and
  rows of a recurring Series, or of a Linked Lane, are skipped as well, so an
  exported file can be imported again without duplicates.
- If the preview shows any problem, fix the file and choose it again: **Import**
  saves only a file without problems, and then saves all of it. Imported Events
  appear in each Event's history as "Imported".
- Files with macros, over the limits, or that are not Excel or CSV files are
  refused with a reason. Imports count toward the 20 exports and imports an
  hour.

## Exporting and importing all your data (Owners and Admins)

- Open the account menu (your name, top right) and choose **Export and import
  data**. The page lists the Organizations where you are Owner or Admin; the
  menu entry is missing if there are none.
- **Download CSV** saves one file with all of them: Yearclocks (also archived
  ones), Lanes, Categories, Labels, Events, and recurring Series with changed
  or skipped occurrences. People, Groups, access rights, deleted Events,
  Event history, and billing data are not in it.
- To import, choose a file made by the export. You first see, per
  Organization, how many rows are new, changed, or the same, and any problems
  with their row numbers. Nothing is saved until you press **Save import**,
  and if any row has a problem nothing is saved at all.
- A row whose id already exists is updated from the file; a row whose id does
  not exist is created. Nothing is ever deleted, an import never creates an
  Organization or changes its settings, and the repeat rule of an existing
  Series cannot be changed. If someone changed an Event after the file was
  made, the preview says so; saving overwrites that change, and the old
  values stay in the Event's history.
- Edit the file in a spreadsheet only if you keep the first row (the column
  names) and the second row (the format marker), and save it as CSV (UTF-8).
- A person can make 3 such exports, previews, and saves an hour.

## Printing and saving an image

- **Export** in the planner toolbar has **Print** and, on the circle,
  **Download image (PNG)**. Neither sends anything to the server.
- **Print** opens your browser's print dialog; choose "Save as PDF" there for a
  PDF. The printout shows the current display on an A4 landscape page without
  the sidebar, toolbar, or panels. It starts with the Yearclock's name, the
  Planning Window, and the print time, and continues with a legend (Lanes and
  Category colours) and, for the circle and the timeline, a list of the Events.
  The list display and the agenda print themselves.
- **Download image** saves the circle as a PNG at twice the screen size on a
  white background, with a title and the legend. The file is named after the
  Yearclock and the window start.

## Planning Window

- By default you see the current planning year in your Organization's time
  zone: January to December, or from the month the Yearclock's year starts
  in. Editors set that month under **Yearclock settings** →
  **Year starts in**, for example August for a school year; it applies to
  everyone and never moves Events.
- The toolbar above the circle holds the Planning Window controls, the
  search, and **New Event**. Beside the circle (below it on a phone) the panel
  has three tabs: **Events** lists what the window shows, **Details** opens
  when you choose an Event, and **Filters** narrows the view.
- **Length** shows 1, 3, 6, 12, 18, or 24 months at a time (12 by default).
  Changing it keeps the first month. Your choice is remembered for each
  Yearclock in this browser; it never changes what others see.
- **Previous period** and **Next period** (the double arrows) move by the
  chosen length; **Previous month** and **Next month** (the single arrows)
  move by one month, and **Start month** jumps to
  any month. **Current period** returns to the window that contains today.
  Events outside the window are kept and reappear when their dates are
  visible.
- With a length of 1 month, the circle shows day marks with a number on every
  fifth day.
- Editors can turn on **Show week numbers** (ISO weeks, starting on Monday)
  and **Show quarters** under **Yearclock settings**. The rings sit
  just inside the month names for everyone. Quarters follow the Yearclock's
  start month: if the year starts in August, Q1 is August–October. In long
  windows only every second or fourth week is numbered so the numbers stay
  readable.
- Each Lane can have a light **Tint** and a **Tall** height (Editors, under
  **Yearclock settings** → Lanes). A tall Lane takes twice the space
  of a normal one, which helps an important process stand out; Event colours
  still come from Categories.

## Events

- An Event has a title (up to 200 characters), a Lane, and an all-day start
  date. It can also have an inclusive end date, a plain-text description, one
  Category, an optional **start time** and **end time** (24-hour, in the
  Organization's time zone; an end time needs a start time, and on a one-day
  Event it must be after it), a **Location** (free text, up to 200 characters), and up to ten
  **Links**, each with a text (up to 100 characters) and an `http` or `https`
  address. The location shows in the panel, the list, the agenda, and the print
  list, and search finds it and the link texts. The description can be
  formatted: with **Use text formatting** on (the default for new Events) the
  toolbar adds **bold**, *italic*, a bulleted list, and a link, and **Preview**
  shows the result; a description written before this stays plain text until you
  switch the option on. Exports, search, the calendar file, and print use the
  text without the markers, with links written as "text (address)". In the editor, **Add link**
  adds a row, and the arrow buttons reorder them.
- Events are planning entries. They have no assignee, due date, or completion
  state.
- Editors create an Event with **New Event**, or by selecting an empty point
  on a Lane ring, which fills in the Lane and date. Select an Event to
  **Edit** or **Delete** it. The form opens in a panel from the right with the
  circle still in view (on a phone it covers the screen); **Cancel** or Escape
  closes it without saving.
- Editors open **Yearclock settings** from the toolbar for the Layout, Lanes
  (including copied and linked ones), Categories, and **Plan a season
  again**. Viewers do not see it.
- **Duplicate** opens a new Event form filled with the Event's title, dates,
  Lane, Category, Labels, description, and link. **Plan again next year**
  does the same with the dates moved one year ahead (29 February becomes
  28 February). Nothing is saved until you press **Save**. Duplicating a
  recurring occurrence creates a single Event.
- To change many Events at once, press **Select Events** and tick Events in
  **Events in this window**, or use **Select all shown** to take every Event
  the Filters show. You can then move them to another Lane, set or clear
  their Category, add or remove a Label, or delete them. You confirm each
  change, and it applies to all selected Events or to none: if someone else
  changed one of them in the meantime, nothing is saved and the latest
  versions are shown. Up to 200 Events can be changed at once. Recurring
  occurrences cannot be selected; change them through their Series.
- To plan a whole season for the next year, open **Layout, Lanes and
  Categories** and use **Plan a season again**:
  1. Choose the season to copy (12 months from the Yearclock's start month),
     and the Lanes and Categories to include.
  2. Choose **Same date** or **Same weekday**. Same weekday moves an Event by
     at most three days so that it keeps its weekday and its length.
  3. **Preview** says how many Events will be created and how many already
     exist and will be skipped. Nothing is created until you press
     **Create**.

  Recurring Series are not copied, because they continue on their own.
- Deleting an Event is recoverable for 30 days from **Deleted Events**; after
  that it is removed permanently. Recurring occurrences are not deleted: skip
  them or end their Series instead.
- If someone else changed the Event after you opened it, your save is rejected
  and the latest version is shown so you can review and retry.
- **History** at the end of an Event's details shows every change, newest
  first: when and by whom, why (for example "Changed with Bulk Edit" or
  "Label Draft merged into Final"), and the old and new values. Everyone who
  can open the Yearclock sees it. People who have left the Organization
  appear as "Former member". For a recurring occurrence, the history shows
  its own changes and each change to its Series.
- Editors can press **Restore this version** on an earlier entry. A preview
  shows what will change, and says if a Category or Label from then no longer
  exists and will be left out. If the Lane is gone, you choose another one.
  Restoring adds a new version; nothing in the history is lost. Recurring
  occurrences use **Restore Series values** instead, and Events of Linked
  Lanes are restored in their own Yearclock.

## My groups

- If an Owner or Administrator has put you in Groups, **My groups** on the
  Organization page lists them, with the Yearclocks each Group lets you open
  and your role there. You see only your own Groups.

## Notifications

- The bell in the top bar of an Organization shows how many notifications you
  have not read. It opens **Notifications**, newest first, with **Mark as
  read**, **Mark all as read**, and **Unread only**.
- You are told when your access to a Yearclock changes (you can now view or
  edit it, your access became view only, or you lost it), when your role in
  the Organization changes, when someone accepts your invitation, and when
  ownership changes hands. You are never told about your own actions, and a
  change that ends where it began before you read it disappears.
- **Settings** (on the Notifications page) chooses, for each kind of change,
  whether you hear about it in the app and by email. By default you get
  everything in the app, and email only when you lose access to a Yearclock.
  Notification email arrives at once, at most 10 a day, in your language, and
  has no tracking.
- Notifications say what changed for you and never include what is in an
  Event. They are deleted after 90 days.

## Summary of upcoming Events

- In **Notification settings**, **Summary of upcoming Events** is off until you
  choose **Weekly, on Mondays** (the next 14 days) or **Every day** (the next 7
  days). The email arrives at about 8:00 in the Organization's time zone, in
  your language.
- It lists Events (title, date, Lane, and Yearclock, with a link) from all the
  Yearclocks you can read, or only the ones you pick. Archived Yearclocks, skipped
  recurring occurrences, and deleted Events are left out, and nothing is sent when
  there is nothing to list.
- It stops when you are removed from the Organization or lose access, and while
  the Organization is read-only or waiting to be deleted. This is the only message
  that includes Event titles, which is why you have to turn it on.

## Changes since your last visit

- When you open a Yearclock, Events that others created or changed since
  your previous visit are marked **New** or **Changed**, in the Event list
  and in what a screen reader announces for the circle.
- **Changes since your last visit** (the "N changes" badge in the toolbar
  shows or hides it) lists those changes, including deleted
  Events (Editors can restore them there) and Series changes. **Mark as
  seen** clears the marks.
- Your own changes are never marked, your first visit shows nothing, and
  changes in Linked Lanes count when you may open their source Yearclock.
- While you have a Yearclock open, the page checks about once a minute
  whether others have changed it. If they have, a notice offers **Refresh**.
  Nothing changes on your screen until you press it, and your own unsaved
  form stays as it is.

## Labels

- An Event can carry up to ten Labels, such as a status, type, or owner, in
  addition to its one Category. Labels are shared by every Yearclock of the
  Organization.
- In the Event form, tick Labels under **Labels**, or type in **Find or create
  a Label** to narrow the list. If no Label has that name, Editors can create
  it with **Create Label** (or by pressing Enter). Label names are visible to
  everyone in the Organization, so do not put confidential information in
  them.
- Labels appear in the Event details, in **Events in this window**, and in
  what screen readers announce for each Event. They are not drawn on the
  circle, which keeps the Category colours readable.
- Owners and Administrators rename, merge, and delete Labels under
  **Administration → Classification**.
- The **Category** list in the Event form has two groups when your
  Organization has shared Categories: **Organization Categories**, which are
  the same in every Yearclock and changed only by Owners and Administrators,
  and the Yearclock's own Categories.

## Recurring Events

- Choose **Weekly**, **Monthly**, or **Yearly** and an interval, then
  **Add recurring Event**.
- A monthly Event anchored to the 29th–31st falls on the last day of shorter
  months and returns to its day later. A yearly Event on 29 February occurs only
  in leap years.
- Select an occurrence to see its Series date. **Edit this occurrence**
  changes only that one; only the fields you change stop following the
  Series, and it is drawn as a diamond or dashed arc. **Restore Series values**
  undoes all changes.
- **Edit this and future occurrences** changes the Series from that date on.
  Earlier occurrences keep their values, and occurrences you changed
  individually keep those changes.
- Labels work the same way: Labels chosen when creating a recurring Event
  apply to every occurrence. **Edit this occurrence** can give one occurrence
  different Labels (or none), and **Edit this and future occurrences** changes
  them from that date on.
- **Skip occurrence** hides one occurrence; restore it under **Skipped
  occurrences**. **End Series from here** removes that and later occurrences
  and keeps the earlier ones.
