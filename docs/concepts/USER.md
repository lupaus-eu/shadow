# User And Authentication Persistence Concepts

Status: identity, session and initial authorization implemented

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

The application session has a 30-minute idle timeout and a fixed eight-hour
absolute lifetime. Provider-side logout or disablement does not immediately
revoke it; Schatten User disablement or administrator session revocation does.

## Authorization And Audit Actors

The active User row is reloaded for each authenticated request so soft deletion
and current database role changes take effect immediately. The `admin` role is
required for all Users administration and session revocation; both roles may
use every other business domain across all organisations under the accepted
internal trust boundary.

User and other core rows retain nullable audit references for historical data.
Current authenticated mutations set creator, modifier and soft-deleter actors
as appropriate without backfilling earlier null values.

## Related Decision

- `docs/decisions/ADR-004-authentication.md`
- `docs/DEPLOYMENT.md`
- `docs/qa/AUTHENTICATION-QA-CHECKLIST.md`
