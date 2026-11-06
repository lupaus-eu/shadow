# API

## Health

`GET /health` on the backend (host port 8100 locally). It is not routed
through Caddy, which forwards `/api/*` unchanged to the backend and every other
path to the frontend.

Response:

```json
{
  "status": "ok",
  "service": "Yearclock"
}
```

## Authentication

- `GET /api/v1/auth/login?return_to=/app` starts an OpenID Connect authorization-code flow with PKCE and redirects to Authentik.
- `GET /api/v1/auth/callback` validates the login transaction, exchanges the authorization code, persists the customer User Account profile, creates an HTTP-only application session, and redirects to the validated local return path.
- `GET /api/v1/auth/session` returns the authenticated customer User Account profile or `401`.
- `PATCH /api/v1/auth/profile/locale` changes the authenticated user's `en` or `fi` interface locale.
- `POST /api/v1/auth/logout` revokes the local session and redirects through Authentik logout.

Health and identity-provider redirects are public. Customer application APIs require the Yearclock session cookie and reject missing, revoked, or expired sessions.

`GET /api/v1/system/status` is part of the authenticated application shell and
therefore also requires a valid customer session.

## Organization signup and activation

- `POST /api/v1/organization-signups` creates a Pending Activation Organization
  for the authenticated customer and returns its identifier, expiry time, and
  Stripe-hosted Checkout URL.
- `GET /api/v1/organization-signups/{organization_id}` lets the initiating
  customer inspect the signup status. Once active, the representation includes
  the initial Owner membership, blank localized Yearclock, and General Lane.
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
  and returns its accessible Yearclocks (with `version` and `access_role`)
  and their ordered Lanes (with `version`).
- `GET /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}`
  returns one Yearclock only when both identifiers belong to the same authorized
  Organization.
- The workspace response includes `recent_yearclock_ids`: up to five
  Yearclocks the user opened most recently and can still open, newest first.
- `POST /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/visit`
  records that the user opened the Yearclock. It needs access to that
  Yearclock (`404` otherwise) and also works while the Organization is
  read-only, because it is navigation. Since Yearclock V2 it returns `200
  {previous_visited_at}`, the Previous Visit (`null` on a first visit).
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
  "switching" | "other"}`) and `POST /billing/cancel/undo` (Yearclock V2 P14,
  ADR-0032) schedule or undo the end of the subscription at the end of the
  paid period. Owners only, on an active Organization; also during grace.
  They answer the new subscription view plus `released_seat_decrease`, 409
  when the subscription has ended, the cancellation is already scheduled, or
  none is scheduled, and 502 when Stripe fails (nothing changes locally).
  Each is audited (`organization.subscription_cancel_scheduled` with the
  reason key and `..._cancel_undone`) and tells the other Owners and Admins.
- `subscription` also has `ended`, true when the subscription has ended.
  `POST /billing/resubscribe` (`{seats}`, Yearclock V2 P14) returns `{url}` of
  a Stripe Checkout for the existing customer. Owners only, only when the
  subscription has ended (409 otherwise); `seats` must cover the members plus
  reserved invitations (422 `too_few_seats` with `minimum`). Audited as
  `organization.resubscribe_started`; the payment is confirmed by the webhook.
- `GET` and `PUT /billing/contact` (`{billing_name, billing_email}`, Yearclock
  V2 P14): Owners only, on an active Organization. `PUT` updates Stripe's
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
  Owner Invitation. Yearclock Editor and Viewer access is granted separately
  after acceptance (see *Yearclock structure and access*).
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
- **Invitation Groups (Yearclock V2):**
  - Invitations accept `group_ids`, which must be Groups of the Organization
    (`422` otherwise).
  - Acceptance joins the new membership to those Groups. Groups deleted in the
    meantime have cascaded away and are skipped.
  - A resend carries the Groups over, and the creation audit lists them.
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
  removes a membership and its Yearclock grants. Any Organization User may
  remove their own membership (leave); removing someone else requires Owner or
  Admin, and an Admin cannot remove an Owner. An Organization must retain at
  least one Owner.
- `POST .../memberships/{membership_id}/transfer-ownership` (Yearclock V2 P14,
  ADR-0032) takes `{expected_version, keep_owner}`: an Owner makes an active
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

## Yearclock structure and access

- `GET` and `POST /api/v1/organizations/{organization_id}/yearclocks` list and
  create Yearclocks. `PATCH .../yearclocks/{yearclock_id}` renames one with
  `expected_version`.
  `DELETE .../yearclocks/{yearclock_id}?expected_version=` recoverably deletes
  a Yearclock with all its content; `POST .../recover?expected_version=`
  brings it back. A deleted Yearclock is absent from the workspace and every
  content route returns `404`; `GET .../yearclocks?include_deleted=true`
  lists it with `deleted_at` and `purge_after`. `PUT .../yearclocks/order`
  reorders the active ones with
  `ordered_ids` and `expected_versions` (one version per Yearclock) and
  rejects any stale version with `409`;
  `POST .../archive` and `POST .../restore` archive and unarchive one. These
  mutations require Owner or Admin.
- `POST .../yearclocks/{yearclock_id}/lanes`, `PATCH .../lanes/{lane_id}`, and
  `PUT .../lanes/order` create, rename, and reorder Lanes and require editor
  access.
- `DELETE .../lanes/{lane_id}?expected_version=` removes an empty Lane. It
  returns `409` with `{"reason": "last_lane"}` for a Yearclock's only Lane, or
  `{"reason": "lane_has_events", "events": n, "series": m}` while any Event
  (including recoverably deleted ones) or Series still uses it.
- `POST .../lanes/{lane_id}/move-events` with `target_lane_id` and the Lane's
  `expected_version` is the explicit flow that moves every Event and Series to
  another Lane of the same Yearclock. Both operations are audited.
- `POST .../lanes/copy` with `{source_lane_id, include_events}` (Yearclock V2)
  copies a Lane into this Yearclock. The source may be any Lane of a Yearclock
  that the caller may read (`app/yearclock_reading.py`), including this one;
  otherwise `404`.
  - The copy takes the name, tint, and height, and optionally the non-deleted
    single Events with their Labels and the Series with their rules and
    Labels, re-materialized. Occurrence exceptions and skips are not copied.
  - Organization Categories carry over. Other Yearclocks' Categories are
    matched by case-insensitive name in the target, and missing ones are
    created.
  - The Lane, Category, Event, and Series ceilings are checked for the whole
    copy first (`409 limit_reached`, nothing written).
  - The copy is independent afterwards and is audited once as `lane.copied`.
  - The response is `{lane, events, series, categories_created}`.
- `POST .../lanes/link` with `{source_lane_id}` (Yearclock V2) adds a Linked
  Lane.
  - The source must be an own Lane of another Yearclock that the caller may
    read (`404` otherwise).
  - Refusals: `422 same_yearclock` or `linked_source` (no chains), `409
    already_linked`, and `409 limit_reached` (`lanes_per_yearclock` counts
    Linked Lanes).
  - It is audited as `lane.linked` for the target and `lane.linked_elsewhere`
    for the source.
  - `DELETE .../lanes/{lane_id}` removes a link without the empty-Lane check
    (the last-Lane rule still applies). It is audited as `lane.unlinked` and
    `lane.unlinked_elsewhere`.
  - `PATCH` on a Linked Lane changes only its tint and height; the name
    stays the source's.
  - Copying a Linked Lane copies its Source Lane.
- Lane responses, including the workspace summary, carry `source_lane_id` and,
  for Linked Lanes, `source: {available, reason, yearclock_id,
  yearclock_name, lane_name}` as the viewer may see it. `reason` is
  `no_access` (no names are revealed) or `deleted` (the source Yearclock is
  recoverably deleted).
- Creating or moving Events or Series onto a Linked Lane returns `422
  {reason: "linked_lane"}`.
- `GET`, `PUT`, and `DELETE .../yearclocks/{yearclock_id}/access[/{user_account_id}]`
  list, grant or replace, and revoke one Member's Editor or Viewer grant.
  Grants require Owner or Admin; revocation takes `expected_version`. Both
  are audited and blocked while the Organization is read-only.

## Yearclock content

- `GET /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/events?window_start=YYYY-MM-DD&months=N` returns Events whose inclusive date range intersects the Planning Window of `months` whole months (1, 3, 6, 12, 18, or 24; default 12; other values `422`). The list also contains the Events and Occurrences of Source Lanes that the viewer may read, with `linked: true`, `source_yearclock_id`, and `lane_id` set to the Linked Lane; they cannot be changed through this Yearclock. `GET .../categories` adds those source Yearclocks' own Categories with `scope: "linked"` and `source_yearclock_name`. A requested window outside the materialization buffer is populated before the response is returned. Occurrences carry `occurrence_id`, `series_id`, `series_date`, and `exception`; `include_skipped=true` (Editors) also returns Skipped Occurrences with `skipped: true`.
- `POST /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/events` creates an Event. `PATCH` updates it with `expected_version`; `DELETE` soft-deletes it; Events and Series carry `starts_at` and `ends_at` (`HH:MM`; an end time needs a start time; on a one-day Event the end is after the start; 422 otherwise; an update replaces them like the other fields; the event list orders a day all-day first and then by `starts_at`) and `description_format` (`plain` or `markdown`; absent means plain on create and unchanged on update) and `location` (up to 200 characters, trimmed) and `links` (a list of at most 10 `{title, url}`: title 1–100, an `http(s)` address up to 2048, no repeated address; Yearclock V2 P11, ADR-0033; every write path including import and Support Access applies `event_content.py`); `GET .../deleted-events` lists recoverable Events with `purge_after` and `POST .../events/{event_id}/restore` restores one. Deleting a recurring Occurrence's Event returns `409` with `{"reason": "recurring_occurrence"}`; skip it or end its Series instead. These mutations require Organization Admin/Owner or Yearclock Editor access and create audit events.
- `GET`, `POST`, `PATCH`, `PUT .../categories/order`, and `DELETE` under `/api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/categories` manage Yearclock-defined Categories. `PATCH` takes `expected_version`; the order takes `expected_versions` per Category; `DELETE` requires `expected_version` and `confirm=true` and leaves affected Events and Series uncategorized. Category mutations require editor access and are audited.
- `POST /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/series` creates a weekly, monthly, or yearly Series (title, Lane, optional Category, description, and link, interval, and either `until` or `occurrence_count`; `last_day` only for monthly) and materializes its occurrences through the forward buffer. The response includes the equivalent RFC 5545 `rrule`. Series creation is audited.
- `PATCH .../occurrences/{occurrence_id}` (“This occurrence only”) takes `expected_version` (the Event's) and any of `title`, `description`, `location`, `links`, `lane_id`, `category_id`, and `starts_on`. Every field present becomes an explicit override; absent fields keep inheriting from the Series. `POST .../skip?skipped=true|false` skips or unskips; `POST .../restore?expected_version=` clears all overrides and the skip. Occurrence routes are scoped to the route Yearclock, preserve the Series Date, and are audited.
- `GET .../series/{series_id}` returns a Series segment with `version`, anchor `starts_on`, `effective_from`, `until`, and `rrule`.
- `POST .../series/{series_id}/split` (“This and future”) takes `from_occurrence_id`, the Series `expected_version`, and any of `title`, `description`, `location`, `links`, `lane_id`, `category_id`. It ends the segment the day before the selected Series Date and returns the successor segment, which keeps the anchor. Occurrences move by Series Date, keep their overrides, and inherit other fields from the successor. From a segment's first Occurrence it edits the segment in place.
- `POST .../series/{series_id}/end` with `from_occurrence_id` and `expected_version` removes that and later Occurrences of the segment and sets `until`; it returns `removed_occurrences`. Earlier Occurrences stay.

## Audit activity

- `GET /api/v1/organizations/{organization_id}/audit-events?action=&prefix=&offset=&limit=`
  returns Audit Events newest first for Owners and Admins (Members `403`).
  `action` filters one action, `prefix` one area such as `event` or
  `support_access`. Each item carries `actor` (email, or "Platform support"
  for a Support Agent), `support_access_id`, `action`, `target_type`,
  `target_id`, `occurred_at`, and `change_summary`. `limit` defaults to 50 and
  is capped at 100; `next_offset` is `null` on the last page. No endpoint
  mutates Audit Events.

## Labels (Yearclock V2)

- `GET /api/v1/organizations/{organization_id}/labels` lists the Organization's
  Labels (name, colour, version, usage) for any member, ordered by name.
- `POST .../labels` with `{name, color}` creates a Label for an Owner, an Admin,
  or an Editor of any live Yearclock (`201`). A name that exists, ignoring case,
  returns that Label with `200`. Colours must come from the fixed palette
  (`LABEL_COLORS`); names are trimmed and at most 60 characters.
- `PATCH .../labels/{id}` (`name`, `color`, `expected_version`),
  `POST .../labels/{id}/merge` (`into_label_id`, `expected_version`,
  `confirm`), and `DELETE .../labels/{id}?expected_version=&confirm=true` are
  Owner or Admin only. Without `confirm`, merge and delete answer `409`
  `{"reason": "confirmation_required", "usage": N}` and change nothing.
- Event create and update (customer and Support Access routes) accept
  `label_ids`: unique Labels of the same Organization, at most
  `LIMIT_LABELS_PER_EVENT`. On update, omitting `label_ids` keeps the current
  Labels and a list replaces them. Unknown, foreign, or duplicate ids return
  `422`; too many return `409 limit_reached` (`labels_per_event`). Every Event
  response carries `label_ids`, ordered by Label name. Audit summaries record
  `labels` on create and `labels_added` / `labels_removed` on update.
- Series create accepts `label_ids`; `GET` and split responses of a Series
  include them, and a split may set new `label_ids` for this and future
  Occurrences. An Occurrence edit may override `label_ids` (an empty list
  removes all Labels for that Occurrence); restore returns to the Series
  Labels.
- Merging or deleting a Label advances the version of every affected Event.
  Support Agents with a write grant can attach existing Labels; they cannot
  create Labels, which is a customer route.
- Changes are refused in a read-only Organization (`403`). The 201st Label
  returns `409 limit_reached` (`labels_per_organization`). Audit actions are
  `label.created`, `label.updated`, `label.merged`, and `label.deleted`, the
  last two with `affected_events`.

## Yearclock layout (Yearclock V2)

- `PATCH /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/layout`
  with `expected_version` and any of `start_month` (1–12), `show_week_ring`,
  and `show_quarter_ring`. Yearclock Editors,
  Admins, and Owners only (`403` otherwise); refused while read-only; no
  Support Access route. A change bumps the Yearclock `version` and is audited
  as `yearclock.layout_changed` with the changed fields; a stale version
  returns `409` with `latest_version`.
- Workspace Yearclock summaries include `start_month`, `show_week_ring`, and
  `show_quarter_ring`; Lanes include `tint` and `height`.
- The Lane `PATCH` also accepts `tint` (a palette colour, or `null` to clear)
  and `height` (`normal` or `tall`). Appearance changes are audited as
  `lane.updated` with the changed fields; renames stay `lane.renamed`.

## Search (Yearclock V2)

- `GET /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/search?q=&offset=`
  needs read access to the Yearclock (as the Event list). `q` must have at
  least two characters after trimming (`422`). Matching ignores case and
  accents (NFKD without combining marks, casefolded) over titles,
  descriptions, Category names, and Label names of non-deleted, non-skipped
  Events, including materialized Occurrences.
- The response is `{items, next_offset, total, includes_recurring}` with 50
  Events per page in date order; `items` are Event responses with
  `label_ids`. Searches are not audited.
- Events of Linked Lanes are included when the viewer may read their source
  Yearclock. They come back as in the Event list, with `linked: true`,
  `source_yearclock_id`, and the Linked Lane's `lane_id`.

## Groups (Yearclock V2)

All Group routes are under `/api/v1/organizations/{organization_id}`.

- **Groups:** `GET` and `POST /groups`, plus `PATCH` and `DELETE
  /groups/{group_id}` (`expected_version`, and `confirm` on delete).
  - Access: Owners and Admins; changes need mutation access.
  - Names are unique ignoring case (`409 duplicate_name`), and the count is
    capped by `groups_per_organization`.
  - Deleting a Group with members or grants without `confirm` returns `409
    {reason: "confirmation_required", members, yearclocks, losing_access}`.
- **Members:** `PUT` and `DELETE /groups/{group_id}/members/{membership_id}`
  add and remove a member of the Organization.
- **Audit:** `group.created`, `group.renamed`, `group.deleted`,
  `group.member_added`, and `group.member_removed`.
- **Own Groups:** `GET /me/groups`, for any member, returns
  `[{id, name, access}]` for the caller's own Groups only.
- **Group grants:** `GET /yearclocks/{yearclock_id}/group-access`, `PUT
  /yearclocks/{yearclock_id}/group-access` with `{group_id, role,
  expected_version?}`, and `DELETE
  /yearclocks/{yearclock_id}/group-access/{group_id}?expected_version=`.
  - Access: Owners and Admins; changes need mutation access.
  - A Group of another Organization returns `422`.
  - Audited as `yearclock.group_access_granted` and
    `yearclock.group_access_revoked`.
  - The access rule adds the source `{kind: "group", group_id, group_name}`
    for every member of the Group.

## Access overview (Yearclock V2)

- `GET /api/v1/organizations/{organization_id}/access-overview/people/{membership_id}`
  returns `{person, yearclocks: [{id, name, archived, role, sources}]}`.
- `GET …/access-overview/yearclocks/{yearclock_id}` returns `{id, name,
  people: [{membership_id, name, email, organization_role, role,
  sources}]}`.
- Both are for Owners and Admins only and come straight from
  `app/access.py`. Each source is `{kind: role | direct | group |
  organization, role, organization_role?, group_id?, group_name?}`.
- The membership removal confirmation uses the person view.

## Organization-wide Access (Yearclock V2)

- `PUT /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/organization-access`
  takes `{role: "none" | "viewer" | "editor", expected_version, confirm}`.
  - Access: Owners and Admins, with mutation access.
  - Setting `editor` without `confirm` returns `409 {reason:
    "confirmation_required", members}`.
  - The change bumps the Yearclock version and is audited as
    `yearclock.organization_access_changed`.
  - The managed Yearclock list returns `organization_access`.
- `app/access.py` adds the source `{kind: "organization"}`. Every member
  receives that role on the Yearclock, and the strongest source wins.

## Export (Yearclock V2 P7, ADR-0030)

- `POST /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/export`
  takes `{format: "xlsx" | "csv" | "ics", scope: "window" | "all", window_start?,
  length?, filters: {lanes, categories, labels}, locale: "en" | "fi"}` and
  answers with the file (`Content-Disposition: attachment`, `Cache-Control:
  no-store`). `filters` follows `frontend/src/yearclock/filters.ts`: OR inside
  a dimension, AND across, and `"none"` in `categories` for Events without a
  Category.
- Any reader of the Yearclock may call it (the access rule). The file holds one
  row per Event and Occurrence, without skipped or deleted ones, with the
  columns Title, Starts, Ends, Lane, Category, Labels, Description, Link,
  Series, and Source (the Yearclock of a Linked Lane the user may read). Dates
  are ISO dates (real date cells in Excel). Text cells that begin with `=`,
  `+`, `-`, or `@` get a leading `'`. CSV is UTF-8 with a byte order mark and
  uses `;` for `fi` and `,` for `en`. `ics` (P8, ADR-0031) is an iCalendar 2.0
  file (`app/ical.py`): one all-day `VEVENT` per Event and Occurrence
  (`DTEND` is the day after the last day), `UID` `<event id>@yearclock`,
  `SEQUENCE` from the Event version, `CATEGORIES` from the Category and
  Labels, and no `RRULE`, alarm, or attendee. Text is escaped and lines are
  folded at 75 octets; the formula guard is not applied.
- `429 rate_limited` (shared with import) with `Retry-After` and `retry_after_seconds` when the user
  already made `LIMIT_EXPORTS_PER_HOUR` exports, imports, or import previews in
  the last hour (counted from the Audit Log); `422` for an unknown window length
  or format.
- CORS exposes `Content-Disposition` and `Retry-After` so the browser can read
  the file name and the retry time.

## Data transfer (ADR-0040)

- `GET /api/v1/data-transfer/organizations` lists the Organizations where the
  user is Owner or Admin (`{organizations: [{id, name, role}]}`); the page and
  the account menu use it.
- `GET /api/v1/data-transfer/export` streams one CSV (UTF-8 with BOM,
  `Content-Disposition: attachment`, `Cache-Control: no-store`) of all of them;
  `403` when the user administers none, `429` over `LIMIT_TRANSFERS_PER_HOUR`.
  The first row names the columns, the second is the format row
  (`type=format`, `id=yearclock-data/1`, `name=<export time>`).
- `POST /api/v1/data-transfer/import?dry_run=true|false` takes the CSV as the
  request body and returns `{rows, organizations: [{id, name, kinds:
  {kind: {created, updated, unchanged}}, overwrites_newer}], errors: [{row,
  type, column, reason, value}], saved, import_id}`. `dry_run=true` saves
  nothing. A save with any error returns `422 {reason: "errors", errors}` and
  saves nothing. File-level refusals: `413 file_too_large`, `422` with
  `not_utf8`, `empty_file`, `unreadable_file`, `missing_column`,
  `unsupported_format`, `missing_format_row`, `too_many_rows`, `id_conflict`.
- Row kinds, parents, and rules are in ADR-0040 and
  `.scratch/yearclock-v2-data-transfer/technical-design.md`.

## Organization Export (Yearclock V2 P7, ADR-0030)

- `GET /api/v1/organizations/{organization_id}/export` streams one JSON document
  (`application/json`, `Content-Disposition: attachment`, `Cache-Control:
  no-store`), restricted to Owners; `403` for any other role and `404` for a
  stranger. It works while the Organization is active or in Pending Deletion
  and while it is read-only.
- The document is `{schema: "yearclock-export/1", exported_at, organization:
  {id, name, time_zone, default_locale, status}, members: [{membership_id,
  user_account_id, name, email, role, joined_at}], groups: [{id, name,
  member_ids}], labels, organization_categories, yearclocks: [...]}`. Each
  Yearclock holds its settings, `lanes`, `categories`, `series` (with
  `label_ids`), `events` (non-deleted, with `label_ids` and, for Occurrences,
  `series_id`, `series_date`, `skipped`, and `exception`), and `access`
  (`members` by membership and `groups`).
- It leaves out Event Revisions, Audit Events, billing and Stripe data,
  invitations, sessions, and the outbox.
- The generator reads one Yearclock at a time in its own transaction with the
  Owner's request context, so memory stays bounded by the largest Yearclock.
  Measured at the largest allowed Organization (50 Yearclocks of 3000 Events):
  13 s and 63 MB in a test client, so no background job is used.
- `429 rate_limited` with `Retry-After` after `LIMIT_ORGANIZATION_EXPORTS_PER_HOUR`
  downloads by the Owner in the last hour; each download writes
  `organization.export` with counts.

## Import (Yearclock V2 P7, ADR-0030)

- `GET .../yearclocks/{yearclock_id}/import/template?locale=en|fi` answers with
  an `.xlsx` of the column titles (Title, Starts, Ends, Lane, Category, Labels,
  Description, Link) and a second sheet listing the Lanes, Categories, and
  Labels that exist. Any reader may download it.
- `POST .../yearclocks/{yearclock_id}/import?format=xlsx|csv&dry_run=true|false`
  takes the file as the raw request body (`application/octet-stream`, at most
  `IMPORT_MAX_BYTES`, 2 MB). It is restricted to Editors, Admins, and Owners and
  refused while the Organization is read-only. The file is read again on the
  save, so nothing is stored between the preview and the save.
- The response is `{rows, create: [{row, title, starts_on, ends_on, lane,
  category, labels}], skipped: [{row, title, reason}], errors: [{row, column,
  reason, value}], created, import_id}`. `skipped` reasons are `duplicate` (the
  same Lane, title, and dates exist), `series`, and `linked` (rows with a Series
  or Source value, such as those of an export). `errors` are per row and per
  column (`missing_title`, `title_too_long`, `missing_start`, `invalid_date`,
  `end_before_start`, `missing_lane`, `unknown_lane`, `linked_lane`,
  `unknown_category`, `unknown_label`, `too_many_labels`, `description_too_long`,
  `invalid_link`, `link_too_long`, `duplicate_in_file`) or `missing_column` on
  row 1.
- A save (`dry_run=false`) with any error answers `422 {reason: "errors"}` and
  creates nothing. Otherwise it creates the Events in one transaction (History
  reason `import` with the `import_id`; one `event.created` audit entry each and
  one `yearclock.import`), after a capacity check: `409 limit_reached` when the
  Event ceiling would be exceeded.
- File problems answer `422` with `reason` `unreadable_file`,
  `macros_not_allowed`, or `too_many_rows` (`maximum`, `LIMIT_IMPORT_ROWS`),
  `413 file_too_large`, and `429 rate_limited` (the same hourly allowance as
  exports).
- Parsing: `.xlsx` is read as values only (formulas are never evaluated; cached
  results are used) and refused when it holds a macro project or unpacks to more
  than 50 MB; CSV is UTF-8 (with or without a byte order mark) or Windows-1252,
  separated by comma, semicolon, or tab. Column titles match in English or
  Finnish ignoring case and accents; unknown columns are ignored. Dates are ISO
  or `d.m.yyyy`. Names match ignoring case and accents. A leading `'` that an
  export puts before text that looks like a formula is removed.

## Bulk Edit (Yearclock V2)

- `POST /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/events/bulk`
  takes `{items: [{id, expected_version}], action, lane_id?, category_id?,
  add_label_ids?, remove_label_ids?}`. `action` is `move` (needs `lane_id`),
  `categorize` (`category_id` or `null`), `label` (adds, then removes), or
  `delete` (soft delete, recoverable as a single delete).
- Access and read-only rules are those of Event mutations. The change is all
  or nothing:
  - `422 {reason: "not_in_yearclock" | "recurring_occurrence", ids}` for
    Events of another Yearclock or recurring Occurrences;
  - `409 {reason: "stale", ids}` when any version differs or an Event is
    already deleted;
  - `409 limit_reached` for `bulk_events` (more items than
    `LIMIT_BULK_EVENTS`) or `labels_per_event`.
- The response is `{bulk_id, changed, items}`. Events that the action does
  not change keep their version and get no audit row; each changed Event is
  audited as `event.updated` or `event.deleted` with `bulk_id` in its change
  summary.

## Plan Again (Yearclock V2)

- `POST /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/plan-again`
  takes `{season_start, lane_ids, category_ids, include_uncategorized,
  date_rule, dry_run}`:
  - `season_start` is the first day of a month; the season is the 12 months
    from it.
  - `date_rule` is `same_date` (29 February becomes 28 February) or
    `same_weekday` (364 days later, which keeps the weekday within three days
    of the date a year later and keeps the length).
  - `dry_run` defaults to `true`.
  - It needs Editor mutation access, even for a dry run.
- It copies the single Events that start in the season on the chosen Lanes
  and Categories, into the same Yearclock, with their Lane, Category, Labels,
  description, and link. Recurring Occurrences are not copied. A copy is
  skipped when an Event with the same title, Lane, and moved start date
  already exists.
- The response is `{to_create, skipped_existing, limit_exceeded, maximum,
  created_ids}`:
  - A dry run writes nothing.
  - A real run that would exceed `events_per_yearclock` returns `409
    limit_reached` and creates nothing.
  - Otherwise every copy is audited as `event.created` with `plan_id`, and
    the whole run once as `yearclock.planned_again` with the counts.

## Event history (Yearclock V2)

- `GET /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/events/{event_id}/history?offset=`
  needs read access to the Yearclock. For an Event of a Source Lane, the
  caller must also be able to read its source Yearclock through a Linked Lane
  (`404` otherwise). It is not exposed to Support Access.
- The response is `{items, next_offset}`, newest first, 50 per page. Each
  item has:
  - `kind` (`created`, `updated`, `deleted`, `restored`, `version_restored`),
    `reason`, `reason_detail`, and `created_at`;
  - `actor: {kind, name}`, where `name` is the display name only while the
    account is a member, and `kind` is `support` or `system` for those
    changes;
  - `changes: [{field, before, after}]`. Lanes, Categories, and Labels come
    as `{id, name}`, with `name: null` once removed. `description` and
    `links` carry only the field name; `location` shows its values. An entry
    written before P11 holds `external_url`, which reads as a one-link `links`.
- **Restore:** `GET .../history/{revision_id}/restore-preview` and `POST
  .../history/{revision_id}/restore` with `{expected_version, lane_id?}`.
  - Both need Editor mutation access.
  - The preview returns `{changes, category_removed, labels_removed,
    lane_missing}`, comparing the current state with the restored one.
  - A missing Category or Label is left out. A missing Lane needs `lane_id`
    (`422 {reason: "lane_required"}` otherwise).
  - Refusals: `422` for recurring Occurrences (`recurring_occurrence`) and
    for Events of Linked Lanes (`linked_event`); `409 {reason: "deleted"}`
    for a deleted Event; `409 {latest_version}` for a stale version.
  - The result is a new `version_restored` revision, audited as
    `event.version_restored` with the restored fields.

## Changes since a time (Yearclock V2)

- `GET /api/v1/organizations/{organization_id}/yearclocks/{yearclock_id}/changes?since=&limit=`
  needs read access. It returns what others changed after `since`: the
  caller's own changes and background Series materialization are left out.
  It covers this Yearclock and the Source Lanes the caller may read.
- The response is `{items, total, more, latest_at}`, newest first:
  - Each item is `{event_id, series_id, title, kind, at, actor, count}`.
  - `kind` is `new`, `changed`, or `deleted`, one item per Event (its latest
    change).
  - A Series change becomes a single `series_changed` item per Series, whose
    `count` is the number of affected Occurrences.
  - `limit` is 1–200 (default 200). The planner uses the Previous Visit for
    marks, and `limit=1` for the change notice.

## Organization Categories (Yearclock V2)

- `GET /api/v1/organizations/{organization_id}/categories` lists Organization
  Categories with `usage` for any member. `POST`, `PATCH .../categories/{id}`
  (`expected_version`), `PUT .../categories/order`, and
  `DELETE .../categories/{id}?expected_version=&confirm=true` are Owner or
  Admin only. Names are unique per Organization ignoring case (`409
  duplicate_name`); the 41st returns `409 limit_reached`
  (`organization_categories`). Deleting without `confirm` answers `409`
  `{"reason": "confirmation_required", "usage": N}`; with it, affected Events
  and Series become uncategorized, Occurrence overrides to it become "no
  Category", and `category.removed` records the count.
- `GET .../yearclocks/{yearclock_id}/categories` returns Organization
  Categories first, then the Yearclock's own, each with `scope`
  (`organization` or `yearclock`). The Yearclock-level `PATCH`, `DELETE`, and
  order routes act only on the Yearclock's own Categories, so an Editor cannot
  change an Organization Category (`404`). Events, Series, Occurrences, and
  Support Access accept either kind of Category of the same Organization.
- Category audit summaries include `scope`.

## Notifications (Yearclock V2 P8, ADR-0031)

All under `/api/v1/organizations/{organization_id}`; any member of the
Organization may call them and only ever sees their own rows (row-level
security checks the recipient as well as the Organization). Support Access has
no route.

- `GET /notifications?cursor=&unread=` returns `{items: [{id, type, params,
  created_at, read_at}], next_cursor}`, newest first, 20 a page. The API sends
  the type and parameters; the interface builds the text in the reader's
  language. Types: `access_changed` (`yearclock_id`, `yearclock_name`,
  `from_role`, `to_role` with `none`, `viewer`, or `editor`), `role_changed`
  (`from_role`, `to_role`), `invitation_accepted` (`name`, `role`), and
  `ownership_changed` (`name`, `owner`). Parameters never hold Event content.
- `GET /notifications/unread-count` returns `{unread}`; the bell polls it
  every minute while the tab is visible.
- `POST /notifications/{id}/read` (204; 404 for someone else's) and
  `POST /notifications/read-all` (`{updated}`).
- `GET /notification-settings` returns `{items: [{key, audience, in_app,
  email}]}` for the caller's own settings (keys: `access_changed`,
  `access_removed`, `role_changed`, `invitation_accepted`, `ownership_changed`,
  and for Owners and Admins `support_access`, `billing`, `deletion`);
  `PUT /notification-settings` takes `{settings: {key: {in_app, email}}}` and
  422s on a key the caller may not set.
- Email: a notification whose key has the email switch on (defaults: only
  `access_removed` and the Organization notices) adds an outbox message
  (topic `notification`) in the same transaction, in the recipient's language,
  up to `LIMIT_NOTIFICATION_EMAILS_PER_DAY` (10) per recipient in 24 hours.
  Owner/Admin types: `support_access_requested`, `support_access_ended`,
  `billing_problem`, `deletion_scheduled`.
- The settings also carry the Summary choice: `summary: {frequency: "off" |
  "daily" | "weekly", yearclock_ids: [uuid] | null}` (null means every
  readable, non-archived Yearclock). `PUT` accepts `summary`; a Yearclock the
  caller may not read is a 422.
- The Summary (`app/summary.py`): the hourly scheduler enqueues one
  `notifications.summary` job per active Organization once its local time has
  reached 08:00 (one per local day). The job queues an outbox message (topic
  `summary`) for each person whose choice is due (daily; weekly on Mondays),
  once per local day, with Events of the next 7 or 14 days from the readable,
  non-archived chosen Yearclocks (own Lanes and Linked Lanes), without skipped
  Occurrences or deleted Events. Nothing is queued when the list is empty, the
  person is no longer a member, or the Organization is read-only or not active.
- A notification is written in the transaction of its cause (`app/notifications.py`).
  Access notices compare effective roles before and after a grant, revoke,
  Group, or Organization-wide Access change (`access.yearclock_roles`) and notify
  only the people whose role changed, never the actor; an unread notice for the
  same Yearclock is replaced and keeps where the change began, and disappears when
  it ended where it began.

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
  Organization's status, subscription view, seats, member and Yearclock
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
  - `GET /{request_id}/yearclocks` returns live Yearclocks with Lanes and
    Categories; `GET /{request_id}/yearclocks/{yearclock_id}/events` returns
    the Events of the current Planning Window (or `window_start`). Each read is
    audited as `support_access.content_read`.
  - `POST /{request_id}/yearclocks/{yearclock_id}/events` and
    `PATCH .../events/{event_id}` (with `expected_version`) need a `write`
    grant and edit single Events only. They write the normal `event.*` audit
    events.
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

An agent the person chooses reads and changes Yearclocks through the Model Context
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
- Tools (every Organization-scoped tool takes `organization_id`): `list_organizations`,
  `list_yearclocks`, `get_yearclock` (Lanes, Categories, Labels), `list_events`,
  `get_event`, `search`, and the writes `create_event`, `update_event`, `move_event`,
  `delete_event`. Writes apply the same rules as the REST API (role on the Yearclock,
  `expected_version`, limits, subscription state), are saved at once, and carry the
  MCP tool annotations (`readOnlyHint`, `destructiveHint`) so the client can ask the
  person first. Results that contain stored text include a notice that the text is data.
- A tool call fails with a readable error when the Organization's `mcp_enabled` switch is
  off or its `mcp_platform_blocked` flag is set, before any content is read.
- Every audit entry written during an MCP call carries `source: "mcp"` and
  `mcp_client` (the client id); Event Revisions made through MCP have the reason `mcp`.

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
