# Yearclock

The domain of visually planning recurring and predictable organizational work across a calendar year.

## Language

**Yearclock**:
An Organization-owned, enduring visual planning timeline containing past and future Events independently of how much time is currently displayed.
_Avoid_: Annual Plan, year progress indicator, calendar

**Planning Window**:
The date range through which a user views a Yearclock. It covers whole consecutive months (1, 3, 6, 12, 18, or 24), starts by default at the Yearclock Start Month of the current season, and displays 12 months unless the user chooses another length. (Yearclock V2)

**Yearclock Start Month**:
The month in which a Yearclock's planning year begins, January by default. It sets the default Planning Window and the quarters; it never moves Events. (Yearclock V2)
_Avoid_: Annual Plan, reporting period

**Category**:
An optional name and color assigned to one Event for classification and filtering across Lanes. An Event has at most one Category, which is either a Yearclock Category or an Organization Category.
_Avoid_: Tag, Label, Lane

**Yearclock Category**:
A Category defined within one Yearclock by its Editors.

**Organization Category**:
A Category defined once by an Owner or Admin and offered, locked, in every Yearclock of the Organization. (Yearclock V2)

**Label**:
An Organization-defined name and color. An Event may carry up to ten Labels to add status, type, owner, or other classification beyond its Category. Label names are visible to every Organization User, and Labels never affect access. (Yearclock V2)
_Avoid_: Tag, Category

**Filter**:
A personal, temporary choice of the Lanes, Categories, and Labels shown on a Yearclock. It is kept in the user's browser and never changes what others see. (Yearclock V2)
_Avoid_: View, saved view

**Display**:
A way of drawing the Planning Window: Circle, Timeline, List, or Agenda. All displays show the same Events under the same Filters. It is a personal choice kept in the user's browser. (Yearclock V2)
_Avoid_: View, layout

**Export**:
A file of a Yearclock's Events (Excel, CSV, or calendar `.ics`) containing only what the user may read, or a printout or image of the Yearclock. Every export is recorded in the Audit Log without content. (Yearclock V2)

**Import**:
Creating Events in a Yearclock from a spreadsheet file. It is previewed first and saved all or nothing; Lanes, Categories, and Labels must already exist, and Series are not imported. (Yearclock V2)

**Organization Export**:
A JSON file of an Organization's content (members, Groups, Yearclocks, Lanes, Categories, Labels, Events, Series, and access) that only an Owner can download, for handover. It leaves out History, the Audit Log, and billing data. (Yearclock V2)

**Data transfer**:
Exporting everything an Owner or Admin administers, across all their Organizations, as one CSV file (the Transfer file), and importing that file back. The import updates existing rows by id, creates missing ones, never deletes, is previewed first, and is saved all or nothing. It holds no people or access rights. (Yearclock V2)

**Notification**:
A short message to one Organization User about a change in their access or role, or (for Owners and Admins) about Support Access, billing, or deletion. It is shown in an in-app inbox, optionally emailed, deleted after 90 days, and never carries Event content. (Yearclock V2)

**Summary**:
An opt-in email, weekly or daily at 08:00 Organization time, listing upcoming Events from Yearclocks the person chose. It replaces per-Event reminders. (Yearclock V2)

**Cancellation**:
An Owner's request to end an Organization's subscription at the end of the paid period. It keeps full access until then, can be undone until then, and leaves the content intact when the Organization becomes read-only. (Yearclock V2)

**Next charge**:
The date and amount of an Organization's next regular invoice, as Stripe previews it for the current seats and any scheduled seat decrease or cancellation. Only Owners see it in the product; Yearclock stores and computes nothing. (Yearclock V2)

**Payment history**:
The latest invoices of an Organization's Stripe customer shown to its Owners, with a link to each in Stripe. It is a view of Stripe's data, not a Billing Record. (Yearclock V2)

**Legal Document**:
One of the versioned texts Yearclock publishes in Finnish and English (terms, data processing agreement, privacy notice, browser storage notice, sub-processors, switching, security, provider information). A draft is never required; a published one has a version and an in-force date. (Yearclock V2)

**Acceptance**:
The record that an Owner accepted one version of a required Legal Document for an Organization: who, when, in which language. It is made at sign-up and again for each new version, and it is kept after the Organization is purged. (Yearclock V2)

**Sub-processor**:
A company that processes customer personal data for Yearclock on its behalf (hosting, email, payments, identity). Owners are told in advance when the list changes. (Yearclock V2)

**Resubscription**:
Buying a new subscription for an Organization whose subscription has ended, which makes it active again with its content. (Yearclock V2)

**Ownership Transfer**:
Making an existing active member an Owner and, unless they keep the role, lowering the previous Owner to Admin in one action. The last Owner who leaves must name a successor. (Yearclock V2)

**Time of Day**:
An optional start and end time on an Event, read in the Organization's time zone, that adds detail to its dates without changing them. The circle keeps its day resolution. (Yearclock V2)

**Location**:
Optional free text saying where an Event happens. (Yearclock V2)

**Link**:
A titled `http(s)` address on an Event or Series; there can be up to ten, and they replace the single Event link. (Yearclock V2)

**Lane**:
A concentric visual ring within a Yearclock representing a process, responsibility, team, or focus area. Every Event belongs to one Lane, and Lanes do not define access permissions.
_Avoid_: Category, permission group

**Linked Lane**:
A Lane of a Yearclock that shows another Yearclock's Lane, its Source Lane, live and read only. It never grants access: each viewer sees its content only with read access to the source Yearclock. (Yearclock V2)
_Avoid_: synced ring, shared Lane

**Source Lane**:
The own Lane of a Yearclock that a Linked Lane shows. Its Events are changed only in its own Yearclock. (Yearclock V2)

**Roll-up Yearclock**:
A Yearclock that consists of Linked Lanes only, used as an overview of several Yearclocks. It is a way of using a Yearclock, not a separate kind. (Yearclock V2)
_Avoid_: master Yearclock

**Event**:
A dated planning entry in one Lane, representing something expected to occur on a start date or across an all-day date range. It may describe future work, but it has no assignment, due-date, completion, or execution state.
_Avoid_: Task, Plan Item, calendar item

**Plan Again**:
Copying Events one year ahead, either one Event through a prefilled form or a season's chosen Lanes and Categories at once. Series are not copied, because they continue on their own. (Yearclock V2)

**Bulk Edit**:
One all-or-nothing change (move, categorize, Labels, or delete) to up to 200 selected Events. (Yearclock V2)

**Series**:
A recurrence definition that produces related Event Occurrences according to a weekly, monthly, or yearly schedule. A change to one Occurrence leaves the Series intact, while a change from a selected Occurrence onward ends the original Series and creates a successor.
_Avoid_: Recurring event, template

**Occurrence**:
One dated Event produced by a Series. An individually changed Occurrence is an exception: its explicitly overridden fields remain independent while its other fields continue to follow the Series.
_Avoid_: Instance, repetition

**Series Date**:
The date generated for an Occurrence by its Series before any individual date change. It remains the Occurrence's stable position within the recurrence sequence.
_Avoid_: Display date, modified date

**Skipped Occurrence**:
An Occurrence intentionally omitted from its Series without erasing its identity or history. It is hidden from the normal Yearclock view and may be restored.
_Avoid_: Deleted Occurrence

**Event Revision**:
The stored state of an Event after one change, with its time, actor, and reason. It is customer content kept outside the Audit Log, is visible to everyone who may read the Yearclock, and never grants access. (Yearclock V2)
_Avoid_: audit entry, snapshot

**Previous Visit**:
The time a user last opened a Yearclock before the current visit. Changes by others after it are marked as new to that user. (Yearclock V2)

**Organization**:
A customer organization that owns its Yearclocks and controls its users' access to them.
_Avoid_: Tenant, account, company

**User Account**:
A person's authenticated identity, used either for customer Organization memberships or as a Platform User, never both.
_Avoid_: Organization, membership

**Organization User**:
A User Account's membership in one Organization, whatever its Organization role (Owner, Admin, or Member). It carries that Organization's granted permissions and occupies one Organization Seat. Removing the membership does not delete the User Account or its memberships in other Organizations.
_Avoid_: User Account, tenant user

**Member**:
The Organization role of an Organization User who is neither an Owner nor an Admin. A Member sees the Organization workspace and only the Yearclocks for which they hold a Yearclock Editor or Viewer grant; they cannot see the membership list, seats, audit activity, or Support Access requests.
_Avoid_: Organization User (for this role), basic user, guest

**Organization Admin**:
A customer-side role that can see, create, and manage every Yearclock without a Yearclock grant, grant Yearclock Editor and Viewer access, and manage Organization Users, including other Admins. When External Signals are introduced after V1, it also selects them. It cannot manage billing or seats, delete the Organization, or add, change, or remove Organization Owners. Because an Admin controls access, the Admin role is the confidentiality boundary of an Organization.
_Avoid_: Customer admin, tenant admin

**Organization Owner**:
An Organization User with all Organization Admin powers plus authority over ownership, billing, and Organization deletion. The User Account that creates an Organization becomes its first Owner; an Organization may have several Owners but must always have at least one, and a newly invited Owner receives authority only after accepting it.
_Avoid_: Organization Admin, creator

**Group**:
A named set of members of one Organization that can receive Yearclock Editor or Viewer access. It takes no seat, contains no other Groups, and never overrides a stronger role. (Yearclock V2)
_Avoid_: team, user group, department

**Organization-wide Access**:
A Yearclock setting that gives every member of its Organization, including future members, Viewer or Editor access. (Yearclock V2)

**Access Source**:
Why a member can open a Yearclock: their Organization role, a direct grant, a Group, or Organization-wide Access. The strongest applicable role wins. (Yearclock V2)

**Invitation**:
A single-use, expiring offer sent to an email address to create an Organization membership with proposed roles. It grants no access until the recipient authenticates and accepts it.
_Avoid_: Membership, guest access

**Subscription**:
An Organization's independent, monthly prepaid per-seat entitlement to use the Yearclock service, regardless of which User Account created or currently owns the Organization.
_Avoid_: User plan, account subscription

**Organization Seat**:
One prepaid unit of capacity for an active Organization User. Each active membership occupies a separate seat in its Organization, and an Invitation temporarily reserves available capacity.
_Avoid_: User Account license, Platform User seat

**Billing Profile**:
An Organization's billing identity and payment responsibility, managed by its Owners independently from every other Organization.
_Avoid_: Owner billing, User Account billing

**Billing Record**:
The minimal invoice, payment, and related audit information retained for accounting, disputes, and compliance after customer planning content is purged.
_Avoid_: Customer content, Billing Profile

**Pending Deletion**:
The recoverable state of an Organization after an Owner requests deletion and before the service's retention window expires. Normal access is blocked during this state, after which customer planning content is purged while required Billing Records and a minimal deletion audit record are retained.
_Avoid_: Deleted, suspended

**Yearclock Editor**:
A customer-side role that can create, change, and remove Events, Lanes, and Categories in assigned Yearclocks. It cannot create Yearclocks or grant access to them.
_Avoid_: Creator, contributor

**Yearclock Viewer**:
A customer-side role with read-only access to assigned Yearclocks.
_Avoid_: Reader, read-only user

**Platform Operator**:
The SaaS operating company responsible for supporting customer Organizations and operating the Yearclock service.
_Avoid_: Organization admin, super user

**Platform User**:
A User Account belonging to the Platform Operator and carrying platform roles instead of Organization memberships.
_Avoid_: Organization User, staff membership

**Platform Admin**:
A Platform Operator role that manages the service and customer Organizations without standing access to their Event content.
_Avoid_: Super admin, Organization Admin

**Support Agent**:
A Platform Operator role that assists customer Organizations and may access their Event content only through explicit Support Access.
_Avoid_: Platform Admin, Organization Admin

**Support Access**:
A customer-approved, scoped, time-limited, and audited grant allowing a Support Agent to access one Organization's Event content for a specific support case. It covers every Yearclock of that Organization, read-only unless write access is approved, for at most 24 hours. An Organization Owner or Admin approves it and may revoke it at any time.
_Avoid_: Impersonation, backdoor access

**External Signal**:
_Not in V1 (ADR-0027)._ A sourced, read-only observation provided by the Platform Operator that an Organization Admin may select and assign to one or more Yearclocks. It remains distinct from Events, though a Yearclock Editor may link a responding Event to it.
_Avoid_: Event, customer event, market event

**Recommendation**:
_Not in V1 (ADR-0027)._ A machine-generated proposal derived from Events and External Signals and presented to an Organization User for human judgment. It is Pending until a human marks it Accepted or Dismissed, and it never performs an action autonomously.
_Avoid_: Automated action, External Signal, Event
