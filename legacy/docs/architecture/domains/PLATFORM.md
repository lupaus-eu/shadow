# Platform domain

Status: foundation implemented (SaaS plan steps 078A–D, ADR-016 and ADR-019);
tenants, billing, legal, invitations and the platform console follow.

The Platform domain holds the services every feature builds on. It owns no
business data of Organisations; it records who did what, runs background work,
sends email and tells people that something changed.

## Owned tables

`audit_events`, `background_jobs`, `outbox_messages`, `notifications`
(see [DATABASE.md](../data/DATABASE.md)). Only the Platform code in
`backend/app/platform/` writes them; other domains call its functions in their
own transaction.

## Capabilities

| Capability | Code | Rule |
| --- | --- | --- |
| Request context | `app.core.database.transaction_session` | New code acts under the role `shadow_app` with `app.*` settings for the user and the tenant (ADR-016). |
| Audit | `app.platform.audit` | `record_audit_event` writes an append-only event with actor and tenant from the context; no context is an error; MCP provenance is stored under `change_summary.source`. |
| Jobs | `app.platform.jobs`, `work_queue` | Idempotent enqueue per tenant, `SKIP LOCKED` claims, retries with backoff, stale-claim recovery; features register handlers and schedulers. |
| Worker | `python -m app.platform.worker` | Runs schedulers, jobs and the email outbox; separate from the prediction worker. |
| Email | `app.platform.email_delivery` | `EMAIL_BACKEND` = `scaleway`, `smtp` (Mailpit) or `log`; content and addresses are never logged. |
| Notifications | `app.platform.notifications` | `notify_many` in the caller's transaction; never notifies the actor; dedupe replaces an unread one; daily email limit except mandatory notices. |

## API

`/api/v1/notifications` (session required; the caller's own notifications only):

| Method and path | Purpose |
| --- | --- |
| `GET /notifications?cursor=&unread=` | Page of 20, newest first, with `next_cursor` |
| `GET /notifications/unread-count` | Number of unread |
| `POST /notifications/read-all` | Mark all own as read (origin and CSRF required) |
| `POST /notifications/{id}/read` | Mark one as read; another person's id is 404 |

## Not yet decided or built

Tenant foreign keys and row-level security on these tables, notification types
and preferences, the frontend inbox, audit calls in existing mutations, the
platform console, and cleanup of finished queue rows.
