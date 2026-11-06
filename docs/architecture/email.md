# Transactional email

## Provider

Scaleway Transactional Email sends identity and application-generated transactional email. Marketing email is outside this system.

## Service boundaries

- Authentik sends verification and recovery messages through the Scaleway TEM SMTP relay using STARTTLS.
- Yearclock sends invitations, ownership changes, billing notices, and support workflow messages through the Scaleway Transactional Email REST API. Only Invitation email is implemented. It is written in the Organization's default language (Finnish or English), because the invitee has no account yet.
- Notification email (topic `notification`) is composed by `app/notification_email.py` in the recipient's language: one sentence, a link to the inbox, a link to the settings, no tracking. The worker sends it with the Invitation email.
- The Summary of upcoming Events (topic `summary`, `app/summary.py`) is opt-in, the only message that carries Event content (titles, dates, Lane and Yearclock names), and goes only to the person who chose it. It is not counted against the notification email limit.
- The billing contact notice (topic `billing.contact_changed`, `app/billing_contact.py`) goes only to the previous billing address when it is replaced, in the Organization's default language, with the new address masked. It is not counted against the notification email limit.
- V1 does not send Event reminders or date-based notifications. V2 P8 (ADR-0031) adds notification email (access, role, and Organization notices, capped at 10 per recipient per 24 hours) and an opt-in Summary of upcoming Events; both go through the outbox.
- The shared Scaleway contract uses `SCW_ACCESS_KEY`, `SCW_SECRET_KEY`,
  `SCW_DEFAULT_ORGANIZATION_ID`, and `SCW_DEFAULT_PROJECT_ID`, so later
  Scaleway services can use the same deployment-secret convention. TEM sends
  authenticate with `SCW_SECRET_KEY` and target `SCW_DEFAULT_PROJECT_ID`.
- `SCW_TEM_REGION`, `SCW_TEM_API_BASE_URL`,
  `SCW_TEM_DEFAULT_SENDER_EMAIL`, and `SCW_TEM_DEFAULT_SENDER_NAME` configure
  the TEM adapter. `SCW_TEM_API_BASE_URL` is the TEM regional API prefix
  (`https://api.scaleway.com/transactional-email/v1alpha1/regions`); the
  adapter appends `/{region}/emails`. Authentik SMTP uses the Project ID as its
  username and the secret key as its password.
- Credentials are stored as deployment secrets and are never committed.

## Application outbox

- Yearclock writes an email outbox record in the same PostgreSQL transaction as the action that triggers it.
- A worker sends pending records and retries transient failures.
- Invitation, ownership, and support state changes never depend on synchronous email delivery.
- Delivery identifiers and status may be stored without copying unnecessary message content into audit records.

## Domain and deliverability

- The sending domain is verified before production use.
- SPF, DKIM, DMARC, and the recommended MX configuration are required.
- Bounce, rejection, and domain-reputation signals are monitored.
- Transactional and marketing traffic do not share this delivery path.

## Deployment

Scaleway SMTP egress must be enabled for the infrastructure running Authentik.
The default SMTP path is `smtp.tem.scaleway.com` on port 587 with STARTTLS.
