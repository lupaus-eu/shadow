# Runbook: a person asks for their personal data

Yearclock has no self-service export of one person's data. The Organization
Export (Owners only) covers a customer's content; a request from one person
(GDPR access or portability) is answered by hand with this procedure. It is an
engineering procedure, not legal advice: the answer's wording and deadlines are
the Platform Operator's legal responsibility.

## Before you start

1. **Confirm who is asking.** Ask the person to write from the email address of
   their account, or have an Owner of their Organization confirm the request.
   Never release data to an address that is not the account's.
2. **Decide the controller.** For planning content that a customer entered, the
   customer's Organization is the controller and the Platform Operator the
   processor: send the request to the Organization's Owner and offer the
   Organization Export. For account, session, and audit data about the person
   themself, the Platform Operator answers.

## Collect (Platform Operator)

Use a read-only database session (never a customer's session, and never Support
Access for this). Replace `:id` with the person's `user_accounts.id`.

| What | Query |
| --- | --- |
| Account | `SELECT email, display_name, locale, created_at FROM user_accounts WHERE id = :id` |
| Memberships and roles | `SELECT organization_id, role, created_at FROM organization_memberships WHERE user_account_id = :id` |
| Yearclock grants | `SELECT yearclock_id, role FROM yearclock_access_grants WHERE user_account_id = :id` |
| Group memberships | `SELECT g.name FROM member_groups g JOIN member_group_members m ON m.group_id = g.id JOIN organization_memberships o ON o.id = m.membership_id WHERE o.user_account_id = :id` |
| Recent Yearclocks | `SELECT yearclock_id, visited_at FROM yearclock_visits WHERE membership_id IN (SELECT id FROM organization_memberships WHERE user_account_id = :id)` |
| Actions they took (audit) | `SELECT action, target_type, occurred_at FROM audit_events WHERE actor_user_account_id = :id ORDER BY occurred_at` |
| Event revisions they made | `SELECT event_id, reason, created_at FROM event_revisions WHERE actor_user_account_id = :id` |

Identity data (credentials, MFA, identity sessions) lives in Authentik: export it
there. Billing identity of the customer is in Stripe.

## Answer

1. Send the collected data in a structured file (CSV or JSON) through a channel
   the person controls; do not email planning content of other people.
2. Leave out other people's personal data, such as other members' names in an
   audit entry.
3. Record the request, the date, who answered, and what was sent, outside the
   application's content.

Erasure of an account is a separate, not yet automated process: see
`docs/gdpr/README.md` (User Account deletion).
