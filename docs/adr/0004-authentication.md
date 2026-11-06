# ADR-004: Authentication, Identity And Session Architecture

Status: Accepted

Date: 2026-08-14

Partial supersession: ADR-005 removes the integration/pre-production environment
and dedicated Entra development tenant from the active model. The OIDC,
identity, session, authorization and production Entra decisions in this ADR
remain active. Historical environment text below is retained as decision
history.

Further partial supersession: amended
[ADR-013](0013-shared-entra-local-https-deployment.md) selects direct Entra in
both environments, one shared confidential registration, distinct secrets and
HTTPS origins. Local Authentik and separate-registration/callback policies below
are historical. Exact tenant issuer, guarded first-link, permanent identity,
sessions and database authorization remain active. Direct Entra uses
`openid profile email`, no Graph calls and no `email_verified` requirement in
both environments. Local runtime migration remains pending TASK-059B.

---

# Context

ADR-001 selected Microsoft Entra ID as Shadow's production identity
provider, but it did not decide the browser authentication flow, application
session model, durable identity key, authorization baseline or local identity
provider. Those choices must be fixed before authentication code, schema,
provider resources or deployment changes are implemented.

Shadow is a first-party internal web application. Its React frontend and
FastAPI API share one public origin, and FastAPI does not use an OAuth access
token to call Microsoft Graph or another resource server. The browser therefore
does not need provider tokens. The backend can establish identity with OIDC and
then maintain a traditional server-side application session.

The initial users are employees of a small company. The same trusted person
administers Entra accounts and the Shadow user allowlist, and every Shadow
user is trusted to work across every organisation. These are explicit security
and authorization assumptions, not general-purpose multi-tenant guarantees.

This ADR has completed human architecture and security review and is
`Accepted`. That acceptance permits TASK-039B through TASK-039G to begin; it
does not claim that any authentication behavior is implemented yet.

# Decision

## Architecture Classification

FastAPI is a confidential OpenID Connect relying party. It uses OIDC only to
establish a user's identity and then creates its own opaque, server-side
application session. React calls FastAPI with the application session cookie;
it is not an OIDC or OAuth client.

This is the common-domain OIDC authentication plus traditional session pattern
described in section 7.1 of
`draft-ietf-oauth-browser-based-apps-27`. It is not the OAuth BFF pattern from
section 6.1 of that draft. A BFF retains provider access and refresh tokens and
forwards calls to a separate resource server with an access token. Shadow
does neither: provider access, refresh and ID tokens are discarded after the
validated identity has been resolved, and its API is the same application's
trusted backend.

Revision 27 of the browser-based applications draft and RFC 9700 are the
current security guidance for this decision. The Internet-Draft remains work
in progress, so a material change before implementation requires review.

## Environment Roles

The same provider-neutral backend contract is used in every environment:

| Environment | Identity provider | Role |
| --- | --- | --- |
| Daily local development | Repository-managed Authentik in Docker Compose | Reproducible development identities without production credentials |
| Integration and pre-production | Dedicated, single-tenant Entra development tenant and app registration | Provider compatibility and deployment rehearsal |
| Production | Single-tenant Microsoft Entra ID and a separate production app registration | Production workforce authentication |

Authentik is local-only and must not appear in staging or production release
manifests. The Entra development and production registrations are confidential
web applications, not SPA registrations. Each environment has its own exact
issuer, client ID, client secret, redirect URI and post-logout URI. Provider
configuration changes; the application protocol and normalized identity
contract do not.

The Entra registrations request only `openid profile email`. They do not
request `offline_access`, Microsoft Graph permissions, provider groups or
provider roles. Entra authentication alone does not grant Shadow access: the
active, pre-provisioned Shadow Users table is the application access
allowlist. The same trusted person administers both Entra and Shadow and adds
only intended internal staff with the appropriate email to Shadow. This
baseline does not require Entra application-assignment filtering. An Entra
account, including a guest account, without an active matching Shadow user
may authenticate at Entra but cannot establish a Shadow identity or session.
Provisioning an external or guest identity as a Shadow user is outside the
accepted trust boundary and requires this decision to be revisited first.

## Public Authentication Interface

FastAPI owns the complete public interface under `/api/v1/auth`:

| Method and path | Authentication | Contract |
| --- | --- | --- |
| `GET /login?return_to=/...` | Public | Starts a browser navigation login and returns `302 Found` to the provider |
| `GET /callback` | Public | Processes the provider response and always returns a clean local `303 See Other` redirect |
| `GET /session` | Public transport endpoint | Returns the active application session or `401` |
| `POST /logout` | Active session plus CSRF | Destroys the local session, then returns a trusted provider logout URL or null |

`return_to` is optional and defaults to `/`. It must be a local absolute path
that begins with exactly one `/`. Protocol-relative values, absolute URLs,
backslashes, fragments, control characters and malformed encodings are
rejected. A validated value is persisted in the login transaction; redirects
are never built from an unvalidated request value.

An authenticated `GET /session` response is:

```json
{
  "user": {
    "id": 101,
    "name": "Example User",
    "email": "user@example.com",
    "role": "consultant"
  },
  "csrfToken": "opaque-session-bound-value"
}
```

An anonymous request uses the repository error envelope with HTTP `401`, code
`AUTHENTICATION_REQUIRED` and the generic message `Authentication required`.
Authentication failures do not disclose whether a provider identity, email or
Shadow user exists.

`POST /logout` returns the following only after local session deletion and
cookie expiry have succeeded:

```json
{
  "logoutUrl": "https://trusted-provider.example/end-session?..."
}
```

`logoutUrl` is a string or `null`; it is never supplied by the browser.

## OIDC Login And Token Validation

FastAPI uses Authorization Code flow with confidential-client authentication
and S256 PKCE. Authorization requests use `response_type=code`,
`response_mode=query`, scopes `openid profile email`, and independent `state`,
`nonce` and PKCE verifier values. Each value is generated by a CSPRNG with at
least 256 bits of entropy. Redirect URIs are registered and compared with exact
string matching.

All redirect and post-logout URIs are constructed from one fixed configured
public origin, never from `Host`, `Forwarded`, `X-Forwarded-*`, `Origin` or
request query values. Production and Entra endpoints use HTTPS. Plain HTTP is
allowed only for documented local origins. ADR-006 supersedes this for
Authentik specifically by requiring `https://auth.localhost:9443`; Shadow's Vite
origin remains local HTTP.

Configuration contains both a discovery URL and a separately pinned expected
issuer. The discovery document must return that exact issuer using
case-sensitive string equality or startup/login fails closed. Generic Entra
authorities such as `common`, `organizations` and `consumers` are forbidden;
the Entra discovery URL and expected issuer are tenant-specific.

Authlib performs discovery and ID-token validation. It is configured with an
explicit asymmetric signing-algorithm allowlist, initially exactly `RS256`.
The implementation must not choose an algorithm from the token header alone.
Unsigned tokens, `none`, every `HS*` symmetric algorithm and every other
unconfigured algorithm are rejected. Signing keys come only from the JWKS URI
in the already validated discovery metadata, including normal key rotation.

Before identity establishment, validation must cover at least:

- signature against the discovered provider keys
- exact `iss` against the separately configured expected issuer
- `aud` containing the configured client ID, with `azp` equal to that client ID
  when multiple audiences or `azp` are present
- required, non-blank, case-sensitive `sub`
- `exp`, and `nbf` and `iat` when present, with at most 60 seconds of clock skew
- exact constant-time comparison of the returned `nonce` with the transaction
  nonce

The authorization code is redeemed only with the exact configured redirect URI
and the transaction's PKCE verifier. Provider-specific claim extraction is
contained in an adapter that produces only `issuer`, `subject`, `email` and
`name`. Provider tokens, authorization codes and PKCE material are never
returned to React, put in browser storage, retained in the application session
or persisted after identity establishment. Shadow does not call UserInfo or
Microsoft Graph.

## Browser-Bound Login Transactions

OIDC `state` alone is not used as proof that the callback browser initiated the
flow. `/login` also creates or reuses a separate raw 256-bit CSPRNG
pre-authentication browser binding. Only its SHA-256 hash is stored with each
login transaction.

A transaction has a ten-minute absolute lifetime and contains:

- the SHA-256 hash of its independent 256-bit `state`
- the SHA-256 hash of the pre-authentication browser binding
- independent 256-bit `nonce` and S256 PKCE verifier values
- the validated relative `return_to` path
- creation and absolute-expiry timestamps

No transaction contains a provider token or application session identifier.
At most five unexpired transactions may exist for one browser binding. The
binding may be reused until its first valid callback or its ten-minute cookie
lifetime expires. A sixth live transaction is rejected with `429 Too Many
Requests` without provider interaction.

The pre-authentication cookie is named `shadow-preauth`. In production it is
`Secure`, `HttpOnly`, `SameSite=Lax`, host-only, `Path=/` and
`Max-Age=600`; it has no `Domain`. Local HTTP omits only `Secure`. The cookie is
never exposed to React and is never promoted or reused as the application
session.

Callback handling requires both a matching hashed state and a constant-time
matching binding hash. Once both are valid, the backend atomically consumes
that transaction, deletes all other transactions for the same binding and
expires the pre-authentication cookie before creating a fresh, unrelated
application session. Thus the first valid callback makes every parallel flow
under that binding unusable. Expired, replayed, swapped or mismatched values
fail closed.

A callback with valid state and browser binding is consumed even if the
provider returned an error or the subsequent token/identity step fails. It
returns `303 See Other` either to the stored clean success path or to the fixed
generic local error path `/login?error=authentication_failed`. An invalid
callback also redirects to that fixed error path, but it must not consume or
alter a transaction found only through attacker-controlled callback data.
Callbacks never render provider values or third-party content.

## Durable Identity And Guarded First Link

The durable provider-neutral identity key is the exact, case-sensitive pair:

```text
(issuer, subject)
```

It maps to one application-wide user owned by Users Domain. Email, name, Entra
`oid`, Entra `tid`, Authentik groups and provider roles are not durable identity
or authorization keys. The application database remains the sole source for
the Shadow role.

Identity resolution is atomic:

1. If exact `(issuer, subject)` already exists, use its linked active Shadow
   user without consulting email.
2. Otherwise, require a non-blank normalized provider email and find exactly
   one active, admin-created Shadow user with the same trimmed,
   case-insensitive email.
3. The candidate must have no existing identity for this issuer, and the
   `(issuer, subject)` must still be unbound when the transaction commits.
4. Create the permanent binding once. Missing, zero, multiple, inactive,
   conflicting or already-bound candidates fail generically.

Here, `admin-created` is an operational provisioning guarantee, not a
`users.created_by` database predicate. In integration and production, the
trusted Shadow administrator must create the user before that person can
first-link. Existing administrator-provisioned bootstrap rows may have a null
`created_by`. Repository-managed local development seed users are an explicit
exception: they count as pre-provisioned users even though no administrator
created them and their `created_by` is null. Identity resolution therefore
checks that the user already exists, is active, has the matching normalized
email and has no identity for the issuer; it does not require non-null
provenance.

Authentication never creates a Shadow user. A changed provider account or
email can never automatically move, replace or relink an existing binding. An
administrator must investigate and use a future explicit recovery process;
deleting and silently rebuilding a binding is not part of this decision.

Microsoft documents that Entra `email` is optional, mutable and unsuitable as
a durable identity or authorization key. Entra also has no generally usable
`email_verified` claim for this workforce flow. After full single-tenant token
validation, Shadow nevertheless accepts the Entra email assertion only for
the one-time guarded first link. Missing email prevents first link. Authentik
development fixtures must emit `email_verified=true`; an unverified Authentik
email cannot first-link.

This limited Entra email use is an explicit risk acceptance. Shadow is
initially for a small company where the same trusted administrator controls
Entra accounts and the Shadow user allowlist. That administrator adds only
internal staff emails to Shadow. A validated single-tenant assertion,
combined with an active pre-created user and the atomic no-existing-binding
guards, is considered sufficient for that one-time link. Email is never
consulted again after `(issuer, subject)` exists. This choice must be revisited
before the company trust boundary expands, Entra and Shadow administration
are separated, user provisioning becomes self-service, or external/guest
identities are added to Shadow.

## Application Session Contract

After a successful identity resolution, FastAPI deletes any application
session presented by that browser and creates a new session using an unrelated
CSPRNG identifier with at least 256 bits of entropy. Only `SHA-256(raw session
identifier)` is persisted. The raw value exists only in the browser's
HttpOnly cookie. Session rotation at login prevents fixation.

Each session also has an independent CSPRNG CSRF token with at least 256 bits
of entropy, its user ID, creation time, last-activity time and fixed absolute
expiry. The CSRF token may be persisted directly because it is not an
authentication credential without the separate HttpOnly cookie. React keeps
the value only in memory and restores it through `GET /session`; it is never
stored in localStorage or sessionStorage.

The server enforces both:

- an eight-hour absolute lifetime measured from session creation
- a 30-minute idle timeout measured from last accepted activity

Either boundary expires and deletes the session. The absolute expiry never
moves. A last-activity persistence write may be coalesced only until five
minutes have elapsed since the previous persisted activity. Coalescing may
shorten the effective idle window by at most five minutes; it must never add
time to the idle or absolute deadline.

The production cookie is named `__Host-shadow-session` and has `Secure`,
`HttpOnly`, `SameSite=Strict`, `Path=/`, host-only scope, no `Domain` and
`Max-Age=28800`. Local HTTP uses `shadow-session`, omits `Secure` and the
`__Host-` prefix, and retains all other controls. Cookie deletion repeats the
same name, path and security attributes.

`SameSite=Strict` is the implementation baseline. It may change to
`SameSite=Lax` only after a documented supported-browser/provider compatibility
failure and human review of an ADR amendment. It is not an implementation-time
configuration default or the primary CSRF defense.

Every authenticated request reloads the user sufficiently to reject a
soft-deleted user and use the user's current database role. Provider-side
disablement does not synchronously revoke an application session. Unless a
Shadow administrator disables the user or revokes their sessions sooner, an
already established session can remain usable until its idle or eight-hour
absolute expiry. This limitation is accepted and must be visible in operator
documentation.

An admin-only operation at
`POST /api/v1/users/{user_id}/sessions/revoke` atomically deletes all
application sessions for the selected active Shadow user and returns `204 No
Content`. It uses the same session, authorization, Origin and CSRF checks as
other unsafe operations. It limits Shadow sessions only and does not claim
provider logout or token revocation.

## CSRF And Origin Enforcement

FastAPI applies one reusable global unsafe-request guard to every authenticated
`POST`, `PUT`, `PATCH` and `DELETE`, including logout and session revocation.
It requires both:

- `X-CSRF-Token` equal to the current session's CSRF token, compared in
  constant time
- `Origin` exactly equal to the configured public origin, including scheme,
  host and port

Missing `Origin`, the literal `null`, multiple Origin values, malformed values,
missing CSRF and mismatched CSRF all fail closed with `403 Forbidden`. Caddy
preserves the browser-supplied `Origin` unchanged for this check. `SameSite`
cookies are defense in depth, not the CSRF mechanism.

Staging and production do not enable CORS. Local development may enable
credentialed CORS only for its one exact configured application origin when
the documented Vite topology requires it. Wildcard origins, origin reflection
and permissive credentialed CORS are forbidden.

## Initial Authorization

> [ADR-017](0017-use-self-hosted-authentik-for-identity.md) replaces the direct Microsoft Entra sign-in described in this ADR with self-hosted Authentik (the guarded email linking, sessions and CSRF stay).
>
> [ADR-016](0016-introduce-tenants-memberships-and-rls.md) replaces this section with tenants, memberships and row-level security.

FastAPI is the trusted authorization boundary. Frontend visibility checks are
only user-experience aids.

- The health endpoint, `/api/v1/auth/login`, `/api/v1/auth/callback` and the
  session-restoration transport endpoint are public. `/session` returns `401`
  when no active session exists.
- `/api/v1/auth/logout` requires an active session and the unsafe-request guard.
- Every business API requires an active session.
- Every Users administration API, including session revocation, requires the
  database `admin` role.
- Both `admin` and `consultant` may use every other business API and read or
  modify resources in every organisation.

All-organisation access is intentional for an internal tool whose users are
trusted across organisations. It is not an omitted object-level authorization
check, and route `orgId` values do not create membership. Organisation
membership is unnecessary under this baseline. The authorization architecture
must be revisited before admitting users outside this trust model or requiring
organisation isolation; provider groups or roles must not be substituted for
that future application decision.

## Authentication Enablement And Release Boundary

TASK-039C introduces login and first-linking, while TASK-039D makes Users
administration admin-only and protects the other business APIs. There is no
supported shared or deployed runtime in which TASK-039C authentication is
enabled without TASK-039D authorization.

TASK-039C and TASK-039D may be implemented and reviewed in separate branches,
but they form one runtime cutover. Their combined result must be deployed or
enabled as one release in integration, pre-production and production. An
automatic deployment after TASK-039C must be paused. OIDC configuration and
public login must remain disabled or unreachable until the release also
contains TASK-039D.

At the first externally reachable login, all business APIs must already require
an active session, every Users administration operation must already require
the application `admin` role, and all authenticated unsafe operations must
already enforce Origin and CSRF. This prevents a caller from creating or
promoting a matching Shadow user through an anonymous Users API before
first-linking. Isolated automated tests may exercise TASK-039C before TASK-039D;
an interactive or shared environment may not.

## Logout Boundaries

Local application logout is guaranteed: the backend first deletes the current
session and expires its cookie, then returns a response. Provider logout is a
best-effort browser navigation performed afterward by React.

A non-null logout URL is built only when validated discovery supplies a usable
provider `end_session_endpoint`. The backend combines that trusted endpoint
with the configured client ID and the exact post-logout URI
`<public-origin>/login`; it does not include an ID-token hint because ID tokens
are discarded. It accepts no browser-supplied endpoint, return URI or query
parameter. When the provider lacks a usable endpoint, the response contains
`null` and the user remains locally logged out.

Back-channel logout, continuous access evaluation and immediate provider-side
revocation are follow-up work. Provider logout success does not revoke other
Shadow sessions, and Shadow session revocation does not promise to end the
provider session.

## Same-Origin Deployment And ADR-003

Staging and production expose exactly one HTTPS public application origin. A
Caddy-based production frontend/static-server container serves the built React
SPA and reverse-proxies `/api` to the internal FastAPI service. Only this Caddy
service receives the public domain in Coolify. Backend, migration and database
ports remain private.

Coolify's edge proxy terminates public TLS and forwards internal HTTP to Caddy.
The application Caddy container listens on one unprivileged internal HTTP port;
it does not obtain certificates and does not publish container ports 80 or 443.
The repository owns a provider-neutral Caddyfile. Authentik is not part of this
release topology.

This extends ADR-003 by adding an immutable frontend/Caddy release artifact and
making it the public ingress. It does not replace or modify ADR-003's backend
artifact or release-migration rules:

- the API and one-shot migration job continue to use the same immutable
  backend image and `DATABASE_URL`
- migration failure still prevents backend startup
- the frontend starts only after the migration-gated backend is healthy
- migrations remain forward-only, provider-neutral and separate from FastAPI
  startup

Caddy and FastAPI each reject a public `Host` that is not the exact host
derived from the configured public origin. Application redirects still use the
fixed origin even after Host validation.

## Proxy Trust Boundary

Forwarded scheme, host and client-address data is trusted only across this
explicit chain:

```text
browser -> configured Coolify edge CIDRs -> Caddy -> configured Caddy CIDRs -> FastAPI
```

Caddy trusts proxy data only when its immediate peer is in the deployment's
explicit Coolify edge CIDR allowlist. It strips browser-supplied `Forwarded`,
`X-Forwarded-*` and `X-Shadow-Client-IP`, derives the client address through
that trusted edge boundary, and overwrites the headers sent to FastAPI. The
forwarded host is the exact configured public host and the forwarded scheme is
the validated public scheme. It preserves the browser-supplied `Origin`
unchanged.

FastAPI trusts `X-Shadow-Client-IP` and other forwarded data only when its
immediate peer is in the configured internal Caddy CIDRs. A forwarded header
from any other peer is rejected rather than ignored. Neither layer trusts all
private networks or an unrestricted proxy-hop count.

## Rate Limits, Caching And Sensitive Data

The initial single-backend deployment uses separate fixed one-minute windows
per trusted client address:

- 20 `/login` starts per minute
- 60 `/callback` attempts per minute

The check occurs before provider redirect, discovery refresh, token exchange or
other provider interaction. Excess requests return `429 Too Many Requests`.
The in-process limiter holds at most 10,000 address/window entries; expired
entries are removed opportunistically, and a new address is rejected with
`429` while the bound is full. Multiple backend replicas require a shared
limiter and an architecture review before rollout.

All `/api/v1/auth` responses, including redirects and errors, carry
`Cache-Control: no-store`. They must not be cached by the browser, Caddy or an
intermediary.

Caddy access logging retains normal request metadata but replaces every value
of the query keys `code`, `state`, `error`, `error_description` and Entra's
`session_state` with `REDACTED` on every path. It retains credential-header
redaction and never logs cookies or authorization values. FastAPI does not log
callback query strings and never logs those values, provider tokens, PKCE
verifiers, client secrets, raw session or pre-authentication cookies, CSRF
tokens or personal email. Error responses contain generic local codes and
messages, not provider descriptions.

## Browser Security Headers

The production repository-owned Caddyfile sets these response headers for the
SPA and applicable same-origin responses:

```text
Strict-Transport-Security: max-age=31536000
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'
```

HSTS deliberately omits `includeSubDomains` and `preload`. CSP is enforced, not
report-only. The narrow `style-src 'unsafe-inline'` allowance is required by
the current React inline style attributes, and `img-src data:` is required by
the current repository-owned CSS image. New external script, connection,
frame, object or base-URI sources require reviewed CSP and architecture changes.

## Dependency Decision

Authlib is explicitly approved as the one new backend runtime dependency for
TASK-039C. It owns OIDC discovery, protocol handling and token validation; the
application must not implement JWT validation manually. No frontend OIDC
library is needed or approved. Exact dependency and container versions remain
repository pins selected and reviewed in their implementation tasks.

# Options Considered

## Provider Tokens In React

Registering React as a public SPA client and storing tokens in browser memory or
web storage was rejected. React does not need a provider access token, and the
design would unnecessarily expose provider credentials to browser JavaScript.

## OAuth Token-Forwarding BFF

A BFF that retains tokens and forwards authenticated calls to Microsoft Graph
or another resource server was rejected because Shadow currently has no such
downstream API. Adding Graph or another delegated resource later requires a new
architecture decision.

## Entra For Daily Local Development

Using the Entra development tenant for every local login was rejected because
it makes normal development depend on network access, shared external state and
tenant credentials. Dockerized Authentik supplies the same OIDC contract
locally. Under ADR-005, direct Entra/Coolify compatibility is first validated by
the limited production smoke. ADR-006 adds an explicitly enabled
Authentik-to-Entra rehearsal without making it the daily default or treating it
as direct production compatibility evidence.

## Email, Entra Object IDs Or Provider Roles As Application Identity

Email is mutable and reusable, Entra `oid`/`tid` are provider-specific, and
provider roles or groups would move authorization ownership outside Users
Domain. These were rejected as durable Shadow keys. Exact `(issuer, subject)`
is provider-neutral and scoped correctly to the relying party.

## Signed Or Self-Contained Application Session Cookies

A cookie containing session or identity data was rejected. An opaque cookie
whose hash resolves to server-side state supports idle expiry, role refresh,
user disablement and administrator revocation without exposing trusted state to
React.

## SameSite=Lax Application Session By Default

`Lax` was rejected as the default because the application session is used only
same-origin after callback. `Strict` gives stronger defense in depth. The
separate short-lived pre-authentication cookie is `Lax` because it must bind the
cross-site top-level provider callback.

## Organisation Membership In The Initial Authorization Model

Membership and tenant-scoped permissions were rejected from this baseline
because all initial users are intentionally trusted across organisations.
They become necessary only when that trust assumption changes.

# Consequences

Benefits:

- React never handles provider tokens or acts as a trusted security boundary.
- Authentik and Entra use one backend OIDC and normalized identity contract.
- Exact issuer/subject identity survives email and display-name changes.
- Server-side sessions can be idled out, disabled through the user lifecycle
  and revoked by an administrator.
- Browser-bound login state, global CSRF checks, exact origins and a strict
  proxy chain provide layered request integrity.
- One public origin removes the need for production credentialed CORS and
  creates one place for Host checks, security headers and query redaction.

Costs and accepted limitations:

- Local development adds Authentik, a loopback TLS proxy and its dedicated
  database services.
- Staging and production add a Caddy frontend artifact and explicit proxy CIDR
  configuration.
- One-time Entra email matching depends on the stated small-company tenant
  administration trust assumption.
- Entra can authenticate an account that is not provisioned in Shadow; the
  application denies identity linking and session creation for that account.
- Both application roles intentionally have access to every organisation.
- Provider-side disablement is not immediate application-session revocation;
  an active session can survive until its 30-minute idle or eight-hour absolute
  expiry unless a Shadow user is disabled or their sessions are revoked.
- Provider logout is best effort; back-channel logout, continuous provider
  revocation, group mapping, Graph access and refresh tokens are not included.
- The bounded in-memory rate limiter constrains this baseline to one backend
  replica until a shared limiter is designed.

# Implementation Rules

- Do not implement TASK-039B or later work while this ADR is `Proposed`.
- Do not deploy or enable TASK-039C authentication in an interactive or shared
  environment until TASK-039D authorization is present in the same release.
- Do not expose, retain or log provider tokens or callback secrets.
- Do not add a frontend OIDC library or another backend auth dependency without
  approval.
- Do not infer application roles or organisation access from provider claims.
- Do not weaken `SameSite`, CSRF, Origin, issuer, Host or proxy checks through
  environment defaults.
- Do not add Authentik to release or Coolify manifests.
- Do not create Entra resources, enter production secrets or deploy production
  changes without human authorization.
- Keep ADR-003 migration gating and artifact portability intact.

# Follow-Up

After human acceptance, and in order:

1. TASK-039B adds the identity, login-transaction and session schema plus user
   email management.
2. TASK-039C implements backend OIDC, identity linking and application sessions
   with Authlib, but is not independently deployable or enableable.
3. TASK-039D protects business APIs, applies authorization and audit actors, and
   adds user-session revocation. TASK-039C and TASK-039D are then enabled in one
   runtime release.
4. TASK-039E adds the local Authentik environment.
5. TASK-039F adds React session restoration and authentication UX.
6. TASK-039G adds the production Caddy topology, Entra runbook, final diagrams
   and cross-provider security QA.
7. TASK-040 and ADR-006 add optional local Authentik-to-Entra federation.

TASK-039B through TASK-039G implement this decision. `docs/architecture/overview.md`,
`docs/architecture/deployment.md` and the authentication diagrams describe the resulting
runtime. Human architecture and security acceptance remains human-owned and an
AI agent must not alter it on the developer's behalf.

# References

- OAuth 2.0 for Browser-Based Applications, revision 27:
  `https://datatracker.ietf.org/doc/draft-ietf-oauth-browser-based-apps/27/`
- RFC 9700, Best Current Practice for OAuth 2.0 Security:
  `https://www.rfc-editor.org/rfc/rfc9700`
- OpenID Connect Core 1.0:
  `https://openid.net/specs/openid-connect-core-1_0.html`
- Microsoft identity platform OpenID Connect protocol:
  `https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc`
- Microsoft identity platform ID token validation:
  `https://learn.microsoft.com/en-us/entra/identity-platform/id-tokens`
- Microsoft identity platform ID token claims:
  `https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference`
- Authentik OAuth 2.0 and OIDC provider:
  `https://docs.goauthentik.io/add-secure-apps/providers/oauth2/`

# Related

- `docs/adr/0006-local-authentik-entra-federation.md`

- Related task: `docs/archive/tasks/TASK-039A-authentication-architecture-adr.md`
- Extends deployment topology: `docs/adr/0003-coolify-deployment.md`
- Technology decision: `docs/adr/0001-tech-stack.md`
- Users ownership: `docs/architecture/domains/USERS.md`
