# Administrator guide

This guide is for the people who administer Shadow: managing users and their
roles, AI connections, and, once Shadow is offered as a service, the
subscribing company's settings and the platform operators' tools.

## Signing in and access (ADR-017)

People sign in to Shadow through Authentik, Shadow's identity provider, with a
passkey or a password plus a second factor. Authentik owns credentials and
recovery; Shadow decides what a person may do.

- **Inviting a person.** In production nobody can create an account without an
  invitation link from the operator ([authentik-invitations](../runbooks/authentik-invitations.md)).
  Until tenants exist, Shadow also needs the person's account in its own user list
  (Users) with the same email address; the first sign-in links the two. A person
  Shadow does not know gets a generic sign-in failure and no account is created.
- **Lost access.** The person uses the recovery flow on the sign-in page: it needs a
  link sent by email and an existing second factor. An operator can reset a person
  in the Authentik administration (Directory, Users); verify the person's identity before
  removing their second-factor devices.
- **Removing access.** Delete or deactivate the person in Users (Shadow) and in
  Authentik; recovery does not reactivate a deactivated person. Revoking sessions in Shadow ends their Shadow sessions at once.
- **Local development.** See [authentik-local](../runbooks/authentik-local.md).

Further sections (companies, roles, billing, AI connections) are added by the
features that introduce them.
