# Production readiness

The first release is the internal alpha ([`alpha-launch.md`](alpha-launch.md)); for
the invited beta also read [`beta-launch.md`](beta-launch.md), which adds the access
gate, the database stance, and the legal and operating items.

For the order of work on a new host (images, registry token, files, first start), use
[`first-deployment.md`](first-deployment.md).

Status: the repository side is prepared (ticket 22). The steps marked
**human** need production accounts, DNS, or secrets and have not been executed.
Record the date, the person, and the evidence next to each item when it is done.

## 1. Host and secrets

- [ ] **human** Create `.env.production` from `.env.production.example` on the host (never
  in git). Every variable marked `:?` in `docker-compose.prod.yml` is required;
  generate `POSTGRES_PASSWORD`, `AUTHENTIK_POSTGRES_PASSWORD`,
  `AUTHENTIK_SECRET_KEY`, `AUTHENTIK_BOOTSTRAP_PASSWORD`, `OIDC_CLIENT_SECRET`,
  `MCP_OIDC_CLIENT_SECRET`, and `MONITORING_TOKEN` with `openssl rand -hex 32` (letters and digits only: the
  database password is part of a URL), a different value for each.
- [ ] **human** Set `SHADOW_EDGE_BIND_ADDRESS=0.0.0.0`,
  `SHADOW_HTTP_PORT=80`, `SHADOW_HTTPS_PORT=443`,
  `SHADOW_SITE_ADDRESS=<app domain>`, `SHADOW_IDENTITY_ADDRESS=<identity domain>`,
  `FRONTEND_URL` and `PUBLIC_API_BASE_URL` to `https://<app domain>`, and
  `OIDC_ISSUER=https://<identity domain>/application/o/shadow/`.
- [ ] **human** Point DNS A/AAAA records for both domains at the host.
- [ ] **human** Order the host (2 GB / 2 CPU at least, 4 GB recommended; add 2 GB swap
  on the smaller one), install Docker, and `docker login ghcr.io` with a
  `read:packages` token (ADR-0035).
- [ ] Cut a `v*` tag from a green `main`, wait for the Images workflow, and set
  `SHADOW_TAG=<tag>` in `.env.production`.
- [ ] Start: `docker compose -f docker-compose.prod.yml --env-file .env.production pull`,
  then `docker compose -f docker-compose.prod.yml --env-file .env.production up -d`.
  `migrate` runs before `backend` and `worker`. Only Caddy publishes ports.

## 2. Authentik

- [ ] **human** Sign in at `https://<identity domain>/if/flow/initial-setup/` with the
  bootstrap password, create a named administrator with a passkey and TOTP,
  and store the bootstrap (`akadmin`) credentials in the break-glass vault.
  Disable daily use of `akadmin`.
- [ ] **human** Confirm the applied blueprints: verified-email enrollment,
  recovery email with MFA verification, passkey support, and mandatory second
  factor for password sign-in.
- [ ] **human** Smoke test: sign up a customer, verify the email, sign in with MFA,
  recover the account, and sign in to `/platform` with an enrolled operator
  (`python -m app.platform_admin enroll ...`).

- [ ] **human** `.env.production` has `MCP_OIDC_CLIENT_ID`, a random `MCP_OIDC_CLIENT_SECRET`, and
  `MCP_OIDC_ISSUER`; `MCP_ENABLED` stays `false` until the MCP smoke test in
  [mcp-interface.md](mcp-interface.md) has passed.

## 3. Stripe (sandbox first)

The full procedure, with receipts and invoices, tax, the restricted key, retries,
test clocks, and the live smoke test, is in
[`stripe-production.md`](stripe-production.md); the items below are the
summary.

- [ ] **human** Create the Product and the EUR 30 monthly per-seat Price, and set
  `STRIPE_MONTHLY_SEAT_PRICE_ID`.
- [ ] **human** Configure tax (Stripe Tax registrations or manual rates).
- [ ] **human** Add the webhook endpoint `https://<app domain>/api/v1/billing/stripe/webhook`
  for `checkout.session.completed`, `customer.subscription.updated`,
  `customer.subscription.deleted`, `customer.subscription.pending_update_applied`,
  `customer.subscription.pending_update_expired`, `invoice.paid`, and
  `invoice.payment_failed`; set `STRIPE_WEBHOOK_SECRET`.
- [ ] **human** Customer Portal: allow payment-method updates, cancellation at period
  end, and invoice history; disable quantity changes.
- [ ] **human** Use a restricted live key, set the retries to one week with the final action "cancel the subscription", and leave delayed payment methods (SEPA, bank transfer) off until the webhook handles their events (`stripe-production.md` sections 2, 6, and 7).
- [ ] **human** Verify in the sandbox (with test clocks for the renewals): signup and activation, a seat increase, a failed
  renewal (grace), recovery, cancellation, and a webhook with a wrong
  signature (rejected with 400). Stripe's dashboard shows failed deliveries;
  Shadow does not store rejected webhook calls.
- [ ] **human** With the restricted key and a test clock, open **Billing and seats**: the next charge shows the previewed amount; after scheduling a seat decrease it shows the lower seat count (if not, see the fallback in `.scratch/shadow-v2-billing-overview/technical-design.md`); after a renewal and a seat increase the payment list shows both invoices with working Stripe links; after cancelling it says there is no further charge.
- [ ] **human** Secret rotation: roll the webhook secret in Stripe, update
  `STRIPE_WEBHOOK_SECRET`, restart `backend`, and send a test event.

## 4. Scaleway Transactional Email

- [ ] **human** Create an IAM application limited to Transactional Email for the
  project, and set `SCW_SECRET_KEY` and `SCW_DEFAULT_PROJECT_ID`.
- [ ] **human** Verify the sending domain: SPF, DKIM, DMARC (`p=quarantine` or
  stricter), and MX; set `SCW_TEM_DEFAULT_SENDER_EMAIL` and `AUTHENTIK_EMAIL_FROM`.
- [ ] **human** Send an Invitation (REST path) and an Authentik recovery email (SMTP
  path); confirm both arrive and pass DKIM.
- [ ] **human** Configure bounce handling in Scaleway and confirm a failed delivery
  appears in the operator console after three attempts.

## 5. Edge and headers

- [ ] **human** Confirm Caddy obtained certificates for both domains.
- [ ] **human** Check `curl -sI https://<app domain>/` and `/platform`: HSTS,
  Content-Security-Policy with `frame-ancestors 'none'`, `X-Content-Type-Options`,
  `Referrer-Policy`, and `Permissions-Policy` are present; `/api/*` and
  `/platform` responses are `Cache-Control: no-store`.
- [ ] **human** Open the app in a browser and confirm the console shows no CSP violations.

## 6. Monitoring

- [ ] **human** Point an uptime monitor at `GET https://<app domain>/api/v1/monitoring/health`
  with `Authorization: Bearer $MONITORING_TOKEN`, alerting on anything but 200
  (see `docs/operations/monitoring.md`), plus a plain check of `/health` and
  of `https://<identity domain>/-/health/live/`.
- [ ] **human** Set `MONITORING_DATABASE_MAX_BYTES` to about 80 % of the volume size.

## 7. Backups

For the invited beta the stance, the retention, the off-host copy, the
dead-man's switch, and the restore-to-a-new-host rehearsal are in
[`beta-launch.md`](beta-launch.md) (Database and backups). The items below are
the minimum for any production use.

- [ ] **human** Set up the scheduled off-host backups, the disk check, and the
  alert emails as described in [`backup.md`](backup.md) (a daily
  `scripts/ops/backup-databases.sh` run copied off the host with encryption is
  the minimum).
- [ ] **human** Run `DRILL=1 scripts/ops/restore-offsite.sh /tmp/restore` (or
  `scripts/ops/restore-drill.sh <shadow dump> <authentik dump>`)
  after the first backup and then monthly; record the output. (Verified on the
  development stack on 2026-09-23: both restores succeeded independently.)
