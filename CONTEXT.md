# Shadow

The domain of modelling an organisation as a digital twin: a graph over time with metrics, forecasts, simulations, and analysis, owned by a customer Organization.

## Language

**Notification**:
A short message to one Organization User about a change in their role or membership, or (for Owners and Admins) about Support Access, billing, or deletion. It is shown in an in-app inbox, optionally emailed, deleted after 90 days, and never carries model content.

**Cancellation**:
An Owner's request to end an Organization's subscription at the end of the paid period. It keeps full access until then, can be undone until then, and leaves the content intact when the Organization becomes read-only.

**Model**:
An Organization-owned digital twin of an organisation: a graph of nodes and connections that is described by a Metamodel, has a history of dated Changes in Lines, and carries Metrics.
_Avoid_: Diagram, workspace

**Metamodel**:
The node types, connection types, and allowed connections of one Model. It starts from the default metamodel and the Model's editors can change it. A type or rule that nodes or connections still use cannot be deleted. All Lines of a Model share it.
_Avoid_: Schema, template

**Node**:
One element of the organisation in a State of a Model (for example a team, a system, or a process), with a name, a description, and a node type.

**Connection**:
A typed, directed link between two Nodes of the same State. The Metamodel must allow its connection type between those node types.
_Avoid_: Edge, relation

**Line**:
An ordered history of Changes of one Model. A Line is either the Base line or a Scenario. A Line's graph is never stored whole; it is computed from its Chain.
_Avoid_: Version, branch

**Base line**:
The one Line of a Model that records what has really happened to the organisation. It can be renamed and never deleted; its Present state is the organisation as it is now. Only Owners and Admins write it.
_Avoid_: Baseline, main

**Scenario**:
Any Line other than the Base line: a what-if with a name, a parent Line, a Branch point, and Changes of its own. It can start from another Scenario. A Member may write it; an Owner or Admin may Adopt it.
_Avoid_: Fork, Version

**Change**:
A dated item on one Line: a title, an optional note, a required date, and an ordered list of Edits. Changes sort by date, then by the order they were entered. Any Change can be corrected or deleted afterwards as long as the Chain stays valid. In the interface a Change is shown in the **change list** of a Line.
_Avoid_: Event (a Change is not an event; see **Event** below)

**Edit**:
One step inside a Change on one element: add node, remove node, update node (name, description, type), add connection, remove connection, re-route connection, or change connection type. Removing a Node removes its Connections in the same step.

**Change list**:
The Changes of the shown Line, oldest first, beside the Canvas. A Scenario's list begins with the fixed **Start** row, which is not a Change.

**Start**:
The first row of a Scenario's change list: the State of the parent Line at the Scenario's Branch point, shown read-only. It names the parent Line and the Change the Scenario starts after. The Base line has no Start row.

**Planned change**:
A Change dated after today in the Organization's time zone. It is an ordinary Change that has not happened yet; it joins the Present state when its date arrives.

**Event**:
Reserved for the organisation's own happenings (for example a launch or a reorganisation) and for Yearclock Events. In the Model timeline the dated item is a **Change**, never an event. **Audit Event** (an entry of the audit log), Stripe events and browser (DOM) events are different things again.

**State**:
The graph (Nodes and Connections with their types) after one Change of one Line, computed by replaying the Chain. It can also be asked for a date: the State after the last Change dated that day or earlier. The State of a Scenario's Start row is the parent Line's State at the Branch point.

**Present state**:
The State after the last Change of a Line dated today or earlier. Planned changes are not part of it.

**Branch point**:
The Change of a parent Line from which a Scenario starts. The Scenario refers to the Change; it is not a copy, so the Change cannot be deleted while a Scenario starts from it.

**Chain**:
The sequence of Changes a State is replayed from: the Changes of every ancestor Line up to the Branch point, then the Line's own Changes up to the chosen Change. Every write is checked by replaying the Chains it touches; a write that would break one is refused ("chain broken") and nothing is saved.

**Adopt**:
Appending a Scenario's own Changes to its parent Line when the parent has not moved on since the Branch point and no adopted Change is dated before the parent's last Change. Metrics are not adopted. Replaces Merge.

**Position**:
Where a Node is drawn on the Structure canvas. A property of the drawing per Line and Node, not a Change; moving a Node writes no Change.

**Canvas**:
The drawing surface of a Model's Structure tab. It shows the State of one Line after one Change, and drawing on it edits that Change.

**View**:
The current pan and zoom of the Canvas. It is kept in the browser's memory only, never stored on the server, and is separate from Positions.

**Version** (retired):
Replaced by **Line**. A Model's complete copies of its graph no longer exist; each former Version became a Line (the former Baseline the Base line, each fork a Scenario with one Change holding its difference).

**Baseline** (retired):
Replaced by **Base line**.

**Change list** (retired meaning):
The former computed difference between a Version and its base no longer exists; the Structure canvas marks what the shown Change edited. The term now names the list of Changes of a Line (see **Change list** above).

**Merge** (retired):
Replaced by **Adopt**, which appends Changes instead of applying a difference, and only while the parent has not moved on.

**Metric**:
A named measure of a Line with a unit and monthly values. An entered Metric holds its values; a derived Metric is computed from a formula over other Metrics of the same Line.
_Avoid_: KPI, series

**Formula**:
An expression over the keys of other Metrics that defines a derived Metric. Cycles are rejected.

**Forecast**:
Predicted monthly values of a Metric by one method: linear, seasonal, Holt, or Prophet, with an uncertainty band. Each method needs a minimum history (Prophet 12 months, seasonal 24).

**Simulation**:
A stored run of Forecasts for a Line, optionally with what-if adjustments. Derived Metrics follow the adjusted values. It is not a Scenario: a Scenario is a Line of Changes, a Simulation adjusts Metric values.
_Avoid_: Scenario, projection

**Analysis**:
The Findings and Proposals derived from a Simulation by rules, optionally extended by a summary and Proposals an Agent wrote through MCP.

**Finding**:
An observation in an Analysis, such as a Metric that falls below a threshold in the forecast.

**Proposal**:
A suggested action from an Analysis. It is open until someone accepts or dismisses it, and the decision survives a new Analysis. Rule Proposals and Agent Proposals are kept apart by **Proposal source**.
_Avoid_: Recommendation, task

**Agent**:
Software acting for a person through MCP under that person's own account and rights. It is not part of Shadow: Shadow calls no model itself (ADR-0047). The agent, its provider and its token cost are the connecting person's responsibility.
_Avoid_: AI Analysis, bot

**Agent call**:
One MCP tool call, successful, refused or failed, recorded without its arguments or result with the person and the agent program. Owners and Admins read the record in Activity.

**Proposal source**:
Where a Proposal came from: `rule` (generated from the forecast rules) or `agent` (written through MCP). There is one agent Proposal per Metric; repeating the call replaces it.

**Import**:
Reading Metric values for a Line from a CSV or Excel file, in a wide layout (months as rows, Metrics as columns) or a long layout (metric, period, value). Unknown or derived Metrics and unreadable cells are reported and skipped.

**Export**:
Writing the Metric series as CSV or Excel, or an Analysis as an Excel workbook. Cells that could run as formulas are neutralised.

**Agent tool**:
An MCP tool that lets an AI agent the person chooses read or change Models, Lines, Changes, Metrics, Simulations, and Analyses under the person's own rights and the same rules as the web application. Every change is audited as made through MCP.

**Next charge**:
The date and amount of an Organization's next regular invoice, as Stripe previews it for the current seats and any scheduled seat decrease or cancellation. Only Owners see it in the product; Shadow stores and computes nothing.

**Payment history**:
The latest invoices of an Organization's Stripe customer shown to its Owners, with a link to each in Stripe. It is a view of Stripe's data, not a Billing Record.

**Legal Document**:
One of the versioned texts Shadow publishes in Finnish and English (terms, data processing agreement, privacy notice, browser storage notice, sub-processors, switching, security, provider information). A draft is never required; a published one has a version and an in-force date.

**Acceptance**:
The record that an Owner accepted one version of a required Legal Document for an Organization: who, when, in which language. It is made at sign-up and again for each new version, and it is kept after the Organization is purged.

**Sub-processor**:
A company that processes customer personal data for Shadow on its behalf (hosting, email, payments, identity). Owners are told in advance when the list changes.

**Resubscription**:
Buying a new subscription for an Organization whose subscription has ended, which makes it active again with its content.

**Ownership Transfer**:
Making an existing active member an Owner and, unless they keep the role, lowering the previous Owner to Admin in one action. The last Owner who leaves must name a successor.

**Organization**:
A customer organization that owns its Models and controls who may use them.
_Avoid_: Tenant, account, company

**User Account**:
A person's authenticated identity, used either for customer Organization memberships or as a Platform User, never both.
_Avoid_: Organization, membership

**Organization User**:
A User Account's membership in one Organization, whatever its Organization role (Owner, Admin, or Member). It carries that Organization's granted permissions and occupies one Organization Seat. Removing the membership does not delete the User Account or its memberships in other Organizations.
_Avoid_: User Account, tenant user

**Member**:
The Organization role of an Organization User who is neither an Owner nor an Admin. A Member works with the Organization's Models; they cannot see the membership list, seats, audit activity, or Support Access requests.
_Avoid_: Organization User (for this role), basic user, guest

**Organization Admin**:
A customer-side role that can manage Organization Users, including other Admins, write the Base line, adopt Scenarios into it, and connect agents. It cannot manage billing or seats, delete the Organization, or add, change, or remove Organization Owners.
_Avoid_: Customer admin, tenant admin

**Organization Owner**:
An Organization User with all Organization Admin powers plus authority over ownership, billing, and Organization deletion. The User Account that creates an Organization becomes its first Owner; an Organization may have several Owners but must always have at least one, and a newly invited Owner receives authority only after accepting it.
_Avoid_: Organization Admin, creator

**Invitation**:
A single-use, expiring offer sent to an email address to create an Organization membership with proposed roles. It grants no access until the recipient authenticates and accepts it.
_Avoid_: Membership, guest access

**Subscription**:
An Organization's independent, monthly prepaid per-seat entitlement to use the Shadow service, regardless of which User Account created or currently owns the Organization.
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

**Platform Operator**:
The SaaS operating company responsible for supporting customer Organizations and operating the Shadow service.
_Avoid_: Organization admin, super user

**Platform User**:
A User Account belonging to the Platform Operator and carrying platform roles instead of Organization memberships.
_Avoid_: Organization User, staff membership

**Platform Admin**:
A Platform Operator role that manages the service and customer Organizations without standing access to their model content.
_Avoid_: Super admin, Organization Admin

**Support Agent**:
A Platform Operator role that assists customer Organizations and may access their model content only through explicit Support Access.
_Avoid_: Platform Admin, Organization Admin

**Support Access**:
A customer-approved, scoped, time-limited, and audited grant allowing a Support Agent to access one Organization's model content for a specific support case. It is read-only unless write access is approved, for at most 24 hours. An Organization Owner or Admin approves it and may revoke it at any time.
_Avoid_: Impersonation, backdoor access
