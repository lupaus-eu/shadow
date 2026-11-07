# Shadow

The domain of modelling an organisation as a digital twin: a graph over time with metrics, forecasts, simulations, and analysis, owned by a customer Organization.

## Language

**Notification**:
A short message to one Organization User about a change in their role or membership, or (for Owners and Admins) about Support Access, billing, or deletion. It is shown in an in-app inbox, optionally emailed, deleted after 90 days, and never carries model content.

**Cancellation**:
An Owner's request to end an Organization's subscription at the end of the paid period. It keeps full access until then, can be undone until then, and leaves the content intact when the Organization becomes read-only.

**Model**:
An Organization-owned digital twin of an organisation: a graph of nodes and connections that is described by a Metamodel, has Versions, and carries Metrics.
_Avoid_: Diagram, workspace

**Metamodel**:
The node types, connection types, and allowed connections of one Model. It starts from the default metamodel and the Model's editors can change it. A type or rule that nodes or connections still use cannot be deleted. All Versions of a Model share it.
_Avoid_: Schema, template

**Node**:
One element of the organisation in a Version of a Model (for example a team, a system, or a process), with a name, a description, and a node type.

**Connection**:
A typed, directed link between two Nodes of the same Version. The Metamodel must allow its connection type between those node types.
_Avoid_: Edge, relation

**Version**:
A complete copy of a Model's graph and Metrics. The Baseline is the Model's current state; other Versions are forked from a base Version to explore a change. Each Node remembers its origin, so a Version can list its changes against the base.
_Avoid_: Branch, scenario

**Baseline**:
The Version of a Model that describes the organisation as it is now and is the base of forks.

**Change list**:
The added, removed, and changed Nodes and Connections of a Version compared with its base.

**Merge**:
Applying a Version's change list to its base Version. Only an Owner or Admin may merge. Metrics are not merged, and afterwards the Version shows no changes.
_Avoid_: Promote, publish

**Metric**:
A named measure of a Version with a unit and monthly values. An entered Metric holds its values; a derived Metric is computed from a formula over other Metrics of the same Version.
_Avoid_: KPI, series

**Formula**:
An expression over the keys of other Metrics that defines a derived Metric. Cycles are rejected.

**Forecast**:
Predicted monthly values of a Metric by one method: linear, seasonal, Holt, or Prophet, with an uncertainty band. Each method needs a minimum history (Prophet 12 months, seasonal 24).

**Simulation**:
A stored run of Forecasts for a Version, optionally with what-if adjustments. Derived Metrics follow the adjusted values.
_Avoid_: Scenario, projection

**Analysis**:
The Findings and Proposals derived from a Simulation by rules, optionally extended by an AI summary and AI Proposals.

**Finding**:
An observation in an Analysis, such as a Metric that falls below a threshold in the forecast.

**Proposal**:
A suggested action from an Analysis. It is open until someone accepts or dismisses it, and the decision survives a new Analysis. Rule Proposals and AI Proposals (`kind` `rule` or `ai`) are kept apart.
_Avoid_: Recommendation, task

**AI Analysis**:
An optional Analysis step that sends metric names and forecast figures to the Anthropic API and stores the returned summary and Proposals. It exists only when `ANTHROPIC_API_KEY` is set; the Organization has no separate switch yet.

**Import**:
Reading Metric values for a Version from a CSV or Excel file, in a wide layout (months as rows, Metrics as columns) or a long layout (metric, period, value). Unknown or derived Metrics and unreadable cells are reported and skipped.

**Export**:
Writing the Metric series as CSV or Excel, or an Analysis as an Excel workbook. Cells that could run as formulas are neutralised.

**Agent tool**:
An MCP tool that lets an AI agent the person chooses read or change Models, Versions, Metrics, Simulations, and Analyses under the person's own rights and the same rules as the web application. Every change is audited as made through MCP.

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
A customer-side role that can manage Organization Users, including other Admins, merge Versions into their base, and connect agents. It cannot manage billing or seats, delete the Organization, or add, change, or remove Organization Owners.
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
