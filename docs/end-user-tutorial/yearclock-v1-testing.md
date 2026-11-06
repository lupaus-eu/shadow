# Yearclock V1 end-user testing tutorial

This tutorial is a human-readable test journey for the features planned in
the 23 Yearclock V1 tickets. It is organized by ticket so that each implemented
slice can be demonstrated without reading implementation code.

Each chapter carries one of three statuses, last reviewed on 2026-09-23.
The authoritative acceptance state is in
the ticket files under [`.scratch/yearclock-v1/issues/`](../../.scratch/yearclock-v1/issues/)
and summarized in [`.scratch/_PORTFOLIO.md`](../../.scratch/_PORTFOLIO.md).

- **Available:** the ticket is implemented and the chapter is a runnable test.
- **Partial:** part of the ticket is implemented. The chapter tests only that
  part and lists what is missing.
- **Not implemented:** the chapter describes the intended demonstration, but
  the controls and behavior must not be expected to exist yet.

Do not use production identities, payment details, or confidential planning
content when following this tutorial.

## Before you begin

You need Docker with Docker Compose and a browser. From the repository root,
create the local environment file if it does not exist:

```bash
cp .env.example .env
```

Replace the placeholder secrets in `.env`, especially:

- `AUTHENTIK_POSTGRES_PASSWORD`
- `AUTHENTIK_SECRET_KEY`
- `AUTHENTIK_BOOTSTRAP_PASSWORD`
- `OIDC_CLIENT_SECRET`

The same `OIDC_CLIENT_SECRET` is used by Yearclock and the local Authentik
provider. To test registration, email verification, or recovery, also
configure the Scaleway SMTP values in `.env`.

Start the application:

```bash
docker compose up --build
```

Wait until the backend and frontend have started. The principal local
addresses are:

- Yearclock: <http://localhost:8173>
- Backend health: <http://localhost:8100/health>
- Authentik administration: <http://localhost:8190>

On a fresh Authentik database, open
<http://localhost:8190/if/flow/initial-setup/> and complete the initial setup
for the `akadmin` administrator. Its password is the
`AUTHENTIK_BOOTSTRAP_PASSWORD` value from `.env`.

There is no pre-created Yearclock customer. Create a separate non-admin test
identity through the registration link presented by Authentik. The `akadmin`
identity is for identity-provider administration, not normal Yearclock use.

## Ticket 01 — Establish the PostgreSQL application foundation

**Status: Available**

This ticket demonstrates that the browser, API, migrations, and PostgreSQL
database are connected through a production-shaped local stack.

### Test the service path

1. Start the stack as described in [Before you begin](#before-you-begin).
2. Open <http://localhost:8100/health>.
3. Confirm that the response reports an `ok` status for `Yearclock`.
4. Open <http://localhost:8173>.
5. After completing Ticket 02 sign-in, find the readiness message in the
   application shell.
6. Confirm it reads `PostgreSQL ready · schema <revision>` in English or
   `PostgreSQL valmis · skeema <revision>` in Finnish, where `<revision>` is
   the latest Alembic revision under `backend/migrations/versions/`
   (currently `0020`).

### Expected result

The frontend loads, the backend health endpoint responds, and an authenticated
shell can read the current schema revision from PostgreSQL. Restarting the
stack retains database state in the Docker volume.

This ticket also established migrations, transaction context, row-level
security foundations, audit primitives, and background-job primitives. These
are infrastructure capabilities and do not yet have separate end-user
controls.

## Ticket 02 — Authenticate a customer User Account

**Status: Available**

This ticket demonstrates private access, verified registration, strong
authentication, a persisted customer profile, language selection, session
expiry, and logout.

### Register a test customer

1. Ensure the Scaleway SMTP settings in `.env` can deliver to an email address
   you control.
2. Open <http://localhost:8173> in a private browser window.
3. Confirm that only the Yearclock sign-in entry point is shown. Planning or
   database content must not be visible.
4. Select **Continue with Authentik**.
5. Use the Authentik registration link to create a non-admin test identity.
6. Open the verification email and follow its link.
7. If Authentik prompts for strong-authentication setup, use a passkey when
   your browser and device support it, or configure TOTP with an authenticator
   app. If registration finishes without this prompt, sign out and start a new
   password sign-in; Authentik must require setup before that sign-in finishes.
8. Complete sign-in.

### Expected result

Yearclock opens the authenticated application shell and shows the test
identity's display name. The identity is linked by the provider's stable
issuer and subject identifiers; changing its email address does not create a
second Yearclock account.

An active Authentik identity that did not complete the configured email
verification flow must not be accepted as a verified Yearclock customer.

### Test Finnish and English

1. In the authenticated shell, select **Suomi**.
2. Confirm that the heading becomes **Vuosikello** and the shell messages are
   Finnish.
3. Reload the page and confirm Finnish remains selected.
4. Select **English** and confirm the English shell returns.

### Test logout and private access

1. Select **Sign out**.
2. Confirm that the authenticated shell disappears and the sign-in entry point
   returns.
3. Try opening <http://localhost:8100/api/v1/system/status> while signed out.
4. Confirm that the API rejects the request with HTTP `401 Unauthorized`.
5. Open <http://localhost:8173> in another private window and confirm it also
   starts signed out.

### Test an expired application session

1. Sign in to Yearclock.
2. In browser developer tools, remove the Yearclock application session
   cookie for `localhost`. The cookie is HTTP-only, so remove it through the
   browser's cookie/storage inspector rather than page JavaScript.
3. Reload Yearclock.
4. Confirm that the application fails closed, shows the session-expired
   message, and displays the sign-in entry point instead of customer content.

### Test password and recovery policy

1. Sign in using the test identity's password.
2. Confirm that password entry alone cannot finish authentication and that an
   enrolled second factor is required.
3. Start Authentik account recovery for the test identity.
4. Confirm that recovery requires the delivered email link and the configured
   MFA check.
5. Confirm that a passkey can be used as the preferred sign-in method when one
   has been enrolled.

## Ticket 03 — Activate the first paid Organization

**Status: Available**

### Prepare Stripe test mode

1. In Stripe test mode, create one product and a recurring monthly EUR 30 Price.
2. Copy `.env.example` to `.env` if you have not already done so.
3. Set `STRIPE_SECRET_KEY` to the Stripe test secret key and
   `STRIPE_MONTHLY_SEAT_PRICE_ID` to the recurring Price identifier.
4. Start a local Stripe webhook forwarder:

   ```bash
   stripe listen --forward-to localhost:8100/api/v1/billing/stripe/webhook
   ```

5. Copy the displayed `whsec_...` signing secret to
   `STRIPE_WEBHOOK_SECRET` in `.env`.
6. Restart the stack with `docker compose up --build`.

Never use live Stripe keys or a real card for this tutorial.

### Create and pay for an Organization

1. Sign in through Authentik.
2. In **Create your organization**, enter an Organization name, valid IANA time
   zone such as `Europe/Helsinki`, default language, billing name and email.
3. Set **Seats** to `3`.
4. Confirm that the page shows **€90.00 per month, billed in advance** and says
   that tax is calculated at Checkout.
5. Select **Continue to secure checkout**.
6. In Stripe Checkout, confirm the three-seat monthly subscription, billing
   address, tax details, and final tax amount. Pay with Stripe's test card
   `4242 4242 4242 4242`, any future expiry, and any CVC.
7. After returning, wait for the verified webhook. Confirm that the page shows
   the Organization as active, the Owner seat as active, and the localized
   blank **Yearclock · General** (or **Vuosikello · Yleinen**) structure.

The browser redirect does not activate anything. If Checkout is abandoned,
unpaid, or its Pending Activation record reaches 24 hours, no membership or
Organization access is created. Automated backend tests also replay the same
Stripe event to verify that duplicate delivery creates no duplicate content.

## Ticket 04 — Enter and switch Organization context safely

**Status: Available**

### Test direct entry

1. Sign in with a customer account that belongs to exactly one active
   Organization.
2. Open the application root.
3. Confirm that the browser proceeds directly to
   `/organizations/{organization-id}` without showing a selector.
4. Confirm that the Organization heading, your Organization role, its
   Yearclock, and General Lane are visible.

### Test the Organization selector and separate tabs

1. From an Organization workspace, select **Create another organization** and
   complete Ticket 03's Stripe test-mode activation flow.
2. Return to the application root.
3. Confirm that **Choose an organization** lists both Organizations and your
   role in each.
4. Open each Organization link in a separate browser tab.
5. Confirm that each tab keeps a different explicit
   `/organizations/{organization-id}` URL and continues to display the correct
   Organization after switching between tabs and refreshing.

### Test fail-closed links

1. Replace the Organization identifier in one tab's URL with a random valid
   UUID.
2. Confirm that the application reports that the Organization is unavailable
   rather than showing either Organization's content.
3. Restore the valid URL and confirm normal access.

The backend integration suite additionally pairs a Yearclock identifier from
one Organization with another Organization route and runs deliberately
unfiltered PostgreSQL reads and writes. Forced row-level security hides the
foreign rows and makes the cross-Organization update affect zero records.

## Ticket 05 — Adjust prepaid Organization Seat capacity

**Status: Available**

### Prepare Stripe

1. Use the Stripe test-mode product, Price, webhook forwarder, and test payment
   details from Ticket 03.
2. In the Stripe Customer Portal configuration, leave **Update quantities**
   disabled. Quantity changes must go through Yearclock so occupied and
   reserved capacity can be checked.

### Inspect and increase capacity

1. Open an Organization where you are an Owner.
2. In **Seat capacity**, confirm that **Purchased**, **Occupied**,
   **Reserved**, and **Available** are shown. The initial Owner counts as one
   occupied seat.
3. Enter a quantity larger than **Purchased** and select
   **Preview increase**.
4. Confirm that the prorated amount due now is shown before any change is
   requested.
5. Select **Confirm and pay** once.
6. Confirm that the old purchased and available counts remain in force while
   Stripe payment confirmation is pending.
7. After the verified Stripe subscription event arrives, reload if necessary
   and confirm the purchased quantity and available capacity increase.

An unpaid or failed increase never grants capacity. Replaying the same webhook,
or delivering a delayed failure after a successful change, must not alter the
confirmed quantity.

### Schedule a decrease

1. Enter a quantity lower than **Purchased**, but not lower than
   **Occupied** plus **Reserved**.
2. Select **Schedule decrease**.
3. Confirm that the current purchased quantity remains available and that the
   renewal date and future quantity are shown.
4. In Stripe test mode, advance the subscription to its renewal through a test
   clock or equivalent Stripe test tooling.
5. After the verified subscription update arrives, confirm that Yearclock
   applies the lower quantity.
6. Try a quantity below **Occupied** plus **Reserved** and confirm it is
   rejected.

Removing an Organization User in the later membership-management flow releases
one occupied seat immediately for reuse. It does not call Stripe or create a
credit for the already-paid current period.

## Ticket 06 — Invite and onboard an Organization User

**Status: Available**

An Owner or Administrator can invite a person when the Organization has an
available purchased Seat. Choose **Member** for a normal member;
Owners can additionally invite an Owner and Administrators can invite an
Administrator.

1. Sign in as an Owner, create an Organization with at least two Seats, and
   open its workspace.
2. Under **Invite people**, enter an email address, choose **Member**, and select **Send invitation**. Confirm that the invitation is
   shown as `pending` and that **Reserved** rises by one in the Seat capacity
   section.
3. Obtain the invitation URL from the email delivered by the `worker` service
   through Scaleway Transactional Email, and open it in a separate browser
   profile. No local mail catcher is included in the stack.
4. Sign in or register through Authentik using the exact invited, verified
   email address, then select **Accept invitation**. Confirm that the person
   can open the Organization and that the seat changes from Reserved to
   Occupied.
5. Try the URL while signed in with a different email. It must not grant
   access. Reusing an accepted URL must not create a second membership.
6. Back as an Owner or Administrator, use **Resend**. The original URL must no
   longer work; the replacement remains a single seat reservation. Use
   **Revoke** to release it immediately.
7. Leave a pending invitation for seven days. The next invitation-management
   view refresh marks it `expired` and releases its reservation.

Editor and Viewer access is not part of the Invitation. After acceptance, grant
it per Yearclock as described in Ticket 09.

Email delivery is asynchronous. Creating an invitation succeeds even if the
provider is temporarily unavailable; the worker retries delivery a bounded
number of times and records a failed job after the final attempt.

## Ticket 07 — Administer roles, ownership, and account exit

**Status: Available**

Removing or demoting the final Owner is protected. V1 has no account-deletion flow by design (Authentik owns identity lifecycle).

Owners and Administrators administer memberships in the **People** panel.
Owners alone can grant or remove ownership; Administrators manage Member and
Administrator roles, including other Administrators, but cannot alter Owners,
billing, seat capacity, or Organization deletion. Members see neither the
People panel nor invitations.

1. As an Owner, invite a second person with the `owner` role and have them
   accept the invitation using the exact invited email address.
2. Confirm both people appear in the **People** panel (and in
   `GET /api/v1/organizations/{organizationId}/memberships`).
3. As either Owner, use the role selector to change the other Owner to `admin`
   only after another Owner exists. Confirm the former Owner can no longer
   invite an Owner or use Owner billing controls.
4. Try to remove the final remaining Owner, including by using their own
   membership removal endpoint. Confirm that Yearclock rejects the action and
   retains the User Account.
5. Invite an Administrator. Confirm that they can list and remove a non-Owner
   membership through **People**, but cannot change an Owner role or remove an
   Owner.
6. Confirm a removed person loses this Organization from their organization
   selector, while their User Account and memberships in other Organizations
   remain intact.
7. Sign in as a Member. Confirm that neither **People** nor **Invite people**
   is shown, and that `GET .../memberships` and a role change through
   `PATCH .../memberships/{id}` return `403`, including for their own
   membership.

All invitation acceptance, membership-role, and membership-removal changes are
recorded in the Organization audit trail.

## Ticket 08 — Create and structure Yearclocks with Lanes

**Status: Partial**

Not yet available: Yearclock deletion (ticket 16).

1. As an Owner or Admin, open **Yearclocks**, enter a name, and select
   **Create**. Confirm it starts with one **General** Lane and is visible in
   normal navigation.
2. Rename the Yearclock with its inline name field. Repeat the equivalent API
   request with an old `expected_version` and confirm a `409` conflict returns
   the latest version.
3. Use **Up**/**Down** beside a Yearclock to change its order. Add a Lane,
   rename it, and use its **Up**/**Down** to change the ring order.
   Confirm the circular shell follows this Lane order.
4. Select **Archive**. Confirm normal Yearclock navigation omits it while the
   management list keeps it available for **Restore**.
5. Open the Organization workspace. Each active Yearclock has a responsive
   twelve-month circular SVG shell: the outer month scale and concentric Lane
   rings are visible even before Events exist.

All Yearclock creation, rename, archive, and restore mutations are audited.

## Ticket 09 — Grant Yearclock Editor and Viewer access

**Status: Available**

1. As an Owner or Admin, open **Yearclocks**, expand an active Yearclock’s
   **Access** section, select an existing Member, choose **Editor**
   or **Viewer**, and select **Grant**. The equivalent API is
   `PUT /api/v1/organizations/{organizationId}/yearclocks/{yearclockId}/access`.
2. Confirm an Owner or Admin retains management access without a grant.
3. Change a grant from Viewer to Editor and confirm it replaces the earlier grant; use **Revoke** (or the matching DELETE endpoint) to remove it.
4. Attempts to grant access to a person outside the Organization, or by an unrelated user, must be rejected.
5. Sign in as the invited Member. An Editor can add, rename, and
   reorder Lanes only in the granted Yearclock; the same user cannot create,
   archive, rename, or reorder Yearclocks. Change the grant to Viewer and
   confirm that the Lane controls are rejected as well.

6. As a Viewer, open the Yearclock. Confirm that Events and their details are shown, but there are no Add, Edit, Delete, or Category controls.

## Ticket 10 — Create and inspect Events

**Status: Available**

1. As an Owner, Admin, or Yearclock Editor, select **New Event**, or select an
   empty point on a Lane ring to prefill that Lane and date. Enter a title and
   an all-day start date, optionally an inclusive end date, Category,
   plain-text description, and `https` link, and select **Save**.
2. Confirm that a single-day Event appears as a dot and a date range as an arc
   on its Lane ring, and that **Events in this window** lists the same Event
   with its dates, Lane, and Category.
3. Try a blank title, an end date before the start date, or a non-HTTP link.
   The form explains the problem and keeps **Save** disabled; the API rejects
   the same values.
4. Select the Event and choose **Edit**. In another browser, change the same
   Event first; then save the first change. Confirm that Yearclock reports the
   conflict and shows the latest version instead of overwriting it.
5. Select **Delete**, confirm, and find the Event under **Deleted Events**.
   As a Viewer, confirm that the same details are shown without Edit or Delete.

## Ticket 11 — Classify Events and maintain Lane structure

**Status: Available**

1. As an Editor or higher, open **Yearclock settings**, enter a Category
   name and color, and select **Add Category**. Rename or recolor it with
   **Save** and reorder it with **Up**/**Down**.
2. Give Events on two different Lanes the same Category. Confirm they share
   its color on both rings and that the legend and the Event list name the
   Category, so color is never the only signal.
3. Delete a Category. Confirm the dialog says its Events become
   uncategorized, and that they remain after confirming.
4. Reorder Lanes and confirm the rings follow the new order while Event dates
   stay the same.
5. Delete a Lane that has Events. Confirm Yearclock reports how many Events
   and Series use it, then select another Lane and **Move Events and delete
   Lane**. The last remaining Lane cannot be deleted.

## Ticket 12 — Navigate the 12-month Planning Window

**Status: Available**

1. Confirm the default window is the current January–December calendar year
   in the Organization's time zone, with today's red line, the shaded elapsed
   part, and the elapsed percentage below the circle.
2. Use **Next year** and confirm that today's marker and the elapsed
   percentage disappear for a window that does not contain today.
3. Use **Previous month**, **Next month**, or **Start month** to start the
   window in any month, including across a year boundary. Confirm the circle
   still shows exactly 12 months and that February is visibly shorter.
4. Create a range that crosses the window boundary. Confirm it is clipped and
   described as continuing from or into the neighbouring window, and that it
   reappears in full when the window moves.
5. On a phone-sized screen, confirm the circle fits the width and Event
   details open as a full-screen sheet.

## Ticket 13 — Generate recurring Events

**Status: Available**

The constrained recurrence engine supports weekly, monthly, and yearly Series.
Monthly anchors fall back to the final valid date of shorter months and return
to their original anchor; last-day-of-month is distinct and always falls on
the month end. Yearly February 29 Series skip non-leap years.

1. Select **New Event**, fill in the title, start date, and Lane, and choose
   **Weekly**, **Monthly**, or **Yearly** under **Repeat**. Set **Every**, and
   choose whether it **Ends** never, on a date, or after a number of
   occurrences. Select **Save**.
2. Move the Planning Window forward and confirm the Occurrences appear on
   their dates. A monthly anchor such as the 31st uses the final day of a
   shorter month and returns to the 31st later.
3. Open a Planning Window several years ahead. Confirm it is complete: a
   distant window materializes its Occurrences before it is shown.
4. The `worker` service extends every Series daily through the Organization's
   today plus `RECURRENCE_BUFFER_DAYS`; no user action is needed.

## Ticket 14 — Edit recurring Occurrences and Series

**Status: Available**

1. Create a weekly Series. Select one occurrence and choose **Edit this
   occurrence**. Change its title and date and select **Save**. Confirm it is
   drawn as a diamond, its details show its original Series date, and the
   other occurrences are unchanged.
2. Select a later occurrence and choose **Edit this and future
   occurrences**. Change the description and Lane. Confirm earlier
   occurrences keep their values, later ones use the new values, and the
   occurrence you changed in step 1 keeps its title if it comes later.
3. Move an occurrence's date to before the point where you split the Series.
   Confirm it still belongs to the segment of its original Series date.
4. Select the changed occurrence and choose **Restore Series values**.
5. **Skip occurrence** hides one occurrence; restore it under **Skipped
   occurrences**.
6. Choose **End Series from here** on a future occurrence. Confirm that it
   and later occurrences disappear, earlier ones remain, and moving the
   Planning Window forward shows no new occurrences.

## Ticket 15 — Render dense recurrence accessibly

**Status: Available**

1. Create a weekly Series. Confirm the circle draws small markers with the
   Series title shown once, and that **Events in this window** groups the
   Series as one expandable entry with its occurrence count.
2. Change one occurrence. Confirm it is drawn as a diamond (or a dashed arc
   for a range) and described as a changed occurrence, not only by color.
3. Skip one occurrence and confirm it can be restored from **Skipped
   occurrences**.
4. With only the keyboard, press Tab from the Planning Window controls.
   Confirm focus moves through the markers in date order with a visible dark
   outline, and that Enter or Space opens the selected occurrence's details.
5. On a phone-sized screen, open the grouped Series and select an
   occurrence. Confirm the entries are easy to tap and the details open as a
   full-screen sheet.

## Ticket 16 — Recover deleted Events and Yearclocks

**Status: Available**

1. As an Editor, select a standalone Event and choose **Delete**. Confirm it
   appears under **Deleted Events** with the date until which it can be
   recovered, and restore it.
2. Select a recurring occurrence and confirm there is no Delete action: use
   **Skip occurrence** or **End Series from here** instead.
3. As an Owner or Admin, choose **Delete** beside a Yearclock under
   **Yearclocks** and confirm. The Yearclock and all its Events disappear from
   the workspace and appear under **Deleted Yearclocks**. Choose **Recover**
   and confirm its Lanes, Categories, Events, Series, and access grants are
   back.
4. The `worker` service purges Events and Yearclocks deleted more than 30
   days ago (`DELETED_CONTENT_RETENTION_DAYS`).

## Ticket 17 — Enforce renewal, cancellation, and payment-failure states

**Status: Available**

Use Stripe test mode with the webhook forwarder from Ticket 03.

1. As an Owner, select **Manage billing** and confirm Stripe's Customer
   Portal opens for this Organization.
2. Cancel the subscription in the portal. Confirm the workspace says when the
   subscription ends and that editing still works. Resume it in the portal
   and confirm the notice disappears.
3. Simulate a failed renewal (for example with a test clock and the
   `4000 0000 0000 0341` card). Confirm the workspace shows the seven-day
   deadline and editing still works.
4. After the grace period (or by letting the subscription end), confirm the
   workspace is read-only: Events stay visible, but New Event, Yearclock
   management, and invitations are hidden and the API returns `403` for
   changes. **Manage billing** still works for Owners.
5. Pay the outstanding invoice and confirm editing returns without any data
   being recreated.

## Ticket 18 — Expose Organization audit activity

**Status: Available**

1. Sign in as an Owner or Admin and open **Activity** at the bottom of the
   workspace.
2. Confirm recent changes (for example Event creation or a role change) are
   listed newest first with the action, the actor's email, and the time.
3. Choose an **Area** such as Events and confirm the list is filtered. Use
   **Load more** for older entries.
4. Confirm a Member sees no Activity panel and that the API
   `GET /api/v1/organizations/{organizationId}/audit-events` returns `403` for
   them. Ordinary viewing creates no entries, and no endpoint changes or
   deletes an entry.

## Ticket 19 — Operate Organizations and background jobs

**Status: Available**

1. Enroll a separate test identity:
   `docker compose exec backend python -m app.platform_admin enroll --email ops@example.com --role platform_admin`.
2. Open `/platform` and sign in with that identity. Confirm the console shows
   service health, the Organization list with status, subscription, seats, and
   counts, and failed jobs. No customer Event content appears.
3. Open the customer application with the same account and confirm it refers
   you to the console; the customer API returns `403`.
4. Sign in to `/platform` with a customer account and confirm it is refused.
5. Replay a failed job and confirm it is queued again and appears in the
   Organization's Activity as `platform.job_replayed`.

## Ticket 20 — Request and approve Support Access

**Status: Available**

1. Sign in to `/platform` with a Support Agent (see ticket 19 for enrollment).
   Under **Support Access**, enter the Organization ID (shown to Owners and
   Administrators in the customer **Support Access** panel), a case reference,
   scope *Read only*, and 4 hours, then **Send request**.
2. As the Owner, open the Organization. The request shows as waiting for a
   decision. Set **Approve for hours** to 2 and choose **Approve**; the grant
   shows as active with its end time. A Member sees no Support Access panel.
3. As the agent, choose **Open content** and confirm the Yearclocks and current
   Events appear. Creating an Event through the API with a read grant returns
   `403`.
4. As the Owner, open **Activity** and filter by *Support Access*: the request,
   approval, and each content view appear, marked *through Support Access*.
5. Choose **Revoke now** and confirm the agent can no longer open the content.
   Repeat with a *Read and edit Events* request to check that Event changes
   are marked in Activity.

## Ticket 21 — Delete and purge an Organization safely

**Status: Available**

1. As an Owner, open **Delete Organization** in the workspace. The button stays
   disabled until you tick the confirmation. Delete the Organization.
2. You return to the Organization list, which shows *Pending deletion — purged
   on (date)* about 30 days ahead. Other members no longer see the
   Organization, and its API routes are refused.
3. Choose **Restore**. The Organization opens again with its content, and
   Activity shows `organization.deletion_requested` and
   `organization.deletion_restored`. The subscription state is unchanged.
4. To test purge, set `ORGANIZATION_DELETION_RETENTION_DAYS=0` for the backend
   and worker, delete the Organization again, and wait for the worker
   schedule (`WORKER_SCHEDULE_INTERVAL_SECONDS`). The Organization disappears
   and the database keeps only its row with status `purged`.

## Ticket 22 — Harden production integrations and deployment

**Status: Partial — repository side ready; production verification needs a human**

1. Run `python3 scripts/check-compose-ports.py`; both Compose files pass.
2. Build the production frontend with
   `docker build --target production -t yearclock-frontend-prod frontend`, run it,
   and confirm `/platform` and `/organizations/<id>` return the app.
3. Start the local edge with `docker compose --profile edge up caddy` and check
   `curl -sI http://localhost:8180/platform` shows the security headers and
   `Cache-Control: no-store`.
4. Set `MONITORING_TOKEN`, then call `/api/v1/monitoring/health` with and
   without the bearer token (200 or 503, and 401).
5. Run `scripts/ops/backup-databases.sh backups` and
   `scripts/ops/restore-drill.sh backups/yearclock-*.dump backups/authentik-*.dump`.
6. Work through `docs/runbooks/production-readiness.md` on the production host.

## Ticket 23 — Complete v1 acceptance and security hardening

**Status: Partial — automated checks done; manual reviews open**

1. Run the backend suite and confirm `test_authorization_matrix.py`,
   `test_operational_limits.py`, and `test_security_review.py` pass.
2. Set `LIMIT_EVENTS_PER_YEARCLOCK=3` for the backend, create four Events, and
   confirm the fourth is refused with a message that names the limit.
3. Switch the interface to Finnish and walk through every panel; report any
   English text (`npm run test:unit` checks that every text exists in both
   languages).
4. Review `docs/runbooks/v1-acceptance-trace.md` (Partial items),
   `docs/architecture/security-review.md` (open items), and
   `docs/runbooks/launch-checklist.md`.

## Recording a test result

For each test session, record:

- date and tester;
- commit or release identifier;
- browser and operating system;
- ticket and test section;
- expected and actual result;
- screenshots or console/network evidence when useful;
- whether the result passed, failed, or was blocked;
- reproducible steps for every failure.

Do not record passwords, session cookies, verification links, MFA seeds,
payment details, or other secrets in test notes.
