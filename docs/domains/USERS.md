# Users Domain

Status: identity and session persistence baseline

## Purpose

Users Domain hallitsee Schattenin sovelluskayttajia, kayttajan sovellusroolia,
ulkoisten tunnusten pysyvia sidoksia ja palvelinpuolen kirjautumisistuntoja.

Tama domain toimii source of truth -kerroksena sovelluksen omille user-riveille. Microsoft Entra ID on tuleva ulkoinen identiteettilahde, mutta sen tarkka mappaus ei kuulu tahan taskiin.

---

# Responsibilities

Owns:

- application users
- user roles
- user email and soft-delete lifecycle
- provider-neutral external identity bindings
- browser-bound OIDC login transactions
- opaque application sessions

Provides:

- user lookup
- user role lookup
- audit user references for other core tables
- identity and session persistence services for the authentication layer

Does NOT Own:

- Microsoft Entra ID or Authentik configuration and protocol adapters
- organisation membership rules
- organisation data
- scenario or graph data

---

# Domain Rules

## Role Values

User `role` must be one of:

- `consultant`
- `admin`

## Email

- Every User has a trimmed, non-blank email.
- Active User emails are unique under case-insensitive comparison.
- A soft-deleted User's email may be reused by a new active User.
- Email is used only to discover a guarded first-link candidate. It is not a
  durable identity, session or authorization key.

## External Identity

- Exact, case-sensitive `(issuer, subject)` is the durable external identity.
- One `(issuer, subject)` can bind to only one User.
- One User can have at most one identity per issuer.
- Authentication never creates a User or silently relinks an identity.

## Login Transactions And Sessions

- Login transactions persist separate SHA-256 state and initiating-browser
  binding hashes, nonce, PKCE verifier, validated relative return path and a
  ten-minute absolute expiry.
- Application sessions persist only a SHA-256 session identifier hash, a
  session-bound CSRF token and timestamps for idle and absolute expiry.
- Provider tokens, raw session identifiers and client secrets are never stored.

## Audit References

Core tables may reference `users.user_id` through nullable audit columns:

- `created_by`
- `modified_by`
- `deleted_by`

Audit references remain nullable until authentication is implemented.

## Deletion

User deletion is a soft delete using `deleted_time`.

Normal reads should exclude rows where `deleted_time IS NOT NULL`.

---

# Database Ownership

Tables:

- users
- user_identities
- oidc_login_transactions
- auth_sessions

Owned exclusively by Users Domain.

Other domains may reference `users.user_id` from audit columns but may not modify user records directly.

---

# API Ownership

Endpoints:

```text
/users
```

Exact HTTP operations and versioned paths are defined in backend implementation tasks.

---

# Dependencies

Depends On:

- Microsoft Entra ID, when authentication is implemented

Referenced By:

- Organisations Domain
- Organisation States Domain
- Organisation Twin Structure Domain

---

# Common Workflows

## Create User

Flow:

1. Validate user name, email and role.
2. Confirm the normalized email is not used by another active User.
3. Create active user row.
4. Return user data.

## Soft Delete User

Flow:

1. Load active user.
2. Set `deleted_time`.
3. Set `deleted_by` when authenticated actor data exists.
4. Exclude user from normal reads.

---

# AI Agent Guidance

When implementing user features:

- read this document before changing user data, APIs or rules
- preserve role constraints
- keep audit user references nullable until authentication is implemented
- do not add Entra ID behavior without an auth-specific task or ADR

Avoid:

- modifying organisation, scenario or graph tables directly from Users Domain
- hardcoding identity provider assumptions outside approved auth work

---

# Open Questions

- organisation membership and authorization model
