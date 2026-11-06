# Organization authorization matrix

This matrix states the V1 authorization rules from the PRD and ADR-0007,
ADR-0020, and ADR-0021. The *Notes* column records known implementation gaps
(QA review 2026-09-23); ticket state lives in `.scratch/yearclock-v1/issues/`.

Roles:

- **Owner**, **Admin**: Organization roles.
- **Member**: the Organization role without administration rights (`member`).
- **Editor**, **Viewer**: per-Yearclock grants held by a Member. A Member with
  no grant sees the workspace but no Yearclock and no administration data.
- **Unrelated**: an authenticated customer without a membership in the
  Organization.
- **Platform Admin**, **Support Agent**: Platform User roles. They never hold
  memberships (ADR-0021).
- **Support (grant)**: a Support Agent acting through an active, approved
  Support Access grant, limited to its scope (`read` or `write`).

## Organization administration

| Action | Owner | Admin | Member | Unrelated | Platform Admin | Support Agent | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Invite Member or Admin | allowed, within capacity | allowed, within capacity | denied | denied | denied | denied | |
| Invite, resend, or revoke Owner Invitation | allowed | denied | denied | denied | denied | denied | |
| List memberships | allowed | allowed | denied | denied | denied | denied | |
| Change a Member or Admin role, including other Admins | allowed | allowed | denied | denied | denied | denied | |
| Grant, demote, or remove Owner | allowed; final Owner protected | denied | denied | denied | denied | denied | |
| Remove a Member or Admin membership | allowed | allowed | denied | denied | denied | denied | |
| Transfer ownership | allowed; to an active Admin or Member, optionally keeping the Owner role | denied | denied | denied | denied | denied | One transaction; not while read-only; audited |
| Leave the Organization | allowed; the only Owner names a successor | allowed | allowed | — | — | — | The only person in the Organization cannot leave |
| Download the Organization Export | allowed | denied | denied | denied | denied | denied | Also while read-only or Pending Deletion; audited, 3 an hour |
| Download the all-Organizations CSV and import it back (Data transfer) | allowed | allowed | denied | denied | denied | denied | Per Organization where the user is Owner or Admin; members, Groups, and access rights are not in the file; audited, 3 an hour |
| Cancel the subscription or undo the cancellation | allowed | denied | denied | denied | denied | denied | End of the paid period only; audited; the other Owners and Admins are notified |
| Subscribe again after the subscription has ended | allowed | denied | denied | denied | denied | denied | Starts a Checkout; the webhook confirms it |
| Read or change the billing contact | allowed | denied | denied | denied | denied | denied | Stripe is updated first; the old address is told; 5 changes a day |
| Seat capacity and billing | allowed | denied | denied | denied | denied | denied | Customer Portal entry is not implemented |
| Request or restore Organization deletion | allowed | denied | denied | denied | denied | denied | 30-day limit and purge not implemented |
| Read and mark own notifications | allowed | allowed | allowed | denied | denied | denied | Own rows only; also while read-only |
| Read or change own notification settings | allowed | allowed | allowed | denied | denied | denied | Owners and Admins also see the Organization notice switches |
| Browse Organization audit activity | allowed | allowed | denied | denied | denied | denied | |
| Approve, reject, or revoke Support Access | allowed | allowed | denied | denied | denied | denied | |
| Request Support Access | denied | denied | denied | denied | denied | allowed | |

## Yearclock structure and content

| Action | Owner | Admin | Editor | Viewer | Unrelated | Platform Admin | Support (grant) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Create, rename, order, archive, restore Yearclocks | allowed | allowed | denied | denied | denied | denied | denied | Yearclock deletion not implemented |
| Grant or revoke Editor/Viewer access | allowed | allowed | denied | denied | denied | denied | denied | |
| Create, rename, reorder Lanes | allowed | allowed | granted Yearclocks | denied | denied | denied | `write` scope | Lane removal not implemented |
| Manage Categories | allowed | allowed | granted Yearclocks | denied | denied | denied | `write` scope | |
| Read Events and Occurrences | allowed | allowed | granted Yearclocks | granted Yearclocks | denied | denied | `read` or `write` scope | |
| Create, change, delete, restore Events and Occurrences | allowed | allowed | granted Yearclocks | denied | denied | denied | `write` scope | |

## Export and import (Yearclock V2 P7)

| Action | Owner | Admin | Editor | Viewer | Unrelated | Platform Admin | Support (grant) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Import Events from Excel or CSV (preview and save) | allowed | allowed | granted Yearclocks | denied | denied | denied | denied | Audited, hourly limit, blocked while read-only |
| Download the import template | allowed | allowed | granted Yearclocks | granted Yearclocks | denied | denied | denied | Lists the Lane, Category, and Label names the user may already see |
| Export a Yearclock's Events (Excel or CSV) | allowed | allowed | granted Yearclocks | granted Yearclocks | denied | denied | denied | Audited, hourly limit; Linked Lane content only with read access to the source |

## Agent access through MCP (ADR-0037)

An agent acts with the rights of the person who signed in; the tables above and below apply to
every tool call. The rows here are the MCP-specific controls.

| Action | Owner | Admin | Member | Unrelated | Platform Admin | Support Agent | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| See the connection details and the client secret | allowed; reveal is audited | allowed; reveal is audited | denied | denied | denied | denied | |
| Turn agent access on or off for the Organization | allowed | allowed | denied | denied | denied | denied | Audited; works in every subscription state |
| Block agent access for an Organization | denied | denied | denied | denied | allowed | denied | Audited; the Organization cannot lift it |
| Use an agent on the Organization's content | as the person's role | as the person's role | as the person's grants | denied | denied | denied | Refused while the switch is off or the block is set |

## Platform operations

| Action | Platform Admin | Support Agent | Any customer role | Notes |
| --- | --- | --- | --- | --- |
| List Organization lifecycle and subscription state | allowed | denied | denied | |
| List failed outbox messages | allowed | allowed | denied | Other job types and replay not implemented |
| Reach customer content | denied | only through an approved grant | — | Grant use is not yet wired into content endpoints or RLS |

## Rules

- No role has a deny override; the strongest granted role is effective.
- One function computes a member's role on Yearclocks and its Access Sources:
  `app/access.py` (`yearclock_access`, `role_on`, `accessible_yearclock_ids`),
  since Yearclock V2 P10a. Every authorization check uses it:
  - the Event, occurrence, Series, search, history, and Category sessions;
  - the Lane and structure session;
  - the inline Label check;
  - the workspace list and `access_role`;
  - visits;
  - `readable_yearclock_ids` for Linked Lanes.

  A test fails if any other module reads Yearclock grants, apart from grant
  management and cleanup.
- Every membership has one Organization role: Owner, Admin, or Member.
- Owner includes all Admin authority. Owner and Admin need no per-Yearclock
  grant, so the Admin role is the confidentiality boundary (ADR-0007).
- Only Owners and Admins create Yearclocks and grant Editor or Viewer access;
  Editors cannot share a Yearclock.
- A Member sees only granted Yearclocks and no membership list, seats, audit
  activity, or Support Access requests.
- A Support Access grant covers every Yearclock of the Organization (ADR-0020).
- Subscription read-only state blocks customer mutations for every role except
  Owner billing access.
- Account deletion is not exposed by the Yearclock API: Authentik remains
  authoritative for identity lifecycle. If an account-deletion flow is added,
  it must reject a request while the account is the last accepted Owner of any
  Organization.
