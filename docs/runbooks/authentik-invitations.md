# Authentik invitations

In production nobody can create an account without an invitation link
(`AUTHENTIK_ENROLLMENT_OPEN=false`, the production default). The operator creates
the links in Authentik and sends them to the people chosen for the alpha or the
beta. People who already have an account sign in as usual and need no
invitation. The local development stack keeps enrollment open
(`AUTHENTIK_ENROLLMENT_OPEN=true`) so that tests and demonstrations can create
accounts freely.

This is separate from a **Yearclock Invitation**, which adds an existing account
to an Organization. A new person first needs an Authentik invitation to create
the account, then (optionally) a Yearclock Invitation to join an Organization.

## Create an invitation

1. Open the Authentik administration at
   `https://<identity domain>/if/admin/` and sign in as the administrator.
2. Choose **Directory**, then **Invitations**, then **Create**.
3. Fill in the form:
   - **Name**: lowercase letters, digits, and hyphens only, for example
     `anna-virtanen`. It identifies the invitation in the list; it is not shown
     to the invitee.
   - **Expires**: a date and time after which the link stops working. Use
     about a week.
   - **Single use**: on, for a personal link. The link is spent the first time
     it is opened (see "Good to know"). Leave it off for one link shared with a
     small group, and delete it when the group has joined.
   - **Flow**: choose `default-enrollment-flow` (Default enrollment Flow) so
     the link can be used only for enrollment. Leaving it empty also works.
   - **Custom attributes**: leave empty.
4. Select **Create**.

## Copy and send the link

1. In the **Invitations** list, open the arrow at the start of the invitation's
   row. Authentik shows the link to use.
2. Copy it. It looks like:

   ```text
   https://<identity domain>/if/flow/default-enrollment-flow/?itoken=<long identifier>
   ```

   If the interface does not show the link, build it yourself from the
   enrollment flow's address and the invitation's identifier (`itoken`).
3. Send it to the person yourself, by email or chat, with the notice about the
   alpha and what to expect (see `alpha-launch.md`). Authentik does not email
   invitation links.

## What the invitee sees

They open the link, choose a username and password, enter their name and email,
confirm the email through the link Authentik sends, and set up a second factor
(a passkey or an authenticator app). Enrollment then ends on Authentik's own user
page, which shows "Permission denied: Interface can only be accessed by internal
users", because enrollment creates external users; the account is fine. Tell the
invitee to open the Yearclock address next and choose **Continue with Authentik**;
they can then create an Organization or accept a Yearclock Invitation.

## Revoke or clean up

- Delete an invitation in the **Invitations** list to make its link stop
  working at once. Accounts already created from it stay.
- Delete spent, expired, or unused invitations after a while.

## Good to know

- A visitor without a valid link who opens the enrollment page, or follows the
  **Sign up** link on the sign-in page, sees "Invalid invite/invite not found".
  That is the expected closed state, not a fault.
- A single-use invitation is spent when the link is first opened, even if the
  person does not finish. If someone gives up halfway or their link is refused,
  create a new invitation for them.
- An expired or deleted invitation shows the same message. Send a new link.
- The invitation does not limit which email address is entered; check the
  address you expect when the person appears in **Directory**, **Users**.
- Closing and opening enrollment later: set `AUTHENTIK_ENROLLMENT_OPEN=true` in
  `.env.production` and restart `authentik-config-init`
  (`docker compose -f docker-compose.prod.yml --env-file .env.production up -d authentik-config-init`).
  Set it back to `false` to close it again.
- The invitation requirement is part of the versioned identity policy
  (`authentik/blueprints/yearclock-identity-flows.yaml`); a change made only in
  the Authentik interface is reverted the next time the blueprints are applied.
- The blueprints are applied only when something that feeds them changed (the
  script, the blueprint files, the Authentik image, or the OIDC, `FRONTEND_URL`, and
  `AUTHENTIK_ENROLLMENT_OPEN` values); otherwise `authentik-config-init` skips and
  exits in a second. To apply them anyway, for example to undo an interface change or
  after the Authentik database was recreated but the `authentik_media` volume was
  not:

  ```bash
  docker compose -f docker-compose.prod.yml --env-file .env.production run --rm -e AUTHENTIK_CONFIG_FORCE=true authentik-config-init
  ```
