# TASK-039A Authentication Architecture ADR

Status: Implemented

## Source Plan

Approved plan: use Microsoft Entra ID in production, a dedicated Entra
development tenant for integration testing and Dockerized Authentik for daily
local development. Shadow will use one provider-neutral OIDC contract and a
backend-managed application session.

The plan was amended for `draft-ietf-oauth-browser-based-apps-27`: because the
React application and API share one public origin and Shadow does not forward
provider access tokens to another resource server, this is a confidential OIDC
web application with a traditional server-side session, not a full OAuth BFF.

## Goal

Create and obtain human acceptance for ADR-004 before authentication code,
schema or infrastructure is implemented. The ADR must make the authentication,
identity-linking, authorization and deployment security boundaries
decision-complete for the remaining TASK-039 work.

## Requirements

- Add `docs/adr/0004-authentication.md` with status `Proposed` for
  human review; implementation tasks may start only after it is changed to
  `Accepted` by the developer.
- Record these environment roles:
  - local development: repository-managed Authentik in Docker Compose
  - integration/pre-production: dedicated single-tenant Entra development
    tenant
  - production: single-tenant Microsoft Entra ID
- Define FastAPI as a confidential OIDC relying party using Authorization Code
  with PKCE, exact redirect URI matching, discovery, state and nonce.
- Define React-to-FastAPI authentication as an opaque server-side application
  session cookie. Provider access, refresh and ID tokens are never exposed to
  React or browser storage and are discarded after identity establishment.
- Define the public auth interface under `/api/v1/auth`: browser-navigation
  `GET /login`, provider `GET /callback`, session-restoration `GET /session`
  and CSRF-protected `POST /logout`. Logout returns a trusted provider logout
  URL or null after the local session has already been destroyed.
- Record that this is not the OAuth BFF token-forwarding pattern described in
  draft revision 27. Reference revision 27 and RFC 9700 as the current security
  guidance.
- Define one HTTPS public origin in staging and production: the frontend serves
  the SPA and reverse-proxies `/api` to FastAPI. Record that this extends the
  deployment topology in ADR-003 without changing its release-migration rules.
- Select a Caddy-based production frontend/static-server container as the
  same-origin reverse proxy. Keep the Caddyfile repository-owned and
  provider-neutral; Coolify assigns the public domain only to this service.
  Coolify's edge proxy terminates public TLS and forwards internal HTTP to
  Caddy, so the application Caddy container does not obtain certificates or
  publish ports 80/443 itself.
- Define the session contract:
  - a CSPRNG-generated opaque identifier with at least 256 bits of entropy;
    only its SHA-256 hash is persisted
  - eight-hour absolute lifetime, a 30-minute idle timeout and rotation after
    successful login; activity persistence may be coalesced for at most five
    minutes without extending either timeout
  - production cookie is `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, has
    no `Domain`, and uses a `__Host-` prefix
  - local HTTP omits `Secure` and the prefix but retains the other controls
  - `SameSite=Lax` requires a documented browser/provider compatibility failure
    and a reviewed ADR amendment; it is not an implementation-time default
- Require the backend to enforce a session-bound CSRF header for every
  authenticated unsafe request (`POST`, `PUT`, `PATCH` and `DELETE`) plus exact
  configured-origin validation. Missing and `null` origins fail closed and
  token comparison is constant-time. `SameSite` alone is not the CSRF defense.
- Bind every OIDC login transaction to the initiating browser with a separate,
  short-lived pre-authentication cookie. A browser may reuse the same binding
  for at most five live login transactions; the first callback with valid state
  and binding destroys the cookie, making the other transactions unusable.
  Persist only its hash with each transaction, destroy it before creating a
  fresh authenticated session, and never promote it into the application
  session.
  The production pre-authentication cookie is `Secure`, `HttpOnly`,
  `SameSite=Lax`, host-only and `Path=/`; local HTTP omits only `Secure`.
- Define provider-neutral identity as exact `(issuer, subject)` and Shadow's
  database role as the authorization source. Do not use email, Entra `oid` or
  `tid`, Authentik groups, or provider roles as the durable application key.
- Record the guarded first-link rule: a validated identity without a mapping
  may atomically link only to one active, admin-created user with the same
  normalized email and no identity for that issuer. Never automatically
  relink an existing binding after an email or provider-account change.
- Record that Entra email is mutable, may be absent and has no generally usable
  `email_verified` claim. Its validated single-tenant assertion is accepted
  only for the guarded first link; Authentik fixtures must mark their seeded
  email addresses verified.
- Record the explicit risk acceptance for email first-linking: Shadow is for
  a small company with tenant administrators trusted to control Entra email
  assignments, so a validated single-tenant Entra email match is considered
  sufficient for the one-time link. Email is never used after the permanent
  `(issuer, subject)` binding exists. Revisit this decision before expanding
  beyond that trust boundary or admitting external/guest identities.
- Define initial authorization:
  - health and required auth initiation/callback endpoints are public
  - all business APIs require an active session
  - Users administration APIs require the application `admin` role
  - `admin` and `consultant` may use every other API and access every
    organisation
  - record that this is intentional for an internal tool whose users are all
    trusted across organisations, not an accidental missing object-level check;
    organisation membership is needed only if that trust model changes
- Define local and provider logout boundaries. Local session termination is
  guaranteed; provider end-session redirect is best effort. Back-channel
  logout and immediate provider-side revocation are follow-up work.
- Explicitly approve Authlib as the one new backend runtime dependency for
  TASK-039C. No frontend OIDC library is needed.
- Document the security limitation that an application session can remain
  valid after provider-side disablement until its eight-hour expiry, unless
  the Shadow user is disabled sooner.
- Require an admin-only operation to revoke every application session for a
  selected Shadow user. Revocation and the idle timeout limit application
  sessions but do not claim immediate provider-side logout or revocation.
- Pin the expected OIDC issuer separately from discovery, require discovery to
  return that exact issuer, allow only explicitly configured asymmetric ID-token
  signing algorithms (initially `RS256`), and reject unsigned or symmetric ID
  tokens. Redirects are constructed only from the fixed public origin.
- Require an exact public Host allowlist, no permissive credentialed CORS, and
  trust forwarded scheme, host and client-address headers only across the
  documented Coolify-to-Caddy-to-FastAPI proxy chain. Caddy overwrites those
  forwarded headers; it preserves the browser-supplied `Origin` for FastAPI's
  exact validation.
- Require bounded public-auth endpoint rate limiting and a maximum of five live
  login transactions per pre-authentication browser binding. The initial
  single-backend limits are 20 login starts and 60 callback attempts per minute
  per trusted client address; excess requests return `429` without provider
  interaction.
- Require auth/session responses to use `Cache-Control: no-store`. Every
  callback with valid state and browser binding consumes its transaction and
  returns a `303` to a clean relative success or error URL. Invalid callbacks
  also return `303` to one fixed generic local error URL without consuming any
  transaction located only by attacker-controlled data. Caddy access logs must
  redact `code`, `state`, `error` and `error_description` query values, and
  backend logs must never contain them.
- Require production Caddy security headers: one-year HSTS without
  `includeSubDomains`, `Referrer-Policy: no-referrer`,
  `X-Content-Type-Options: nosniff`, frame denial and an enforced
  repository-owned CSP compatible with the built frontend. CSP must at minimum
  restrict scripts and connections to self and deny objects, framing and base
  URI injection.
- Do not implement code, migrations, Compose services or provider resources.

## Acceptance Criteria

- [ ] ADR-004 records every decision above and has no unresolved implementation
      choice.
- [ ] The ADR distinguishes same-origin OIDC session authentication from an
      OAuth token-forwarding BFF.
- [ ] The ADR cites revision 27 rather than revision 26.
- [ ] The identity-link and initial authorization rules agree with Users
      Domain ownership.
- [ ] The ADR explains how its same-origin ingress decision extends ADR-003.
- [ ] The ADR explicitly records the accepted all-organisation access and Entra
      email first-link trust assumptions and their reconsideration triggers.
- [ ] Login binding, global backend CSRF enforcement, session expiry/revocation,
      OIDC validation, rate limiting, proxy trust, log redaction and browser
      security headers have no unresolved implementation choice.
- [ ] Human review changes ADR-004 to `Accepted` before TASK-039B through
      TASK-039G begin.
- [ ] No application, schema, deployment or local-runtime behavior is changed.

## Out Of Scope

- Implementing authentication, sessions, user linking or authorization.
- Adding Authentik, Caddy or Entra resources.
- Organisation membership, tenant-scoped permissions or provider group mapping.
- Microsoft Graph or another delegated downstream API.

## Implementation Notes

- Read `AGENTS.md`, `docs/architecture/overview.md`, ADR-001, ADR-003,
  `docs/architecture/domains/USERS.md`, `docs/architecture/data/DATA-MODEL.md` and this task.
- Human ownership of architecture and security means an AI agent may draft the
  ADR but must not silently treat an unreviewed `Proposed` ADR as accepted.
- Use these primary references:
  - `https://datatracker.ietf.org/doc/draft-ietf-oauth-browser-based-apps/27/`
  - `https://www.rfc-editor.org/rfc/rfc9700`
  - Microsoft identity-platform OIDC and token-validation documentation
  - Authentik OAuth2/OIDC provider documentation

## Testing

Required:

- [ ] Documentation consistency and link verification
- [ ] Human architecture and security review

Not applicable:

- [ ] Backend/frontend tests, lint, build and typecheck: documentation-only
      task.

## Documentation

Add `docs/adr/0004-authentication.md`. Do not update
`docs/architecture/overview.md` to claim authentication is implemented.

## Notes For AI Agent

- Toteuta vain ADR-dokumentti.
- Ala aloita TASK-039B:n tai myohempien taskien toteutusta.
- Ala hyvaksy arkkitehtuuri- tai tietoturvapaatosta ihmisen puolesta.
