# Lifecycle defaults

These are initial product defaults. Durations remain configuration values so production policy can be adjusted without changing domain behavior.

## Invitations

- Invitations expire after seven days.
- Resending an Invitation invalidates the prior token.
- Expiry grants no access and does not create an Organization User.

## Support Access

- A Support Access request is read-only unless write access is explicitly requested and approved.
- A grant lasts no longer than 24 hours and may use a shorter requested duration.
- Expiry and revocation fail closed immediately.

## Recoverable deletion

- A deleted Event or Yearclock remains recoverable for 30 days
  (`DELETED_CONTENT_RETENTION_DAYS`) before content purge. A deleted
  Yearclock hides all its content in one lifecycle. The worker's daily
  `content.purge` job hard-deletes expired content idempotently and records
  `event.purged` or `yearclock.purged` Audit Events without content.
- A Pending Deletion Organization remains recoverable for 30 days
  (`ORGANIZATION_DELETION_RETENTION_DAYS`). The worker then enqueues one
  `organization.purge` job, which deletes Yearclocks with all content,
  memberships, invitations, and Support Access requests, empties queued email
  payloads and audit change summaries, and marks the Organization `purged`.
  The Organization row (billing identity and Stripe ids) and the audit trail
  of actions remain as Billing Record and deletion evidence. A job for an
  Organization restored in the meantime does nothing.
- Restoring an Organization does not itself restore an expired or cancelled Subscription.
- Recurring Events use Series-aware operations such as Skip Occurrence and ending a Series rather than silently deleting recurrence history.

## Account deletion

Yearclock does not yet provide an account-deletion flow; Authentik owns
identity lifecycle. These rules apply when one is added:

- A customer User Account cannot be deleted while it is the sole Owner of any Organization.
- The user must transfer ownership or delete each owned Organization first.
- Removing the final Organization membership does not automatically delete the User Account.
- Identity deletion is coordinated with Authentik after Yearclock confirms that ownership invariants are satisfied.

## Retention review

- Customer content follows the recoverable-deletion windows above and is then purged.
- Billing Records and minimal deletion evidence follow legally required retention rather than customer-content retention.
- Audit retention is configurable and distinct from customer content.
- Exact statutory billing and audit periods require legal review before production launch.
