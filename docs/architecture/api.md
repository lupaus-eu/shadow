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
| `GET`, `PATCH`, `DELETE` `/models/{model_id}` | Read (with types and rules), rename, delete |
| `POST`, `PATCH`, `DELETE` `.../nodes[/{node_id}]` | Nodes of a version (`version_id` in the body or query) |
| `POST`, `DELETE` `.../connections[/{connection_id}]` | Connections; the allowed-connection rule is enforced |
| `POST`, `PATCH`, `DELETE` `.../node-types[/{type_id}]` | Node types; deleting one in use answers 409 `in_use` |
| `POST`, `PATCH`, `DELETE` `.../connection-types[/{type_id}]` | Connection types; the same rule |
| `POST`, `DELETE` `.../allowed-connections` | Add or remove a rule allowing a connection type between two node types; removing one in use answers 409 |

## Versions (ADR-0045)

| Method and path | Purpose |
| --- | --- |
| `GET`, `POST` `/models/{model_id}/versions` | List and fork a version from a base |
| `PATCH`, `DELETE` `.../versions/{version_id}` | Rename, delete |
| `GET` `.../versions/{version_id}/changes` | Change list against the base: added, removed, and changed nodes and connections |
| `POST` `.../versions/{version_id}/merge` | Apply the change list to the base. Owner or Admin only. Answers counts of what was applied; metrics are not merged. Audit `version.merged` |

## Metrics

Under `.../versions/{version_id}/metrics`.

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

Under `.../versions/{version_id}/simulations`: `GET`, `POST` list and run a
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
  - Reads: `list_models`, `get_model` (nodes, connections, metamodel), `get_version_changes`,
    `list_metrics`, `get_metric_series`, `list_simulations`, `get_simulation`, `get_analysis`.
  - Writes: `create_model`, `create_node`, `create_connection`, `create_version`,
    `create_metric`, `set_metric_values`, `run_simulation`, `generate_analysis`,
    `set_analysis_summary`, `add_proposal` (the agent's own analysis, ADR-0047), and
    `merge_version` (Owner or Admin; marked destructive).
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
