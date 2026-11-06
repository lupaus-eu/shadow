# Yearclock V2 testing tutorial

Hands-on checks for the Yearclock V2 features, in the order they were
delivered. V1 is covered in `yearclock-v1-testing.md`. Run the local stack with
`make up` and open <http://localhost:8173>.

## P2 — Classification and findability

**Status: Available**

1. **Yearclock pages.** Open the Organization. The page lists your Yearclocks
   under **Open a Yearclock**; type part of a name (accents do not matter) in
   **Find a Yearclock**. Open one: it has its own address and a **Back to …**
   link. Return to the Organization page and check that it appears under
   **Recently opened**.
2. **Shared vocabulary (Owner or Administrator).** Open **Classification**.
   Add an Organization Category (for example *Board*) and two Labels (*Decision
   needed*, *Finance*). Note the reminder that Label names are visible to the
   whole Organization.
3. **Labelling.** On a Yearclock, create an Event. Choose *Board* from the
   **Organization Categories** group, tick *Decision needed*, type *Budget* in
   **Find or create a Label**, and press Enter to create and select it. Save.
   The Event's details and the list show the Labels; a screen reader announces
   them with the Event.
4. **Recurring Events.** Create a weekly Event with a Label. Edit one
   occurrence and give it another Label, then use **Edit this and future
   occurrences** to change the Labels from a later date. Earlier occurrences
   keep theirs.
5. **Filters.** Under **Filters**, tick a Label: only matching Events stay, the
   count after each choice updates, and the page says how many Events are
   hidden. Reload the page: the filter is remembered. **Show all** clears it.
6. **Search.** Search for a word from a title or description in another year.
   Choose the result: the Planning Window moves there and the Event opens.
7. **Housekeeping.** Back in **Classification**, merge *Budget* into
   *Finance* and delete an unused Label; each asks for confirmation with the
   number of affected Events, and **Activity** lists the change under
   *Labels*.
8. **Roles.** As a Viewer, confirm that Labels are visible but cannot be
   changed. As a Member without access to a Yearclock, confirm that its link
   shows the not-found message.

## P1 — Wheel display and layout

**Status: Available**

1. **Length.** On a Yearclock page, choose 3 months under **Length**. The
   circle shows three months from the same start month. **Next period** moves
   three months; the month buttons still move one. Reload the page: the
   length is remembered on this browser only.
2. **One month.** Choose 1 month and press **Current period**. The month ring
   shows a mark for every day and a number on every fifth day.
3. **Start month (Editor).** Open **Yearclock settings**, set
   **Year starts in** to August, and press **Save layout**. With the 12-month
   length, **Current period** now shows August–July. Events stay on their
   dates.
4. **Rings.** Tick **Show week numbers** and **Show quarters** and save. Q1
   begins in August. Try 24 months: week numbers thin out but stay legible.
5. **Lanes.** Give a Lane a tint and make it tall, then press **Save**. The
   Lane gets a light background band and more room; Event colours do not
   change.
6. **Preview.** Point at an Event or reach it with Tab. Its title, date, and
   Lane appear in the middle of the circle.
7. **Roles.** As a Viewer, confirm that the length and preview work but the
   layout controls are not offered. Open the same Yearclock in two tabs,
   change the layout in one, and save a different change in the other: it is
   refused with a message and the latest layout is shown.

## P3 — Planning productivity

**Status: Available**

1. **Duplicate.** Open an Event and press **Duplicate**. The form is filled
   in; change the date and save. **Plan again next year** does the same one
   year ahead.
2. **Bulk edit (Editor).** Press **Select Events**, tick a few Events or
   filter by a Label and press **Select all shown**, then move them to
   another Lane. Recurring occurrences cannot be ticked. Open the same
   Yearclock in a second tab, change one of the selected Events there, and
   try again in the first tab: nothing is saved and an alert explains why.
3. **Plan a season again.** In **Yearclock settings**, choose the
   current season, keep all Lanes, choose **Same weekday**, and press
   **Preview**. Create the Events, then preview again: everything is reported
   as already existing.
4. **Copy a Lane.** Under **Copy from another Yearclock**, copy a Lane with
   its Events from a second Yearclock. Change an Event in the original: the
   copy does not change.
5. **Roll-up Yearclock (Owner or Administrator).** Create a Yearclock
   "Company overview", link a Lane from each of two team Yearclocks under
   **Link from another Yearclock**, and delete its own default Lane. The
   circle shows both Lanes as "<Lane> (from <Yearclock>)"; opening an Event
   offers **Open in <Yearclock>** and no editing.
6. **Access.** Give a Member Viewer access to the overview and to only one of
   the team Yearclocks. Signed in as that Member, the other Linked Lane says
   "Lane not available", and search finds only the readable team's Events.
7. **Lifecycle.** Delete one team Yearclock: its Linked Lane says "Lane no
   longer available". Recover it from **Deleted Yearclocks**: the Lane
   returns.

## P4 — History and awareness

**Status: Available**

1. **History.** Open an Event and expand **History**. Change its date and
   Category, then look again: the newest entry shows who changed what, with
   old and new values. Older Events start with "State when history began".
2. **Restore (Editor).** Press **Restore this version** on an older entry,
   check the preview, and restore. The Event returns to that state, and the
   history gains a new "Earlier version restored" entry.
3. **Indirect changes.** As an Owner, merge a Label that the Event carries.
   Its history shows "Label … merged into …".
4. **Changes since your last visit.** Sign in as a second user, change an
   Event, add one, and delete one. Back as the first user, open the
   Yearclock: the Events are marked **New** or **Changed**, and **Changes
   since your last visit** lists all three. Restore the deleted one, then
   press **Mark as seen**.
5. **Change notice.** Keep the Yearclock open in one browser and change an
   Event in another as a different user. Within about a minute the first
   browser says the Yearclock has changed. **Refresh** shows the change.
6. **Access.** As a Viewer, check that History is visible but restore is
   not. As a Member without access, the Event's history is not reachable.

## P10a — Organization administration

**Status: Available**

1. **Groups (Owner or Administrator).** Open **Administration → Groups**, add "Finance", and add two members. Try adding "finance" again: the
   duplicate name is refused.
2. **Group access.** In **Administration → Yearclocks and access**, give a Yearclock's **Access** "Finance" Editor under
   **Groups**. Sign in as one of its members: the Yearclock opens with edit
   access, and **My groups** lists it. Remove the member from the Group, and
   the access is gone.
3. **Everyone in the Organization.** Set a Yearclock to Viewer for everyone,
   then to Editor. The confirmation says how many members gain edit access.
   Invite a new person: after accepting, they see it too.
4. **Bulk invitations.** On **Administration → People**, under **Invite people → Invite several people**,
   paste five addresses, including an existing member and a repeated one,
   choose **Groups to join**, and press **Preview**. The skipped addresses
   have reasons. If seats are short, the preview says how many are needed and
   sends nothing. Send once seats suffice, and after acceptance the people are
   in the Group.
5. **Access overview.** In **Administration → People**, press **Access** for a member: every
   Yearclock is listed with its sources, such as Group, Direct, or Everyone.
   In a Yearclock's **Access**, press **Who has access**. Remove a member: the
   confirmation names what they lose.
6. **Read-only.** While the Organization is read-only, Groups, sharing, and
   invitations cannot be changed, but access keeps working.

## P5 — Additional displays

**Status: Available**

1. **Choose a display.** In the planner toolbar, **Display** offers Circle,
   Timeline, List, and Agenda. Pick **List**, reload the page: it is still
   List. Open another Yearclock: it shows the Circle.
2. **List.** Sort by **Title**, then **Lane**, then **Date**; the arrow shows
   the order and a second press reverses it. Open the "Weekly" row to see its
   occurrences. Choose a title: **Details** opens. As an Editor, press
   **Select Events**, tick three rows, and move them to another Lane; the
   confirmation says how many Events change. Occurrences cannot be ticked.
3. **Agenda.** Set the length to 1 month and open **Agenda**: the circle is
   above a list grouped by day with weekday names. Choose a row, then an Event
   on the circle: each marks the other. Switch to Finnish and check the
   weekday and month names.
4. **Timeline.** Each Lane is a row; single-day Events are dots with titles,
   ranges are bars, a weekly Series is a row of small dots. Switch the length
   to 3 months (week numbers) and 1 month (days). With 24 months the timeline
   scrolls sideways on its own, and the Lane names stay put. Choose an empty day on a Lane as an Editor:
   the Event form opens with that Lane and date. As a Viewer nothing happens.
   Linked Lanes are read only.
5. **The same Events everywhere.** Apply a Filter, then switch between all
   four displays: the same Events show in each, and the Event you selected
   stays selected.
6. **Keyboard and phone.** Tab through the timeline: Lane by Lane, in date
   order within a Lane; Enter selects. On a phone, the list is cards and the
   timeline scrolls inside its box.
7. **Needs a human.** Review the Finnish texts of the display names and column
   headings, and read the timeline and list with a screen reader.

## P7 — Print, export, and import

**Status: Available**

1. **Print and image.** Open a Yearclock and choose **Export → Print**. The
   print preview shows the name, window, and print time, the circle, a legend,
   and an Event list on a second page; the sidebar and toolbar are gone. Save it
   as PDF. Then choose **Download image (PNG)**: the picture has a title and a
   legend on white.
2. **Export to a spreadsheet.** Turn on a Filter, choose **Export → Export to
   Excel…**, keep "The current window", and open the file: only the filtered
   Events are there, with Title, Starts, Ends, Lane, Category, Labels,
   Description, Link, Series, and Source. Export to CSV in Finnish and open it
   in a Finnish spreadsheet: the columns split correctly. Give an Event the
   title `=1+1` first: the file shows it as text, not as a result.
3. **Import.** As an Editor choose **Export → Import from Excel or CSV…** and
   **Download template**. Fill in three rows, one with a Lane that does not
   exist. Choose the file: the preview lists the problem with its row, and
   **Import** is disabled. Fix the Lane, choose the file again, and press
   **Import**: the Events appear, and each Event's history says "Imported".
   Choose the same file again: its rows are skipped as already existing.
4. **Round trip.** Export a Yearclock, create a second one, and import the file
   into it: single Events arrive, and rows of a recurring Series are skipped.
5. **Refusals.** Try a `.xlsm` file, a file over 2 MB, and a file with more than
   1000 rows: each is refused with a reason and nothing is created. As a Viewer
   the Import entry is missing.
6. **Limits.** Make more than 20 exports or previews in an hour (or set
   `LIMIT_EXPORTS_PER_HOUR=2`): the dialog says how many minutes to wait.
7. **Organization Export.** As an Owner open **Organization settings** and
   **Download Organization Export**. The JSON file holds members, Groups,
   Yearclocks, and Events, but no history or billing data. An Administrator has
   no such page. **Activity** lists each export without content.
8. **Needs a human.** Check the Finnish texts, open the files in your
   spreadsheet programs, and review the print preview in each browser.

## P8 — Notifications and calendar export

**Status: Available**

1. **Calendar file.** Open a Yearclock with a recurring Series, choose
   **Export → Export to calendar (.ics)…**, keep "The current window", and open
   the file in Outlook, Apple Calendar, or Google Calendar: every Event and
   occurrence is an all-day entry with its link and description, and a range
   ends on its last day. Export again after changing a title and import the
   file again: most calendars update the entries instead of duplicating them.
2. **Access notifications.** As an Admin, give a Member Viewer access to a
   Yearclock. The Member's top bar shows a bell with 1 unread; **Notifications**
   says "You can now view …" with an **Open** link. Make them an Editor before
   they read it: still one notification, now "You can now edit …". Give and
   remove the access before they read it: the notification disappears.
3. **Groups and Organization-wide Access.** Give a Group of three people
   access, one of whom is already an Editor through another route: only the
   other two are told. Share the Yearclock with the whole Organization: every
   Member is told, Owners and Admins are not.
4. **Role and invitation notices.** Change a Member's role to Admin (they are
   told), accept an invitation (the inviter is told), and give someone
   ownership (the other Owners are told). Nobody is told of their own action.
5. **Email and settings.** Open **Notifications → Settings**. By default you get
   everything in the app and email only when you lose access to a Yearclock.
   Turn on **By email** for "Access to a Yearclock changed" and give yourself
   access in a second account: an email arrives at once in that person's language,
   with a link to the inbox and one to the settings and no tracking. (Ask before
   sending real email; the local stack sends through Scaleway.) More than 10 in
   24 hours stay in the app only.
6. **Owner and Admin notices.** Let a Support Agent request Support Access,
   let a grant expire, simulate a failed renewal payment, and request Organization
   deletion: Owners and Admins are told in the app and by email; Members are not.
7. **Summary.** In the settings choose **Weekly, on Mondays** (or **Every day**)
   and pick one Yearclock. With Events in the next days the email arrives after 8:00
   Organization time (within the worker's scheduling interval); change the choice
   and it does not repeat the same day. Archive the Yearclock: nothing is sent.
8. **Retention.** Notifications older than 90 days disappear after the daily
   cleanup job (`NOTIFICATION_RETENTION_DAYS`).
9. **Needs a human.** Open the `.ics` file in each calendar, check the email
   rendering in real mail clients, check the Finnish wording, and have the
   data protection owner review the Summary as a purpose of processing.

## P11 — Richer Event content

**Status: Available**

1. **Location and links.** Edit an Event: add a **Location** and three **Links**
   (a text and an address each), reorder them with the arrow buttons, and save.
   The panel shows the location and the links (they open in a new tab). The list,
   the agenda, and the print list show the location; search finds the location
   and a link text. An Event that had a single link before the upgrade shows it as
   a link titled with the website's name.
2. **Formatted description.** On a new Event leave **Use text formatting** on, select
   a word and press **Bold**, add a list with **Bulleted list**, add a link with
   **Link**, and open **Preview**. After saving, the panel shows the formatting.
   Open an older Event: its description is plain text and **Use text formatting**
   is off until you switch it on. Type `<b>x</b>` in a formatted description: it
   shows as text.
3. **Times.** Give an Event a start time and an end time. They show with the date
   (`10 Mar 2026, 14:00–16:00`), and on the same day the all-day Events come first.
   An end time before the start is refused on a one-day Event and allowed on a
   longer one. Make a weekly Series with a time, then change one Occurrence's time.
4. **Exports.** Export to Excel and CSV: the new columns **Start time**, **End
   time**, **Location**, and **Links** are there, and the description has no
   formatting marks. Import the file into another Yearclock: everything arrives,
   and an older file with one **Link** column still imports. Download the calendar
   file and open it: timed Events appear at the right time in your own time zone
   (also across the daylight-saving change), and untimed ones stay all-day.
5. **History.** Change the location, a link, the formatting, and a time: each shows
   in the Event's history and can be restored.
6. **Needs a human.** Open the calendar file in each calendar in two time zones,
   check the editor with a screen reader in Finnish and English, review the
   Finnish texts, and open the spreadsheets in each spreadsheet program.

## P14 — Subscription and ownership management

**Status: Available**

1. **Cancel and undo.** As an Owner open **Billing and seats** and choose
   **Cancel subscription**. The dialog states the end date, that the
   Organization is read-only afterwards with its content kept, and offers a
   reason. Confirm: the card says the subscription ends on that date, and the
   other Owners and Administrators are notified (also by email). Choose
   **Undo cancellation**: the subscription continues. Repeat with a seat
   decrease scheduled first: the dialog says the decrease is released.
2. **Portal.** Cancel in **Manage billing** (Stripe's portal) and come back:
   the card shows the same state.
3. **Subscribe again.** In Stripe test mode, end the subscription (cancel and
   wait for the period end, or delete it in the Stripe dashboard). The
   Organization becomes read-only and the card offers **Subscribe again**.
   Enter fewer seats than the people and invitations: it is refused. Enter
   enough, pay with a Stripe test card in Checkout, and return: the card waits for
   confirmation, then the Organization is writable again with all its content.
   Abandon Checkout instead: nothing changes.
4. **Transfer ownership.** On **People** choose **Transfer ownership**, pick a
   Member, leave **Keep me as an Owner** off, and confirm: they are an Owner and
   you are an Administrator; both of you and the other Owners are notified. Do it
   again keeping the role: two Owners.
5. **Leave.** As the only Owner choose **Leave**: you must pick a successor and
   leave with the transfer. As the only person in the Organization the dialog
   tells you to invite someone or delete the Organization.
6. **Billing contact.** Change the billing name, then the email. The old address
   gets a short notice with the new one partly hidden; the other Owners and
   Administrators are notified; **Activity** shows which field changed but not the
   values. A sixth change in a day is refused with the hours to wait.
7. **Needs a human.** Run this guide in Stripe test mode, check the emails in a
   real mail client, and review the Finnish texts.

## Interface redesign

**Status: Available**

1. **Shell.** Sign in. Every page has the dark sidebar (Organization switcher,
   **Overview**, your Yearclocks with the recent ones first, **My groups** if
   you are in a Group, and **Administration** for Owners and Administrators)
   and a top bar with the page title and your initials. The current page is
   highlighted. Use Back and Forward: each page has its own address.
2. **Account menu.** Open your initials: it shows who is signed in, **English**
   and **Suomi**, and **Sign out**. Switch the language and back.
3. **Administration pages.** As an Owner, open each item under
   **Administration**. Each has a one-line description, cards, and an empty
   state when there is nothing yet. **Delete Organization** is on
   **Organization settings** in the red danger zone. As an Administrator,
   **Billing and seats** and **Organization settings** are missing; as a
   Member, the whole section is missing.
4. **Planner.** Open a Yearclock. The toolbar holds the length (1–24 months),
   the arrows, **Current period**, search, and **New Event**. The circle fills
   the space; the panel beside it has **Events**, **Details** (after choosing
   an Event), and **Filters**. If others changed things since your last visit,
   the "N changes" badge shows or hides the list.
5. **Event drawer.** Press **New Event** or **Edit**: the form opens from the
   right with the circle still visible. Escape closes it and returns focus.
6. **Yearclock settings.** As an Editor, open **Yearclock settings**: Layout,
   Lanes, Categories, **Plan a season again**, and copying and linking Lanes
   are there. A Viewer does not see the link.
7. **Confirmations and messages.** Delete an Event: a dialog states what
   happens, with a red action; focus starts on **Cancel**. A save shows a
   short message at the bottom right that disappears by itself; an error
   stays next to the form.
8. **Phone.** On a phone, open the menu button at top left for the sidebar.
   The circle comes first and the panel below it; the Event form covers the
   screen. Nothing scrolls sideways.
9. **Operator console.** Sign in at `/platform` with a platform account: the
   same frame with a **Platform** badge and its own sidebar.
10. **Needs a human.** Review the Finnish wording of the new texts, and use a
    screen reader over the shell, the panel tabs, and the Event drawer.

