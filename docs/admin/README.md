# Administrator guide

This guide is for Organization Owners and Admins, and for Platform Admins and
Support Agents. The full permission rules are in the
[authorization matrix](../architecture/organization-authorization-matrix.md).
Features marked *not yet available* are specified for V1 but not implemented.

## Where administration lives

Owners and Administrators find **Administration** in the sidebar. Each area is
its own page with its own address:

| Page | Address | Who |
| --- | --- | --- |
| People (invitations, roles, access per person) | `/organizations/{id}/admin/people` | Owners, Admins |
| Groups | `…/admin/groups` | Owners, Admins |
| Yearclocks and access (create, order, archive, delete, share) | `…/admin/yearclocks` | Owners, Admins |
| Classification (Organization Categories, Labels) | `…/admin/classification` | Owners, Admins |
| Activity | `…/admin/activity` | Owners, Admins |
| Support Access | `…/admin/support` | Owners, Admins |
| Connect an agent (connection details and the agent-access switch) | `…/admin/agents` | Owners, Admins |
| Billing and seats (billing portal, seat capacity) | `…/admin/billing` | Owners |
| Organization settings (details, Organization Export, deletion in the danger zone) | `…/admin/settings` | Owners |

The Organization overview keeps only the Yearclocks, recently opened ones, and
My groups. A page your role may not open says that the page does not exist.

## Agents and the agent call log

Shadow calls no AI model itself. People connect their own agents under **Connect an agent**; each agent acts with the rights of the person who connected it. The agent, its provider, its token cost and what it does with the data it reads are that person's responsibility. Every agent call, reads included, is recorded without its content (tool, person, agent program, outcome). Open **Activity** and choose **Agent calls** to read the record; only Owners and Admins can. Successful reads are kept for 90 days, writes and refused or failed calls longer. Turning agent access off stops every call for the Organization.

## Creating an Organization

1. Sign in and choose **Create your organization** (or **Create another
   organization**).
2. Enter the name, IANA time zone (for example `Europe/Helsinki`), default
   language, billing name and email, and the number of seats.
3. Pay in Stripe Checkout. Each seat costs EUR 30 per month before tax, billed
   in advance.
4. The Organization becomes active only after Stripe confirms payment. You
   become its first Owner, and it starts with one Yearclock and a **General**
   Lane. An unpaid signup expires after 24 hours.

## Legal documents (Owners)

The terms and the data processing agreement are public at `/legal` in Finnish and English. When you create an
Organization you tick one box for each document that is published as required; you cannot continue to checkout
until you have. Nothing is asked while no required document is published.

Open **Organization settings** to see the **Legal documents** block: for each required document it shows the
version accepted, when, and by whom (a person who has left shows as "a former member"). When a new version is
published and its in-force date has passed, an Owner sees a banner on **Billing and seats** and an **Accept this
version** button in the block. Admins and Members do not see the block. When a new version of any legal document is published, every Owner also gets a notice in the app and an email (always, even if you turned notification emails off) that states the in-force date and the 30 days to object. The Organization keeps working until
someone accepts; each acceptance is recorded and kept as contract evidence even after the Organization is purged.

## Organization Export (Owners)

- **Organization settings → Organization Export → Download Organization
  Export** saves one JSON file (`yearclock-export/1`) with the Organization,
  its members (name, email, role), Groups, Labels, Organization Categories, and
  every Yearclock with its Lanes, Categories, Events, Series, and access. Deleted
  Events and Yearclocks are not in it.
- It does not contain Event history, the Activity log, billing data, or email
  records. Use it for handover or your own records; it is not a restore file and
  Yearclock cannot import it.
- Only Owners can download it, also while the Organization is read-only or in
  Pending Deletion. Each download is recorded in Activity (with counts, never
  content), and an Owner can download it three times an hour.
- Anyone who may read a Yearclock can export its Events to Excel or CSV, and
  Editors can import Events; those actions are in Activity too (see the user
  guide). A request from one person for their own personal data is handled by
  the Platform Operator (`docs/runbooks/personal-data-request.md`).

## Seats (Owners)

- **Seat capacity** on **Billing and seats** shows Purchased, Occupied, Reserved, and Available seats.
  Every active member, including Owners, occupies one seat. A pending
  Invitation reserves one.
- **Preview increase** shows the prorated charge; **Confirm and pay** applies
  the increase only after Stripe confirms payment.
- **Schedule decrease** takes effect at renewal and cannot go below Occupied
  plus Reserved.
- Removing a person frees the seat at once but gives no credit for the current
  month.

## Inviting people (Owners and Admins)

1. Under **Invite people**, enter an email address and a role:
   **Member** or **Administrator**. Only Owners can invite an Owner.
2. The Invitation reserves a seat and is emailed. It is single-use and
   expires after seven days. **Resend** invalidates the earlier link;
   **Revoke** releases the seat.
3. The person must sign in with the invited, verified email address and accept.
4. Grant Yearclock access afterwards: open the Yearclock's **Access** section,
   choose the person and **Editor** or **Viewer**, and select **Grant**. It is
   often easier to choose **Groups to join** in the invitation: the person
   joins those Groups on acceptance and gets their access at once.

**Invite several people** takes up to 50 pasted addresses with one role and
optional Groups.
- **Preview** lists who will be invited. It skips invalid addresses,
  repeats, existing members, and people already invited, and gives the
  reason for each.
- If there are not enough seats, nothing is sent, and the preview says how
  many more seats are needed. Owners can add them under **Seats**.

## Roles and ownership

- Owners and Admins manage memberships in **People**. Admins cannot change or
  remove Owners.
- An Organization always keeps at least one Owner and may have several.
- **Transfer ownership** (Owners, on **People**) picks an active Administrator
  or Member, explains what an Owner can do (billing and subscription,
  deleting the Organization, making and removing Owners), and makes them an
  Owner in one step. Unless you choose **Keep me as an Owner** you become an
  Administrator at the same moment. The new Owner does not have to accept;
  they and the other Owners are notified and the action is in Activity. The
  billing contact is not changed: check it in **Billing and seats**.
- Choosing **Owner** in a person's role list asks for the same confirmation.
  Inviting someone new as an Owner still needs their acceptance.
- **Leave** (on your own row) removes you and frees your seat. If you are the
  only Owner you must choose a successor, who becomes an Owner as you leave.
  If you are the only person in the Organization you cannot leave: invite
  someone or delete the Organization in **Organization settings**.

## Yearclocks (Owners and Admins)

- Create, rename, and reorder Yearclocks. **Archive** hides a Yearclock from
  normal navigation; **Restore** brings it back.
- **Delete** removes a Yearclock with all its Events for 30 days; recover it
  from **Deleted Yearclocks** before the date shown. After that it is purged
  permanently.
- **Roll-up Yearclocks.** For an overview of several teams, create a
  Yearclock, add a Linked Lane for each team Lane under **Layout, Lanes and
  Categories → Link from another Yearclock**, and then remove its own default
  Lane. Access does not change: Owners and Admins see every Linked Lane, and
  other users see only the Linked Lanes whose source Yearclock they may open.
  Grant Viewer access to the source Yearclocks for everyone who should see
  the whole overview.
- Deleting a source Yearclock shows "Lane no longer available" in every roll-up
  until you recover it. Its purge removes the links, as does removing an empty
  source Lane.
- **Everyone in the Organization.** In a Yearclock's **Access**, choose No
  access, Viewer, or Editor for the whole Organization. It applies to every
  current member and to everyone who joins later. Choosing Editor asks for
  confirmation and says how many members gain edit access. A stronger
  individual grant still wins, and every change is recorded in **Activity**.

## Access overview (Owners and Admins)

- In **People**, **Access** next to a person lists every Yearclock they can
  open, with their role and every reason for it: their Organization role, a
  direct grant, a Group, or Everyone in the Organization. The strongest one
  counts.
- In a Yearclock's **Access**, **Who has access** lists everyone who can open
  it, with the same reasons.
- **Remove** asks for confirmation first and names the Yearclocks the person
  will lose. Removing a membership also removes its Group memberships and
  direct grants. Yearclocks belong to the Organization, so nothing needs to
  be handed over.

## Groups (Owners and Admins)

- The **Groups** page collects members who need the same
  Yearclock access, for example "Board" or "Finance team".
  - Create, rename, and delete Groups there, and add or remove members.
  - Group names must be unique in the Organization, and an Organization can
    have up to 100 Groups.
  - A Group takes no seat, and Groups cannot contain other Groups.
- Deleting a Group asks for confirmation. The confirmation says how many
  members and Yearclocks it affects and who can no longer open a Yearclock at
  all.
- Members see only the Groups they belong to, under **My groups**. They never
  see other Groups' members. Every change is recorded in **Activity**.
- Removing someone from the Organization also removes them from every Group.
- In a Yearclock's **Access**, under **Groups**, give a Group Viewer or Editor
  access, change its role, or remove it. People gain that access as soon as
  they join the Group and lose it when they leave, unless another source
  still gives it. The strongest source always wins.

## Audit activity (Owners and Admins)

- Open **Activity** to see changes newest first with the action, the person
  who made them, and the time. Filter by area and use **Load more** for older
  entries. Changes made through Support Access are marked.
- Ordinary viewing is not logged. Audit records cannot be changed.

## Billing contact (Owners)

- On **Billing and seats**, **Billing contact** shows the name and email on
  invoices. Change either and choose **Save billing contact**; Stripe is updated
  first and a failure changes nothing. The billing address, VAT ID, and payment
  method stay in **Manage billing**.
- When the email changes, the old address gets a short notice with the new one
  partly hidden (`b***@e***.com`), and the other Owners and Administrators are
  notified. Activity records which field changed, never the values. At most 5
  changes a day.

## Billing states

- Owners select **Manage billing** (on **Billing and seats**, or in the
  notice shown when the subscription needs attention) to open Stripe's Customer Portal for
  payment methods, invoices, and cancellation. It stays available while the
  Organization is read-only.
- **Next charge** and **Payments** (Owners only, on **Billing and seats**) show
  what Stripe will charge next (date, amount with tax, and the number of seats)
  and the latest 12 invoices with a link to each one in Stripe. Admins and
  Members do not see them. They are read from Stripe each time the page opens
  and are not kept in Yearclock; if Stripe cannot answer, the page says so and
  the rest keeps working. The seat rules are shown beside the next charge: a seat
  you add is charged at once for the days left in the month, a seat you remove
  stays paid until the period ends, and nothing is refunded. After a scheduled
  cancellation the page says there is no further charge. For a failed renewal the
  workspace shows the seven-day deadline, not Stripe's retry dates.
- **Cancel subscription** (Owners, on **Billing and seats**) ends the
  subscription at the end of the paid period and never earlier; there is no
  refund. The dialog states the end date and what happens next: the
  Organization is read-only afterwards, nothing is deleted, the Organization
  Export still works, and an Owner can subscribe again. You may give a reason
  from a short list. A scheduled seat decrease is released. Until the end date
  everything keeps working and **Undo cancellation** continues the
  subscription. Owners and Admins are told when it is cancelled or undone. Cancelling in the
  billing portal gives the same result.
- If a renewal payment fails, everything keeps working for seven days and the
  workspace shows the deadline. After that the Organization is read-only
  until an Owner pays; content stays visible.

## Subscribing again (Owners)

- When a subscription has ended, the Organization is read-only and the notice
  says so. On **Billing and seats**, **Subscribe again** asks for the number of
  seats (at least the people and invitations the Organization has) and opens
  Stripe's payment page. When Stripe confirms the payment the Organization is
  writable again within moments, with all its content; the page updates by
  itself. If you leave the payment page, nothing changes. If the payment only
  failed (a renewal), fix the payment method in **Manage billing** instead.
- Content of an Organization whose subscription ended is not deleted
  automatically. Deleting is a separate, confirmed action.

## Deleting an Organization (Owners)

- Open **Organization settings**, find **Delete Organization** in the danger
  zone, tick the confirmation, and
  choose **Delete Organization**. Access stops at once for everyone, including
  Support Access.
- For 30 days the Organization list shows *Pending deletion — purged on
  (date)* with **Restore**. Only Owners see it.
- After 30 days all Yearclocks, Events, people, and invitations are
  permanently purged. Invoices, billing identity, and a record of what
  happened (without content) are kept.
- Deletion does not cancel billing. Cancel the subscription separately in the
  billing portal. Restoring keeps whatever billing state Stripe reports, so a
  cancelled or unpaid Organization comes back read-only.

## Classification (Owners and Admins)

- The **Classification** page manages the Organization's
  Labels. Labels add status, type, owner, or other details to Events in every
  Yearclock. Each has a name (up to 60 characters) and a colour from a fixed
  palette, and shows how many Events use it. An Organization can have up to
  200 Labels.
- Label names are visible to everyone in the Organization, including people
  without access to a Yearclock. Do not put confidential information in a
  Label name.
- Owners and Admins rename, recolour, merge, and delete Labels. **Merge** moves
  every Event of one Label to another and removes the first; **Delete** removes
  the Label from every Event. Both ask for confirmation with the number of
  affected Events, and both appear in **Activity** under *Labels*.
- Editors can also create a Label while editing an Event. Creating a name that
  already exists (ignoring capital letters) reuses the existing Label.
- While the Organization is read-only, Labels can be viewed but not changed.
- **Organization Categories** (also under Classification) colour Events the
  same way in every Yearclock, up to 40 of them. Editors can choose them in
  any Yearclock but cannot change them; each Yearclock can still have its own
  Categories. Reorder them with **Up** and **Down**. Deleting one asks for
  confirmation with the number of affected Events, which then become
  uncategorized.

## Notifications for Owners and Admins

- Owners and Admins are also told, in the app and by email, when platform
  support requests Support Access and when a grant is revoked or expires, when
  a renewal payment fails or the subscription is canceled, and when Organization
  deletion is requested (the person who did it is not told). Each opens the
  matching administration page from **Notifications**.
- Notification email goes out right away, at most 10 a day to one person
  (`LIMIT_NOTIFICATION_EMAILS_PER_DAY`); the rest stay in the app. Invitations,
  billing receipts, and sign-in email do not count. Each person chooses
  their own switches in **Notification settings**; Organization notices are on
  by default for both channels.
- Notifications never include what is in an Event. The optional Summary of
  upcoming Events is the exception: each person turns it on for themselves, and it
  lists only Events they may read.

## Support Access

- Platform support sees your content only when you allow it. A Support Agent
  requests access for one case, read-only by default or with Event editing,
  for up to 24 hours. Give them your Organization ID, shown in the
  **Support Access** page and in **Organization settings**.
- Owners and Administrators see the request in **Support Access** and choose
  **Approve** (optionally for fewer hours than requested) or **Reject**. An
  active grant can be ended at once with **Revoke now**; it also ends by
  itself when its time runs out.
- A grant covers every Yearclock of the Organization. Every request,
  decision, view, change, expiry, and revocation appears in **Activity**,
  marked *through Support Access*. Members cannot see or decide requests.
- Platform staff have no other access to Event content, and there is no
  emergency bypass.

## The Base line, Scenarios and what agents may do

Each Model has one **Base line** (the history of what has really happened) and any number of **Scenarios**. The
users' view of these is in the [user guide](../user/README.md); this section is about who may do what.

| Action | Who |
| --- | --- |
| Read every line, Event and state | Every member of the Organization (also when the Organization is read-only) |
| Write Events on the **Base line** (including canvas drawing on it) | Owners and Admins |
| Create a Scenario from any Event they can read; write Events in a Scenario | Every member, including Members |
| Rename or delete a Scenario | Its creator, Owners and Admins (a Scenario others start from cannot be deleted) |
| **Adopt** a Scenario into the Base line | Owners and Admins; into another Scenario, whoever may write that Scenario |
| Anything that writes | Nobody while the Organization is read-only (subscription ended or cancelled) |

Limits: a ceiling of events per line (`LIMIT_CHANGES_PER_LINE`, 5000) and lines per model
(`LIMIT_LINES_PER_MODEL`, 200); beyond it a write is refused (`limit_reached`). Every line and Event write is in Activity
(`line.created`, `line.renamed`, `line.deleted`, `line.adopted`, `event.created`, `event.updated`, `event.deleted`) with ids and
counts only, never element names or note text. An adoption is refused with an explanation when the Base line has moved
on since the Scenario started; ask the person to create a new Scenario from the latest state.

**Agents** act with the rights of the person who connected them, so an agent run by a Member cannot write the Base
line, and one run by an Owner or Admin can. The model tools (see
[`docs/runbooks/mcp-interface.md`](../runbooks/mcp-interface.md)) are:

- Reads: `list_models`, `get_model`, `list_lines`, `list_events`, `get_state` (by Event or by date), `list_metrics`,
  `get_metric_series`, `list_simulations`, `get_simulation`, `get_analysis`.
- Writes: `create_model`, `create_scenario`, `add_event`, `update_event`, `delete_event`, `adopt_scenario`,
  `create_node`, `create_connection` (inside an Event), `create_metric`, `set_metric_values`, `run_simulation`,
  `generate_analysis`, `set_analysis_summary`, `add_proposal`.

`delete_event` and `adopt_scenario` are destructive; the agent's own confirmation settings are the only prompt. Chain
checks, stale-version checks and audit apply exactly as in the web application, and every call is in the agent call log.
The old version tools (`create_version`, `merge_version`, `get_version_changes`) no longer exist.

## Connect an agent (Owners and Admins)

The page **Connect an agent** shows how people in the Organization can connect an AI agent of their
choice (MCP, ADR-0037): the server address, the client ID, and the client secret (hidden until you
choose **Show the secret**; each reveal is recorded in Activity), with steps for Claude's custom
connector. Give the three values to the people who want to connect. They must have signed in to
Yearclock at least once, and then sign in through Authentik with their own account.

- An agent acts with the rights of the person who signed in, saves changes at once, and each change
  appears in Activity and in the Event history as made through MCP. Yearclock adds no approval step;
  confirmations are the agent's own settings.
- The secret is the same for every Organization, so it does not separate customers.
- **Agent access for this Organization** is a switch. When it is off, every agent request for the
  Organization is refused, whoever makes it; the web application is unaffected. If the operator has
  blocked agent access, the page says so and the switch cannot be turned on.

## Platform staff

- Platform staff sign in at `/platform` with their platform account. An
  operator first enrolls them with
  `python -m app.platform_admin enroll --email <address> --role platform_admin`
  (or `support_agent`); the first sign-in with that verified email creates the
  account.
- The console has its own sidebar, marked **Platform**: **Service health**
  (`/platform`), **Organizations** (`/platform/organizations`, Platform
  Admins), **Failed jobs** (`/platform/jobs`), and **Support Access**
  (`/platform/support`, Support Agents). A page the role cannot open says so.
- Platform Admins see each Organization's status, subscription, seats, and
  member and Yearclock counts, can **Replay** failed jobs, and can **Block** or **Unblock** agent access (MCP)
  for an Organization; the Organization's Owners cannot lift a block. Support Agents
  see service health and failed jobs. Neither sees customer content.
- Platform accounts cannot hold Organization memberships. Staff who also use
  Yearclock as customers need a separate customer account.

## Exporting and importing the Organizations you administer

- Owners and Admins use **Export and import data** in the account menu. One CSV
  covers every Organization where you are Owner or Admin, and the same file can
  be imported back (updates existing rows by id, creates the rest, deletes
  nothing). Unlike the Organization Export it holds no member names, emails, or
  access rights, which is why Admins may use it. The Organization Export (JSON,
  Owners only, for handover) is unchanged. See the user guide for the steps.
- An Organization that is read-only or not active rejects its rows in an import.
- Each Organization gets an Activity entry per transfer (`data.export`,
  `data.import_preview`, `data.import`) with counts, never content.
