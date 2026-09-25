# Users Domain

Status: identity, session and API authorization implemented

## Purpose

Users Domain hallitsee Schattenin sovelluskayttajia, kayttajan sovellusroolia,
ulkoisten tunnusten pysyvia sidoksia ja palvelinpuolen kirjautumisistuntoja.

Tama domain toimii source of truth -kerroksena sovelluksen omille user-riveille.
OIDC-provider todentaa ulkoisen identiteetin, mutta aktiivinen User-rivi ja sen
tietokantarooli ratkaisevat sovellukseen pääsyn.

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

- Microsoft Entra ID configuration and OIDC protocol adapters
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
- Sessions have a 30-minute idle and fixed eight-hour absolute maximum
  lifetime. Administrator revocation and User soft deletion invalidate access
  without depending on provider logout.

## Audit References

Core tables may reference `users.user_id` through nullable audit columns:

- `created_by`
- `modified_by`
- `deleted_by`

Kentät pysyvät nullable-muotoisina historiallisille, seed- ja
pre-authentication-riveille. Nykyiset autentikoidut sovellusmutaatiot kirjoittavat
actorin: `created_by` luontiin, `modified_by` päivityksiin ja domain-muutoksiin
sekä `deleted_by` soft deleteen. Historiallisia null-arvoja ei backfillata.

## Authorization

- Kaikki Users-hallinnan list/get/create/update/delete-operaatiot vaativat
  aktiivisen istunnon ja tietokannan `admin`-roolin.
- Aktiivinen käyttäjä saa oman profiilinsa `/api/v1/auth/session`-endpointista.
- `POST /api/v1/users/{user_id}/sessions/revoke` on admin-only ja poistaa
  atomisesti valitun aktiivisen käyttäjän kaikki sovellusistunnot.
- Käyttäjän soft delete estää olemassa olevan istunnon käytön heti seuraavassa
  pyynnössä.

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
GET    /api/v1/users
GET    /api/v1/users/{user_id}
POST   /api/v1/users
PATCH  /api/v1/users/{user_id}
DELETE /api/v1/users/{user_id}
POST   /api/v1/users/{user_id}/sessions/revoke
```

Exact HTTP operations and versioned paths are defined in backend implementation tasks.

---

# Dependencies

Depends On:

- the provider-neutral FastAPI OIDC adapter
- tenant-specific Microsoft Entra ID directly in both environments under
  [ADR-013](../decisions/ADR-013-shared-entra-local-https-deployment.md), using
  the shared confidential registration and separate environment secrets
- local Caddy/direct Entra is the checked-in development runtime

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

## Bootstrap First Production Administrator

After migrations and production reference-data seeding, an operator may run the
database-only interactive `python -m app.bootstrap_admin` command once from a
private terminal. The command reuses User name/email validation, fixes the role
internally to `admin`, and creates one active User only when the entire `users`
table is empty, including soft-deleted rows. The emptiness check and insert are
one transaction serialized against other User writers.

Bootstrap audit actors are null because no authenticated application actor can
exist yet. The command never creates an identity or session, never updates,
revives or promotes an existing User, and never runs during application startup.
The first direct-Entra login performs the normal guarded email discovery and
permanent identity link. All subsequent Users are managed through the existing
authenticated admin API/UI.

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
- keep historical audit user references nullable while requiring actor writes
  from current authenticated mutations
- do not add Entra ID behavior without an auth-specific task or ADR

Avoid:

- modifying organisation, scenario or graph tables directly from Users Domain
- hardcoding identity provider assumptions outside approved auth work

---

# Trust Boundary

Both application roles are internal trusted users with access to all
non-Users business domains and all organisations. Revisit ADR-004 before
admitting users outside this boundary or adding organisation isolation.

Direct-Entra first linking in both environments accepts a validated tenant email
only to find one pre-provisioned active User. Missing email prevents first link;
exact `(issuer, subject)` is permanent afterward. There is no provider group
mapping, Graph access, refresh token, back-channel logout or immediate IdP
revocation.
Use exact tenant-specific issuer and `openid profile email`; an `email_verified`
claim is not required. Preserve old Authentik identity rows unchanged when local
runtime migrates; new Entra identities use the same guarded linking rules.
TASK-059B provides explicit local-only administrator provisioning on seeded dev
databases; TASK-059D's production bootstrap still requires an empty users table.
Login creates no Users, and database roles remain authoritative.
