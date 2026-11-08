# Privacy and data protection

This page records what personal data Yearclock processes, where it is kept,
and how long. It is an engineering inventory, not legal advice. Statutory
retention periods for Billing Records and audit evidence need legal review
before launch (PRD, *Further Notes*).

## Personal data held by Yearclock

| Data | Table | Purpose |
| --- | --- | --- |
| OIDC issuer and subject, email, display name, locale | `user_accounts` | Identify the signed-in person |
| Recently opened Yearclocks (membership, Yearclock, time, and the Previous Visit time) | `yearclock_visits` | Show a user their own recent Yearclocks and what others changed since their Previous Visit; only the user sees them; removed with the membership, the Yearclock, or the Organization |
| Session token hash, expiry, and the ID token until logout | `user_sessions` | Keep the person signed in; the ID token is sent once as `id_token_hint` at logout and then cleared |
| Pending login state | `oidc_login_attempts` | Complete the OIDC login securely |
| Membership and role | `organization_memberships` | Authorization |
| Group names and Group memberships | `member_groups`, `member_group_members` (Yearclock V2) | Give several members the same Yearclock access; member lists are visible to Owners and Admins, and each member sees their own Groups; removed with the membership, the Group, or the Organization |
| Invited email address and proposed role | `organization_invitations` | Deliver and accept an Invitation |
| Billing name and billing email | `organizations` | Stripe customer identity; an Owner can change them in the product (`organization.billing_contact_changed`, field names only), and the previous address gets a notice with the new address masked |
| Actor account, action, target, time, minimal change summary | `audit_events` | Accountability |
| Summary choice (daily or weekly, chosen Yearclocks) and the date it was last handled | `notification_preferences` (Yearclock V2 P8) | Send the opt-in Summary of upcoming Events; the emailed list carries Event titles, so the person must turn it on; it stops when the membership ends |
| Recipient, type, and parameters of a notification (never Event content) and each person's notification settings | `notifications`, `notification_preferences` (Yearclock V2 P8) | Tell a person about changes to their own access and role; read only by the recipient; notifications are deleted after 90 days and everything is removed with the membership's Organization |
| Recipient, subject, text, and accept URL of queued email | `outbox_messages` | Reliable email delivery |
| Support case reference, requesting agent, approver, scope, duration, decision times | `support_access_requests` | Controlled support; each use is audited in `audit_events` with the grant id |
| Titles, descriptions, locations, links, and other planning content | Yearclock content tables | The service itself; may contain personal data entered by customers |
| Earlier states of each Event with the changing account, time, and reason | `event_revisions` (Yearclock V2) | Event history and restore for everyone who may read the Yearclock; the account is shown by name only while it is a member, otherwise as "Former member" |
| Model timeline writes (`event.created`, `event.updated`, `event.deleted`) | `audit_events` (change summary) | Accountability. The summary holds ids, the event date and the number of changes per operation, never names of nodes, event titles or notes, so the Audit Log copies no personal data that people type into a Model (checked in `backend/tests/test_timeline_events.py`) |
| Source (`mcp`) and OAuth client id of changes made by an agent | `audit_events` (change summary), `event_revisions` (reason) | Show that a change came through the MCP interface and under whose sign-in; no agent prompts or conversations are stored |

Agent access (MCP): a person who connects an agent has it read and change what they could read and
change themselves; the agent's provider is the person's own choice and processes what the agent
reads. Yearclock stores no agent conversations and sends nothing to an agent unprompted. An Owner or
Admin can turn agent access off for the Organization, and the operator can block it.

Yearclock stores no passwords, passkeys, MFA secrets, or payment card details.

## Exports of personal data

| Route | Who | What leaves the application | Recorded |
| --- | --- | --- | --- |
| Export Events to Excel or CSV | Anyone who may read the Yearclock | The Events they may see, including text that may contain personal data | `yearclock.export` in the Audit Log (counts and format, never content) |
| Import Events | Editors, Admins, Owners | Nothing leaves; a file enters and is read in memory, never stored | `yearclock.import` and `yearclock.import_preview` |
| Organization Export | Owners | Members' names, emails, and roles, and all content | `organization.export` (counts only) |

Hourly limits per user apply to all three (`LIMIT_EXPORTS_PER_HOUR`,
`LIMIT_ORGANIZATION_EXPORTS_PER_HOUR`).

## Other processors

| Party | Data | Role |
| --- | --- | --- |
| Authentik (self-hosted) | Credentials, MFA factors, identity sessions, email | Identity provider operated by the Platform Operator |
| Stripe | Billing identity, address, tax identifiers, payment method, invoices | Billing system of record; Owners see the next charge and the latest invoices in the product, read from Stripe on each visit and never stored in Yearclock |
| Scaleway Transactional Email | Recipient address and message content | Email delivery for Authentik and Yearclock, including notification email (one sentence about a change to the recipient's own access or role, never Event content) |

## Retention and deletion

| Data | Rule | Implemented |
| --- | --- | --- |
| Deleted Event | Recoverable for 30 days, then purged | Yes |
| Event Revisions | At most `LIMIT_REVISIONS_PER_EVENT` (100) per Event, oldest removed first; removed with their Event, Yearclock, or Organization content | Yes |
| Deleted Yearclock | Recoverable for 30 days with all its content, then purged | Yes |
| Pending Deletion Organization | Recoverable for 30 days, then customer content purged; Billing Records and minimal deletion evidence kept | Yes (`organization.purge`): content, memberships, invitations, Support Access requests, email payloads, and audit change summaries removed; Organization row with billing identity and audit actions kept |
| Pending signup | Expires after 24 hours | Yes |
| Invitation | Expires after seven days | Yes |
| Removed membership | Removed; the User Account stays | Yes |
| User Account | Deletion blocked while sole Owner; coordinated with Authentik | No deletion flow |
| Audit Events | Configurable, separate from customer content | Retention not configured |
| Notifications | Deleted after `NOTIFICATION_RETENTION_DAYS` (90) by the daily `notifications.cleanup` job, and in the Organization purge | Yes |
| Legal acceptances (`legal_acceptances`) | Kept after the Organization purge as contract evidence (who accepted which version and when, with the e-mail address as written then); retention period for counsel to set, with the Billing Record identity | Kept, no deletion |
| Purged Organization row (name, billing name, billing email, Stripe ids) | Kept as Billing Record identity after the purge; proposed period: the statutory accounting period (**verify** with counsel, the period is not decided here) | Kept, no deletion job |
| Outbox messages | Not defined; proposal: clear the payload (address and text) a set time after delivery, as the purge already does for a purged Organization | No cleanup |

## Open items

- **Retention periods** for the purged Organization row, audit events, queued email, and acceptance records (including the
  e-mail snapshot) are decisions for counsel. They are listed in the table above and in
  [`backend/legal/privacy.en.md`](../../backend/legal/privacy.en.md) with `TODO(lawyer)`, and in
  `docs/legal/counsel-checklist.md`. Implementing a cleanup for queued email is a separate ticket once counsel decides.
- A data-subject access request from one person is answered by hand with
  [`docs/runbooks/personal-data-request.md`](../runbooks/personal-data-request.md);
  there is no self-service export of one person's data. Customers can take their
  content with them through the **Organization Export** (Owners only, Yearclock
  V2 P7), which is audited and rate limited and leaves out Event history, the
  Audit Log, billing data, and the email outbox.

## Records

| Record | File | Holds |
| --- | --- | --- |
| Records of processing (Art. 30, controller and processor) | [records-of-processing.md](records-of-processing.md) | the arranged inventory |
| Breach procedure (Art. 33 and 34) | [breach-procedure.md](breach-procedure.md) | steps and roles; the register is private |
| DPIA screening and DPO decision | [dpia-and-dpo-note.md](dpia-and-dpo-note.md) | why neither is required now |
| NIS2 and AI Act notes | [nis2-and-ai-note.md](nis2-and-ai-note.md) | applicability notes (**verify**) |
| Staff access and confidentiality | [staff-access-policy.md](staff-access-policy.md) | the rules; signed copies are private |
| Private registers (outside git) | [private-registers.md](private-registers.md) | templates and the folder |
| Public texts | [`docs/legal/`](../legal/README.md) | drafts and counsel's checklist |

Each record has an owner and a review date. Signed processor agreements are collected in the private folder
(`TODO(operator)`); the sub-processor list is `backend/legal/subprocessors.*.md`.

## Browser storage

The cookies and web-storage keys the application sets are listed with purpose and lifetime in
[`backend/legal/browser-storage.json`](../../backend/legal/browser-storage.json). All are strictly necessary or the
person's own preferences, so no consent banner is used (Finnish Act 917/2014 s. 205 allows storage that is needed
to provide the service the user asked for; counsel confirms this, see `.scratch/yearclock-v2-legal-documents/research.md`).
Two tests fail when the code and the list differ, and the browser storage notice (`backend/legal/storage.*.md`) must
follow the list. The identity provider's own cookies on the identity host are listed for information and not scanned.
