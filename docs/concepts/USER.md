# User And Authentication Persistence Concepts

Status: identity and session persistence baseline implemented

## Owner

Owning Domain: Users Domain.

Related domain document: `docs/domains/USERS.md`.

Owned tables: `users`, `user_identities`, `oidc_login_transactions` and
`auth_sessions`.

## User

A User is an application-wide Schatten access-allowlist entry. It has a
display name, required email, application role and soft-delete lifecycle.

Invariants:

- role is `consultant` or `admin`
- email is trimmed and non-blank
- active emails are unique under case-insensitive comparison
- soft deletion makes the email reusable
- email is not a durable identity or authorization key

Lifecycle:

```text
active -> deleted
```

## User Identity

A User Identity permanently binds one exact, case-sensitive provider-neutral
`(issuer, subject)` pair to one User. One pair cannot bind to multiple Users,
and one User cannot have two subjects for the same issuer. Normal
authentication never deletes, replaces or relinks a binding.

## OIDC Login Transaction

An OIDC Login Transaction is a ten-minute, atomically consumable record for one
browser-initiated authorization flow. It stores separate SHA-256 hashes of
state and the pre-authentication browser binding, plus nonce, PKCE verifier, a
validated relative return path, creation time and expiry. It stores no provider
token or application session identifier.

The expiry and browser-binding indexes support opportunistic cleanup and the
limit of five live transactions per initiating browser.

## Authentication Session

An Authentication Session is opaque server-side session state belonging to one
User. The database stores only the SHA-256 hash of the independent raw session
identifier, an independent session-bound CSRF token, creation and last-activity
times, and fixed absolute expiry. These timestamps support the 30-minute idle
and eight-hour absolute timeouts decided in ADR-004.

Provider tokens, raw session identifiers and client secrets are not session
fields. The CSRF token is not sufficient without the separate HttpOnly session
cookie.

## Related Decision

- `docs/decisions/ADR-004-authentication.md`
