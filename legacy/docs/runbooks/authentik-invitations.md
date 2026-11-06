# Authentik invitations

In production nobody can create an account without an invitation link
(`AUTHENTIK_ENROLLMENT_OPEN=false`, ADR-017). The operator creates the links in
Authentik and sends them to the people chosen for the beta. People who already
have an account sign in as usual. The local stack keeps enrollment open so that
tests and demonstrations can create accounts freely.

This is separate from a tenant invitation (step 6 of the SaaS plan), which adds an
existing account to a company. A new person first needs an Authentik invitation to
create the account.

Until tenants exist (step 3), Shadow signs in only people it already knows by
verified email (ADR-017): create the person's account in Shadow first, then send the
invitation for the same email address.

## Create an invitation

1. Open `https://<identity host>/if/admin/` and sign in as the administrator.
2. Choose **Directory**, **Invitations**, **Create**.
3. Fill in the form:
   - **Name**: lowercase letters, digits and hyphens, for example `anna-virtanen`.
   - **Expires**: about a week.
   - **Single use**: on, for a personal link.
   - **Flow**: `default-enrollment-flow`.
   - **Custom attributes**: leave empty, or set `email` to pre-fill the address.
4. Select **Create**.

## Copy and send the link

Open the arrow at the start of the invitation's row and copy the link:

```text
https://<identity host>/if/flow/default-enrollment-flow/?itoken=<long identifier>
```

Send it to the person yourself with a short note about what to expect. Authentik does
not email invitation links.

## What the invitee sees

They open the link, choose a username and password, enter name and email, confirm the
email through the link Authentik sends, and set up a second factor (an authenticator
app or a passkey). Enrollment signs them in. Tell them to open Shadow next and choose
to sign in.

## Revoke or clean up

- Delete an invitation to make its link stop working at once. Accounts already
  created from it stay.
- Delete spent, expired or unused invitations after a while.

## Good to know

- A visitor without a valid link, or one who follows **Sign up** on the sign-in page,
  sees "Invalid invite/invite not found": the expected closed state.
- A single-use invitation is spent when the link is first opened, even if the person
  does not finish; create a new one if they give up halfway.
- The invitation does not limit which email address is entered; check the address in
  **Directory**, **Users**. Shadow links the identity only when the verified email
  matches an existing account.
- The invitation requirement is part of the versioned policy
  (`authentik/blueprints/shadow-identity-flows.yaml`); a change made only in the
  interface is reverted when the blueprints are next applied.
- Closing and opening enrollment later: set `AUTHENTIK_ENROLLMENT_OPEN` in the env
  file and apply the blueprints (`make authentik-apply` locally, see
  [authentik-local.md](authentik-local.md)).
- The email Shadow accepts is the one recorded as verified when the person confirmed the
  link; if an operator later edits the address in Authentik, it is no longer verified and
  the person cannot sign in to Shadow until they verify the new one.
