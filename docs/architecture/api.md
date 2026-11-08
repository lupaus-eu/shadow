# API

## Health

`GET /health` on the backend (host port 8100 locally). It is not routed
through Caddy, which forwards `/api/*` unchanged to the backend and every other
path to the frontend.

Response:

```json
{
  "status": "ok",
  "service": "Shadow"
}
```

## Authentication

- `GET /api/v1/auth/login?return_to=/app` starts an OpenID Connect authorization-code flow with PKCE and redirects to Authentik.
- `GET /api/v1/auth/callback` validates the login transaction, exchanges the authorization code, persists the customer User Account profile, creates an HTTP-only application session, and redirects to the validated local return path.
- `GET /api/v1/auth/session` returns the authenticated customer User Account profile or `401`.
- `PATCH /api/v1/auth/profile/locale` changes the authenticated user's `en` or `fi` interface locale.
- `POST /api/v1/auth/logout` revokes the local session and redirects through Authentik logout.

Health and identity-provider redirects are public. Customer application APIs require the Shadow session cookie and reject missing, revoked, or expired sessions.

`GET /api/v1/system/status` is part of the authenticated application shell and
therefore also requires a valid customer session.

## Organization signup and activation

- `POST /api/v1/organization-signups` creates a Pending Activation Organization
  for the authenticated customer and returns its identifier, expiry time, and
  Stripe-hosted Checkout URL.
- `GET /api/v1/organization-signups/{organization_id}` lets the initiating
  customer inspect the signup status. Once active, the representation includes
  the initial Owner membership.
- `POST /api/v1/billing/stripe/webhook` accepts Stripe events. The raw request
  signature is verified before processing; only a paid Checkout event matching
  the pending Organization and Checkout Session may activate it.
- The signup request carries `accepted_documents: [{document_key, version, locale?}]`. It must name every published
  `required` legal document (today `terms` and `dpa`) at its current version; otherwise the answer is 422 with
  `detail: {reason: "legal_acceptance_required", required: [{document_key, version}]}` and nothing is created. The
  acceptances are written in the same transaction as the pending Organization. While no required document is
  published, the field may be left out.

The browser return from Checkout is informational only. Pending signups expire
after 24 hours and never grant Organization membership or tenant access.

Add new endpoint contracts here before implementing non-trivial API behavior.

## Legal documents (ADR-0041)

Public, no sign-in, `Cache-Control: public, max-age=300` (the edge may override it).

- `GET /api/v1/legal/documents?locale=fi|en` (default `en`) lists `{key, title, version, effective_from, status, acceptance}`
  in the fixed key order. Draft documents appear only when `LEGAL_SHOW_DRAFTS` is true **and** the request carries a live customer session (the alpha's people); anonymous readers get the published texts only. A response that may contain drafts is `private, no-store`; the others are `public, max-age=300` with `Vary: Cookie`.
- `GET /api/v1/legal/documents/{key}?locale=` returns the same fields plus `body` (Markdown). Unknown keys, and drafts
  while drafts are hidden, answer 404; an unsupported locale answers 422.

Owner routes (an Admin or Member gets 403, another Organization's Owner 404):

- `GET /api/v1/organizations/{id}/legal?locale=fi|en` returns `{documents: [{key, title, acceptance, current_version,
  effective_from, accepted_version, accepted_at, accepted_by_name, accepted_by_former_member, state}]}` for the
  published documents; `state` is `accepted`, `acceptance_due`, or `not_required`.
- `POST /api/v1/organizations/{id}/legal/acceptances` `{document_key, version, locale?}` records the acceptance of the
  current published `required` version and returns that document's row. Another version is 409
  (`legal_version_not_current`), a document that is not a published `required` one is 404, repeating the request is
  harmless. Audited as `organization.legal_accepted`.

## Concurrency

- Mutable resources carry a monotonically increasing version.
- Update and delete requests include the version the client loaded.
- A write with a stale version is rejected with a conflict response.
- Conflict responses never overwrite the newer stored value.
- The frontend fetches the latest representation and asks the user to review and retry.

Real-time collaborative editing and WebSocket synchronization are outside the first release.

## Organization context

- `GET /api/v1/organizations` returns the authenticated customer’s active
  Organization memberships. It carries user context only and does not select a
  tenant.
- `GET /api/v1/organizations/{organization_id}` verifies membership, establishes
  that Organization as trusted PostgreSQL context for the request transaction,
  and returns the Organization's models (`id`, `name`, `version`).
- `GET /api/v1/organizations/{organization_id}/models/{model_id}` returns one model only when both identifiers belong to the same authorized Organization.
- Tenant API routes include the Organization identifier explicitly under `/api/v1/organizations/{organization_id}/`.
- The backend verifies the authenticated User Account's membership before establishing database RLS context.
- Organization context is never accepted from an unsigned client claim or mutable server-side "active Organization" session value.
- Resource identifiers are still checked against the route Organization even when they are globally unique.

## Organization Seat capacity

- `GET /api/v1/organizations/{organization_id}/billing/seats` returns the
  Owner-only purchased, occupied, reserved, and currently available seat
  projection, its version, and any open capacity change.
- `POST /api/v1/organizations/{organization_id}/billing/seats/increase-preview`
  asks Stripe for the proration that would result from an increased quantity.
  It stores a single-use, 30-minute confirmation record bound to the
  Organization, seat version, target, amount, and Stripe proration timestamp.
  It does not alter capacity.
- `POST /api/v1/organizations/{organization_id}/billing/seats` requests a new
  quantity with the version the Owner loaded. An increase requires both the
  preview identifier and explicit confirmation; it remains pending until a
  verified Stripe event confirms payment. A valid decrease remains at the
  current capacity until Stripe applies its schedule at renewal.
- A quantity below occupied memberships plus reserved Invitations is rejected.
  One open capacity change is allowed per Organization. A scheduled decrease
  also reserves its lower future ceiling immediately, so no later membership
  or Invitation can make the renewal target invalid.
- Verified, correlated Stripe events are the only way to apply a requested
  quantity. Duplicate events and events for completed or failed changes do not
  alter the projection.

## Subscription and billing portal

- `GET /api/v1/organizations/{organization_id}` includes `subscription` with
  `state` (`active`, `grace`, `read_only`), `writable`, `grace_expires_at`,
  `cancel_at_period_end`, and `current_period_end` for every member.
- `POST /api/v1/organizations/{organization_id}/billing/portal` returns the
  URL of Stripe's hosted Customer Portal. Owners only; it works while the
  Organization is read-only and is audited.
- `POST /billing/cancel` (`{reason?: "too_expensive" | "not_needed" |
  "switching" | "other"}`) and `POST /billing/cancel/undo` schedule or undo the end of the subscription at the end of the
  paid period. Owners only, on an active Organization; also during grace.
  They answer the new subscription view plus `released_seat_decrease`, 409
  when the subscription has ended, the cancellation is already scheduled, or
  none is scheduled, and 502 when Stripe fails (nothing changes locally).
  Each is audited (`organization.subscription_cancel_scheduled` with the
  reason key and `..._cancel_undone`) and tells the other Owners and Admins.
- `subscription` also has `ended`, true when the subscription has ended.
  `POST /billing/resubscribe` (`{seats}`) returns `{url}` of
  a Stripe Checkout for the existing customer. Owners only, only when the
  subscription has ended (409 otherwise); `seats` must cover the members plus
  reserved invitations (422 `too_few_seats` with `minimum`). Audited as
  `organization.resubscribe_started`; the payment is confirmed by the webhook.
- `GET` and `PUT /billing/contact` (`{billing_name, billing_email}`,
  ): Owners only, on an active Organization. `PUT` updates Stripe's
  customer first (502 and no local change when it fails), then the Organization,
  writes `organization.billing_contact_changed` with the changed field names
  only, queues a notice (outbox topic `billing.contact_changed`) to the **old**
  address with the new one masked (`b***@e***.com`) when the email changed, and
  notifies the other Owners and Admins. An unchanged contact does nothing. At
  most `LIMIT_BILLING_CONTACT_CHANGES_PER_DAY` (5) changes per Organization in
  24 hours, counted from the Audit Log (429 with `Retry-After`); 422 for a blank
  name or an address that is not shaped like one.
- `GET /billing/next-charge` and `GET /billing/invoices` (Owners only, on an
  active Organization) show Stripe's data without storing it. `next-charge`
  answers `{status, charge_date, amount, currency, seats}`: `scheduled` carries
  Stripe's previewed next regular invoice (total with tax, minor units);
  `none_cancelled` (cancellation scheduled) and `none_ended` (no subscription)
  never call Stripe; `unavailable` is a Stripe failure, answered with 200 so the
  page degrades. `invoices` answers `{status: "ok" | "unavailable", invoices}`
  with at most 12 entries of the Organization's Stripe customer, newest first:
  `{id, date, amount, currency, state, reason, hosted_invoice_url}` (`state`
  `paid`, `open`, `failed`, `void`, `uncollectible`; `reason` `renewal`,
  `seat_increase`, `signup`, `other`; drafts are skipped and only `https://`
  links pass). Admins and Members get 403, other Organizations' Owners 404.
- While `writable` is false, customer mutations return `403` and reads keep
  working.

## Organization Invitations

- `POST /api/v1/organizations/{organization_id}/invitations` lets an Owner or
  Admin invite a person as a Member (`member`, the default) or an
  Admin when one unreserved purchased seat exists; only an Owner can create an
  Owner Invitation. Models are open to every member of the Organization.
  It creates the Invitation, reservation, audit record, and email outbox record
  in one transaction.
- `POST /api/v1/organizations/{organization_id}/invitations/{invitation_id}/resend`
  supersedes a pending Invitation and sends a new single-use seven-day link
  without consuming another seat. `DELETE` revokes a pending Invitation and
  releases its reservation.
- `POST /api/v1/invitations/accept` requires an authenticated customer whose
  verified account email matches the Invitation. Acceptance creates one
  membership, converts the reservation to occupied capacity, and consumes the
  Invitation atomically.
- **Bulk invitations:** `POST /api/v1/organizations/{organization_id}/invitations/bulk`
  takes `{emails: [..≤50], role, group_ids, dry_run}` (`dry_run` defaults to
  `true`).
  - The response is `{invite, skipped: [{email, reason}], seats_needed,
    created}`. `reason` is `invalid`, `duplicate`, `member`, or `invited`.
  - A real run that needs seats returns `409 {reason: "seats_needed",
    seats_needed}` and sends nothing.
  - Otherwise each address goes through the single-invitation flow
    (reservation, audit, email).

## Organization membership administration

- `GET /api/v1/organizations/{organization_id}/memberships` lists current
  memberships with each person's email and display name. Only Owners and
  Admins may list; a Member receives `403`.
- `PATCH /api/v1/organizations/{organization_id}/memberships/{membership_id}`
  changes a role with `expected_version`. Only Owners and Admins may change
  roles. Admins manage Member and Admin roles, including other Admins; only
  Owners grant, change, or remove the Owner role. The final Owner cannot be
  demoted.
- `DELETE /api/v1/organizations/{organization_id}/memberships/{membership_id}`
  removes a membership. Any Organization User may
  remove their own membership (leave); removing someone else requires Owner or
  Admin, and an Admin cannot remove an Owner. An Organization must retain at
  least one Owner.
- `POST .../memberships/{membership_id}/transfer-ownership` takes `{expected_version, keep_owner}`: an Owner makes an active
  Admin or Member (never themselves) an Owner and, unless `keep_owner`, becomes
  an Admin, in one transaction. 403 for a caller who is not an Owner or while the
  Organization is read-only, 409 with `latest_version` for a stale target, 422
  for a target who cannot receive ownership. Audit
  `organization.ownership_transferred` (`kept_owner`); the person and the other
  Owners are notified through the role notices of P8.
- `POST .../memberships/{membership_id}/leave` (`{successor_membership_id?}`)
  lets a member leave for themselves (403 for another's membership). The only
  Owner must name a successor, who becomes an Owner in the same transaction
  (409 `successor_required`); with nobody else the answer is 409 `last_member`.
  A refused attempt changes nothing.

## Models, graph, and metamodel (ADR-0043)

All routes sit under `/api/v1/organizations/{organization_id}/models`. Reading
needs any membership; writing needs a member session and is blocked while the
Organization is read-only. Writes that change a version take
`expected_version` and answer 409 `{"latest_version": n}` when stale (ADR-0018).
Every write is audited.

| Method and path | Purpose |
| --- | --- |
| `GET`, `POST` `/models` | List and create models; a new model gets the default metamodel and a base version |
| `GET`, `PATCH`, `DELETE` `/models/{model_id}` | Read (with types and rules; `?version_id=` picks the line of that version), rename, delete. The graph is the replayed state after the line's last event, with `latest_event` (`id`, `version`, `occurred_on`, `title`); nodes and connections carry no `version`. Until ticket 08 retires the route, prefer `GET .../lines/{line_id}/state` |
| `POST`, `PATCH`, `DELETE` `.../node-types[/{type_id}]` | Node types; deleting one that any event change names (or an old `nodes` row) answers 409 `in_use` |
| `POST`, `PATCH`, `DELETE` `.../connection-types[/{type_id}]` | Connection types; the same rule |
| `POST`, `DELETE` `.../allowed-connections` | Add or remove a rule allowing a connection type between two node types; removing one that some chain of the Model needs to replay (an event adds or re-routes a connection by it, in any line) answers 409 `in_use` |

The routes `POST`, `PATCH`, `DELETE` `.../nodes` and `.../connections` (version-based) were removed with the
model-timeline ticket 07; canvas edits are changes inside an event (below). The node-type, connection-type and
rule deletes lock the Model row like event writes, so an event cannot start using a type while it is deleted.

## Versions (ADR-0045)

| Method and path | Purpose |
| --- | --- |
| `GET`, `POST` `/models/{model_id}/versions` | List and fork a version from a base; a fork also creates the Scenario line of the same id (branching from the base line's last event) and copies the base line's metrics |
| `PATCH`, `DELETE` `.../versions/{version_id}` | Rename, delete; the line of the same id is renamed or deleted with it |

The change list (`GET .../versions/{id}/changes`) and merge (`POST .../versions/{id}/merge`) routes were removed with
ticket 07 of the model timeline: graphs live in events now (ADR-0048) and ADR-0050 replaces merge with adoption of
a Scenario. A fork starts from the base line's graph (it branches from its last event, so it copies no nodes);
ticket 08 retires the remaining version routes.

## Lines, events and state (model timeline; ADR-0048, ADR-0049)

Routes under `/models/{model_id}/lines` and `/models/{model_id}/events`. Reads are in
`backend/app/timeline_routes.py` (loading and the planned rule are in `backend/app/timeline/loader.py`) and
need any membership; they work while the Organization is read-only. Event writes are in
`backend/app/timeline_event_routes.py`. Another Organization, an unknown Model, line or event answers 404. A
line's id equals its former version id. Scenario and position writes are in `backend/app/timeline_line_routes.py`
(below); canvas edits are in `backend/app/timeline_edit_routes.py` (below); adoption arrives with ticket 08.

| Method and path | Purpose |
| --- | --- |
| `GET` `/lines` | Lines, Base first: `kind`, `parent_line_id`, `branch_event_id`, `start_changed_at`, `created_by_user_account_id`, `version`, `event_count`, `latest_event_date` (the state's `line` carries the same fields) |
| `GET` `.../lines/{line_id}/events` | The line's own events by date then entry order: `occurred_on`, `title`, `note`, `planned`, `change_count`, `change_counts` per operation, `branches` (Scenarios that branch from the event) |
| `GET` `.../lines/{line_id}/state` | The graph after `?event_id=` (an event of that line) or on `?as_of=YYYY-MM-DD` (the last event dated that day or earlier); with neither, the present state (`as_of` = today). Both together answer 422 `event_id_and_as_of` |
| `GET` `/events/{event_id}` | One event with its ordered `changes` (`position`, `op`, `element_id`, `payload`) |
| `POST` `/lines/{line_id}/events` | Add an event: `occurred_on`, `title`, `note`, `changes[]` (`op`, `element_id`, `payload`); answers 201 with the event and its changes |
| `PATCH` `/events/{event_id}` | Change `title`, `note`, `occurred_on`, or replace `changes`; only the fields sent change; `expected_version` required; a patch that changes nothing answers 200 without a new version |
| `DELETE` `/events/{event_id}?expected_version=` | Delete an event; answers 204 |
| `POST` `/lines` | Create a Scenario (see below) |
| `PATCH` `/lines/{line_id}` | Rename and set the description (see below) |
| `DELETE` `/lines/{line_id}` | Delete a Scenario (see below) |
| `POST` `/lines/{line_id}/acknowledge-start` | Clear `start_changed_at` |
| `PUT` `/lines/{line_id}/positions` | Write node positions for one line |

The state answers the graph in the shape of `GET /models/{model_id}` (`nodes`, `connections`, `node_types`,
`connection_types`, `allowed_connections`; nodes carry no `version`) plus `line`, `event` (null before the
line's first event), `as_of`, `planned`, `positions` (`node_id`, `x`, `y`: the line's own position, else the
nearest ancestor line's, else the position the node was added with; node `x` and `y` already hold the
resolved position), and, for the shown event, `added`, `updated` (with `previous`) and `removed` lists of
`nodes` and `connections` (removed ones keep their data and last drawn position). `planned` is true when
the shown event is dated after today in the Organization's time zone; the present state ignores such events,
but a planned event's own state can be read by `event_id`. A chain that cannot be replayed answers 422
`chain_broken` with `line_id`, `event_id`, `position`, `cause`, `element`.

### Writing events (ADR-0049)

A change is `{op, element_id, payload}`; `payload` is validated by the Pydantic payloads in
`backend/app/timeline/payloads.py` (`add_node`: `node_type_id`, `name`, `description`, `x`, `y`; `remove_node`: none;
`update_node`: any of `name`, `description`, `node_type_id`; `add_connection`: `connection_type_id`,
`source_node_id`, `target_node_id`; `remove_connection`: none; `reroute_connection`: `source_node_id` and/or
`target_node_id`; `change_connection_type`: `connection_type_id`). `element_id` names the node or connection; an
`add_node` or `add_connection` may leave it out and the server generates one (a client that wants a later change
in the same event to refer to it supplies its own). Changes are stored in the order sent, numbered
`position` 0..n-1; a bad shape answers the usual 422 validation list. Titles are trimmed (at most 200 characters).
A node added by a change gets a drawn position on the line (from `x`, `y`) unless the line already has one for it;
deleting or rewriting the event that added a node drops that position when no event adds the node any more.

Every write locks the Model row (`SELECT ... FOR UPDATE`), loads the whole timeline, applies the change in memory
and replays the changed line and every Scenario that branches from it, directly or through other Scenarios
(`backend/app/timeline/validate.py`). Nothing is saved unless every replay is valid.

| Answer | When |
| --- | --- |
| 403 | A Member writes the Base line (Owners and Admins write it; any Member writes a Scenario), or the Organization is read-only |
| 404 | Unknown Model, line or event, or another Organization's |
| 409 `{latest_version}` | `expected_version` is stale |
| 409 `{reason: "branch_point", line, line_id, lines}` | The event to delete is the branch point of another line; `line` is that Scenario's name. Checked before the chain |
| 409 `{reason: "limit_reached", limit: "events_per_line", maximum}` | The line holds `LIMIT_EVENTS_PER_LINE` events (create only) |
| 422 `{reason: "chain_broken", event, line, position, element, cause, hint}` | Some chain would not replay |

`chain_broken` carries ids for the machine (`event` is the event that fails, which may be in another line;
`line` the line it is in; `position` the change number, null for the date rule; `element` the node, connection or
type id) and `cause`, one of `missing_element`, `duplicate_element`, `missing_type`, `connection_not_allowed`,
`missing_endpoint`, `self_connection`, `duplicate_connection`, `missing_branch_event`, `before_branch_event`. `hint`
is structured data for the interface to word in Finnish and English, never prose: `code` (what to do first:
`add_element_before`, `remove_duplicate_add`, `choose_existing_type`, `choose_allowed_connection`, `add_endpoint_before`,
`choose_different_ends`, `remove_duplicate_connection`, `restore_branch_event`, `move_after_branch_event`), `event_title`,
`event_date`, `op`, `line_name`, `line_kind`, `scenario_name` (set when the failing line is a Scenario),
`in_other_line` (true when the failing event is not in the line that was written), `element_kind`, `element_name`
(where known), `type_name`, `source_name`, `target_name`, `branch_event_title` and `branch_event_date`.

After a successful write, each Scenario below the changed line whose starting point changed (an event inserted,
removed or moved before its branch point, or the content of one of those events replaced) gets
`start_changed_at` set. Audit actions `event.created`, `event.updated` and `event.deleted` hold ids, the event
date and change counts per operation, never names, titles or notes (`audit.md`).

### Canvas edits inside an event (ADR-0049)

| Method and path | Purpose |
| --- | --- |
| `POST` `/events/{event_id}/nodes` | `node_type_id`, `name`, `description?`, `x`, `y`, `expected_version?`; answers 201 `{id, event, node}` (`id` is the generated element id) |
| `PATCH` `/events/{event_id}/nodes/{node_id}` | `name`, `description` (null clears), `node_type_id` (only the fields sent change), `expected_version`; answers `{id, event, node}` |
| `DELETE` `/events/{event_id}/nodes/{node_id}?expected_version=` | Remove the node (its connections go with it); 204 |
| `POST` `/events/{event_id}/connections` | `connection_type_id`, `source_node_id`, `target_node_id`, `expected_version?`; 201 `{id, event, connection}` |
| `PATCH` `/events/{event_id}/connections/{connection_id}` | Re-type and/or re-route (`connection_type_id`, `source_node_id`, `target_node_id`), `expected_version`; `{id, event, connection}` |
| `DELETE` `/events/{event_id}/connections/{connection_id}?expected_version=` | Remove the connection; 204 |

The event is the one whose state the person is looking at: any event of a line they may write, not only the last. Each
edit is appended to the event's changes, the list is tidied (`backend/app/timeline/compact.py`: an element added and
removed in the same event leaves no change, nor do its connections and renames; renames, re-routes and type changes
merge into the add or the earlier change of the same element; a change that leaves the state as it was is dropped),
the whole chain is replayed as for any event write, and the event's changes are rewritten and renumbered. The `event`
in the answer is the saved event with its changes and new `version`; an edit that changes nothing writes nothing and
leaves the version alone. `expected_version` is the event's `version` (409 `{latest_version}` when stale); a create may
leave it out, a change and a delete need it. The node or connection must exist in the state after the event (404
otherwise). Roles, read-only Organization, 404 and 422 `chain_broken` as for event writes (the 422 also covers what a
single edit gets wrong: `duplicate_connection`, `connection_not_allowed`, `self_connection`, `missing_endpoint`,
`missing_type`); on a refusal the event is unchanged. Re-typing and re-routing a connection in one PATCH is tried in
both orders; a pair that is allowed only together is refused with `connection_not_allowed` (remove the connection and add
a new one). A node created here also gets the position `x`, `y` on the line (a Scenario's own line for a Scenario's
event). Moving nodes stays `PUT .../positions`. The audit entry is `event.updated` with `fields: ["changes"]`, the new
and `previous_change_counts` per operation, and no names.

### Scenarios and positions (ADR-0048)

`POST /lines` takes `name` (trimmed, at most 120, unique per Model ignoring case, the Base line's name counts),
`description` (optional) and `branch_event_id`: any event of any line of the Model, so a Scenario of a Scenario
works to any depth. The parent line is the line that holds the event. The Scenario starts from the parent's state
after that event, and gets a copy of the parent's metrics and stored values as they are now (a metric keeps its
`node_id` only while that node exists in the state at the branch point); afterwards the lines are independent.
Answers 201 with the line. Any Member may create a Scenario. The Model row is locked while it is created.

`PATCH /lines/{line_id}` takes `name`, `description` (replaced; null clears it) and `expected_version`; a patch that
changes nothing answers 200 without a new version. `DELETE /lines/{line_id}` answers 204 and takes the line's events,
changes, positions, metrics, values and simulations with it (optional `?expected_version=`). Rename and delete: the
Base line needs an Owner or Admin (the Base line cannot be deleted); a Scenario needs its creator, an Owner or an
Admin. `POST .../acknowledge-start` clears `start_changed_at` for anyone who may write the line (Base line Owner or
Admin, a Scenario any Member) and answers the line without a new version.

`PUT /lines/{line_id}/positions` takes `[{node_id, x, y}]` (at most 5000, finite numbers; a node named twice takes its
last entry) and upserts the line's own positions, all or nothing; answers the positions written. Moving nodes is part
of drawing, so it follows the line's write rule (Base line Owner or Admin; Scenario any Member). It writes no event,
no audit entry and no version. A node must exist in the line's state at its latest event (including planned ones).
The state read resolves a position as the line's own, else the nearest ancestor's, else the position the node was
added with.

| Answer | When |
| --- | --- |
| 403 | A role is not enough (see above), or the Organization is read-only |
| 404 | Unknown Model, line or branch event, or another Organization's (also an event of another Model) |
| 409 `{reason: "duplicate_name"}` | Another line of the Model has the name (create, rename) |
| 409 `{latest_version}` | `expected_version` is stale |
| 409 `{reason: "limit_reached", limit: "lines_per_model", maximum}` | The Model holds `LIMIT_LINES_PER_MODEL` lines (create only) |
| 409 `{reason: "has_children", children}` | Scenarios branch from the line (delete); the count only, no names |
| 422 `{reason: "base_line"}` | Delete of the Base line |
| 422 `{reason: "unknown_node", node_ids}` | A position names a node the line does not have |

Audit actions `line.created` (`model_id`, `line_id`, `parent_line_id`, `branch_event_id`), `line.renamed` (ids and
the `fields` changed) and `line.deleted` (ids, `parent_line_id`, `event_count`) never hold names or descriptions
(`audit.md`). Until ticket 08 retires the version routes, renaming or deleting a Scenario that came from a fork also
updates or removes its old version row so both route families agree.

## Metrics

Under `/models/{model_id}/lines/{line_id}/metrics` (a line is the Base line or a Scenario; until ticket 09 the web
application passes the id of the selected version, which is also the id of its line). Keys, formulas and derived
metrics are scoped to one line; an unknown line, or one of another Model, answers 404. A metric's `node_id` is a
node's element id (migration 0063 dropped the foreign key to the old `nodes` table); creating or changing a metric
accepts a node of the line's current state (after its last event), otherwise 422, and a metric that already has a node
keeps it when saved unchanged even if a later event removed the node.

| Method and path | Purpose |
| --- | --- |
| `GET`, `POST` `/metrics` | List and create metrics; a metric is either entered or derived from a formula |
| `PATCH`, `DELETE` `/metrics/{metric_id}` | Change or delete; formulas are validated and cycles rejected |
| `GET` `/metrics/{metric_id}/series` | Monthly values, evaluated for derived metrics |
| `PUT` `/metrics/{metric_id}/values` | Set monthly values of an entered metric |
| `POST` `/metrics/import?filename=` | Import values from a CSV or XLSX request body (see below) |
| `GET` `/metrics/export?format=csv\|xlsx` | Export the metric series |

### Import and export

`POST .../metrics/import` takes the file as the raw request body (no
multipart), with the name in `filename` so the type is known. CSV delimiters
`; , tab` are detected and decimal commas read. Both layouts work: wide (one
row per month, one column per metric) and long (`metric`, `period`, `value`).
Unknown and derived metrics and unreadable cells are reported and skipped;
empty cells are ignored. Exported cells that begin with a formula character are
prefixed with `'`.

## Simulations and forecasts (ADR-0042)

Under `.../lines/{line_id}/simulations` (the response field is `line_id`): `GET`, `POST` list and run a
simulation (method `linear`, `seasonal`, `holt`, or `prophet`; a minimum
history applies per method, 12 months for Prophet and 24 for seasonal), `GET`
and `DELETE` `/{simulation_id}` read with history, forecast, and bands, or
delete.

## Analysis (ADR-0044, ADR-0047)

Under `.../models/{model_id}/simulations/{simulation_id}/analysis`.

| Method and path | Purpose |
| --- | --- |
| `GET` | Findings, proposals, and the agent- or person-written `summary`, `summary_at`, `summary_author` (`agent:<client>` when written through MCP) |
| `POST` | Generate rule-based findings and proposals; decided proposals persist |
| `PUT` `/summary` | Set the summary `{text}` (1–4000 characters); audit `analysis.summary_set` without the text |
| `PUT` `/proposals/{metric_key}` | Create or replace the one `agent` proposal of a metric `{title, rationale, severity}`; a replaced proposal goes back to `proposed`; audit `analysis.proposal_set`. Rule regeneration never touches `agent` proposals |
| `GET` `/export` | Excel workbook with Summary, Findings, Proposals, and Forecast sheets |
| `PATCH` `.../recommendations/{recommendation_id}` | Accept or dismiss a proposal |

## Audit activity

- `GET /api/v1/organizations/{organization_id}/audit-events?action=&prefix=&offset=&limit=`
  returns Audit Events newest first for Owners and Admins (Members `403`).
  `action` filters one action, `prefix` one area such as `event` or
  `support_access`. Each item carries `actor` (email, or "Platform support"
  for a Support Agent), `support_access_id`, `action`, `target_type`,
  `target_id`, `occurred_at`, and `change_summary`. `limit` defaults to 50 and
  is capped at 100; `next_offset` is `null` on the last page. No endpoint
  mutates Audit Events.
- `GET /api/v1/organizations/{organization_id}/mcp-calls?outcome=&kind=&offset=&limit=`
  returns the agent calls of the Organization (ADR-0047), newest first, for Owners and
  Admins only (Members `403`). Each item has `person` (email), `mcp_client`, `tool`,
  `kind` (`read` or `write`), `outcome` (`ok`, `refused`, `error`), a short `reason` code and
  `duration_ms`; never arguments or results.

## Notifications

All under `/api/v1/organizations/{organization_id}`; any member of the
Organization may call them and only ever sees their own rows (row-level
security checks the recipient as well as the Organization). Support Access has
no route.

- `GET /notifications?cursor=&unread=` returns `{items: [{id, type, params,
  created_at, read_at}], next_cursor}`, newest first, 20 a page. The API sends
  the type and parameters; the interface builds the text in the reader's
  language. Types: `role_changed` (`from_role`, `to_role`), `invitation_accepted` (`name`, `role`), and `ownership_changed` (`name`, `owner`).
- `GET /notifications/unread-count` returns `{unread}`; the bell polls it
  every minute while the tab is visible.
- `POST /notifications/{id}/read` (204; 404 for someone else's) and
  `POST /notifications/read-all` (`{updated}`).
- `GET /notification-settings` returns `{items: [{key, audience, in_app,
  email}]}` for the caller's own settings (keys: `role_changed`, `invitation_accepted`, `ownership_changed`,
  and for Owners and Admins `support_access`, `billing`, `deletion`);
  `PUT /notification-settings` takes `{settings: {key: {in_app, email}}}` and
  422s on a key the caller may not set.
- Email: a notification whose key has the email switch on (defaults: only
  `access_removed` and the Organization notices) adds an outbox message
  (topic `notification`) in the same transaction, in the recipient's language,
  up to `LIMIT_NOTIFICATION_EMAILS_PER_DAY` (10) per recipient in 24 hours.
  Owner/Admin types: `support_access_requested`, `support_access_ended`,
  `billing_problem`, `deletion_scheduled`.
- A notification is written in the transaction of its cause (`app/notifications.py`) and never holds model content.

## Cross-cutting rules

- Creating content beyond an operational ceiling returns `409` with
  `{"detail": {"reason": "limit_reached", "limit": ..., "maximum": ...}}`
  (`docs/architecture/operational-limits.md`).
- A state-changing request with an `Origin` header that is not a trusted
  frontend origin (`FRONTEND_ORIGINS`) or the API's own origin returns `403`.
  The Stripe webhook is exempt.

## Organization deletion

- Owner only. `GET /api/v1/organizations/{organization_id}/deletion`
  returns `status`, `deletion_requested_at`, and `purge_after`.
- `POST .../deletion` with `{"confirm": true}` moves an active Organization
  (also a read-only one) to Pending Deletion, audits
  `organization.deletion_requested`, and returns the same body. Any other
  status returns `409`.
- `POST .../deletion/restore` returns it to Active before `purge_after`
  (`organization.deletion_restored`); afterwards it returns `409`. Restore
  leaves the subscription state as Stripe last reported it.
- While Pending Deletion, the workspace returns `404`, content and membership
  routes are refused, and mutations return `409`. `GET /api/v1/organizations`
  still lists the Organization to its Owners with `status:
  "pending_deletion"` and `purge_after`.

## Platform API

- Platform endpoints live under `/api/v1/platform/` and accept only Platform
  User sessions; customer sessions receive `403`, and Platform User sessions
  receive `403` from every customer route.
- `GET /api/v1/auth/login?audience=platform` starts a platform sign-in and
  returns to `/platform`. `GET /api/v1/platform/session` returns the account
  and its roles; `POST /api/v1/platform/logout` ends the session.
- `GET /api/v1/platform/organizations` (Platform Admin) lists each
  Organization's status, subscription view, seats, member and model
  counts, and deletion request time, without content.
- `GET /api/v1/platform/health` (Platform Admin or Support Agent) returns
  outbox and background-job counts by status, Stripe webhook outcomes, and
  Organization counts by status.
- `GET /api/v1/platform/jobs?status=failed` lists outbox messages and
  background jobs with type, Organization, attempts, next attempt, and a
  truncated error summary, never payloads.
- `POST /api/v1/platform/jobs/{email|job}/{id}/replay` (Platform Admin)
  returns a failed item to the queue with zero attempts and audits
  `platform.job_replayed` in its Organization; replaying any other state
  changes nothing.
- Platform endpoints accept only Platform Users.
- Customer Organization context is absent unless a Support Agent presents an active approved Support Access grant.
- Platform Admin authority alone never enables customer-content endpoints.

### Support Access (ADR-0020)

- Support Agents work under `/api/v1/platform/support-access` (Support Agent
  role required):
  - `POST` with `organization_id`, `case_reference`, `scope` (`read` default or
    `write`), and `hours` (1–24) creates a `pending` request for an active
    Organization.
  - `GET` lists the agent's own requests.
  - Support Access currently grants no content routes: the approved request is recorded and audited, and the Shadow content routes will be scoped to it when support tooling for models is added.
  - Any other state (pending, rejected, revoked, expired, or an Organization
    that is not active) returns `403`; another agent's grant returns `404`.
- Customer Owners and Admins decide under
  `/api/v1/organizations/{organization_id}/support-access`: `GET` lists
  requests; `POST /{request_id}/approve` accepts an optional `{"hours": n}`
  that may shorten, but never extend, the requested duration;
  `POST /{request_id}/reject` and `POST /{request_id}/revoke` end a pending or
  an active grant. Members receive `403`.
- A support request runs with `app.current_support_access_id` set, and every
  audit event it writes carries `support_access_id`. Expired grants become
  `expired` (audited once) when next listed or used, and within a minute
  through the worker sweep.

## MCP interface (ADR-0037, ADR-0038)

An agent the person chooses reads and changes models through the Model Context
Protocol. The endpoint is off unless `MCP_ENABLED=true`.

- `POST /api/mcp` is the Streamable HTTP endpoint (stateless, JSON responses). It
  needs `Authorization: Bearer <access token>` from the dedicated Authentik provider;
  without a valid token it answers `401` with a `WWW-Authenticate` header that points
  at the metadata below.
- `GET /.well-known/oauth-protected-resource/api/mcp` is the OAuth Protected Resource
  Metadata (RFC 9728): the resource address and the authorization server (the MCP
  provider's issuer). Caddy forwards `/.well-known/oauth-protected-resource*` to the
  API.
- The token must be a JWT signed by the MCP provider whose `iss` is `MCP_OIDC_ISSUER`
  and whose `aud` is `MCP_OIDC_CLIENT_ID`. Tokens of the web provider, of any other
  client, expired tokens, and badly signed tokens are refused. The `sub` claim must
  belong to an existing customer User Account; MCP never creates an account.
- Tools (every Organization-scoped tool takes `organization_id`):
  - Organizations: `list_organizations`, `get_organization`.
  - Reads: `list_models`, `get_model` (nodes, connections, metamodel and `latest_event`, the event `create_node` and `create_connection` write into),
    `list_metrics`, `get_metric_series`, `list_simulations`, `get_simulation` (these four take `line_id`), `get_analysis`.
  - Writes: `create_model`, `create_node` and `create_connection` (these two take `event_id`, as changes inside that event,
    and an optional `expected_version` of the event), `create_version`,
    `create_metric`, `set_metric_values`, `run_simulation` (these three take `line_id`), `generate_analysis`,
    `set_analysis_summary`, `add_proposal` (the agent's own analysis, ADR-0047). `get_version_changes` and
    `merge_version` were removed with ticket 07 of the model timeline.
  - There are no delete tools; Shadow itself calls no model (ADR-0047); metamodel editing, import, and
    export stay in the web application (ADR-0046).
  Tools call the same endpoint functions as the REST API, so roles, `expected_version`,
  the read-only state, and audit are identical. Writes are saved at once and carry the MCP
  tool annotations (`readOnlyHint`, `destructiveHint`) so the client can ask the person
  first. Results that contain stored text include a notice that the text is data.
- A tool call fails with a readable error when the Organization's `mcp_enabled` switch is
  off or its `mcp_platform_blocked` flag is set, before any content is read.
- Every audit entry written during an MCP call carries `source: "mcp"` and
  `mcp_client` (the client id).
- Every tool call, read or write, ok, refused or failed, also leaves one content-free
  `mcp_calls` row naming the person the agent acted for and the agent program (ADR-0047),
  written in its own transaction after the call. A write call, a refusal or a failure fails
  when the row cannot be written; a successful read returns its result and logs the fault.
  `list_organizations` (no Organization) is not stored. Successful reads are deleted after
  `MCP_READ_LOG_RETENTION_DAYS` (default 90) by the daily `mcp.read_log_cleanup` job.

Switch and connection details (Owners and Admins only; other members get `403`):

- `GET /api/v1/organizations/{organization_id}/mcp` returns `interface_available`,
  `enabled`, `platform_blocked`, `server_url`, `client_id`, and `secret_configured`;
  never the secret.
- `PATCH /api/v1/organizations/{organization_id}/mcp` with `{"enabled": bool}` turns
  agent access on or off; allowed in every subscription state. Audited as
  `mcp.enabled` or `mcp.disabled`.
- `POST /api/v1/organizations/{organization_id}/mcp/secret` returns the shared client
  secret and writes an `mcp.secret_revealed` audit entry.
- Platform Admins block or unblock one Organization with
  `PATCH /api/v1/platform/organizations/{organization_id}/mcp-block`
  (`{"blocked": bool}`, audited as `platform.mcp_blocked` or `platform.mcp_unblocked`);
  the Organization cannot lift the block. Support Agents get `403`.
