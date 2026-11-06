# Authentication

## Provider

Self-hosted Authentik is the identity provider. It owns credentials, passkeys, MFA enrollment and validation, recovery flows, and identity sessions.

Yearclock integrates with Authentik through OpenID Connect. A User Account is linked to Authentik by the stable issuer and subject identifiers, never by email address alone.

## Authorization boundary

Authentik establishes who the user is. Yearclock remains authoritative for:

- User Account profiles
- Organizations and memberships
- Organization Owner and Admin roles
- Yearclock Editor and Viewer roles
- Billing and product entitlements

No customer-content authorization decision is delegated to Authentik groups or claims.

## Account classes

- A User Account is either a customer account or a Platform User.
- Customer accounts may have memberships in multiple Organizations.
- Platform Users may hold Platform Admin or Support Agent roles.
- Platform roles and Organization memberships never coexist on one User Account.
- Platform staff who use Yearclock as a customer use a separate customer account.

## Authentication policy

- Every Yearclock view requires authentication.
- Passkeys are preferred.
- Password sign-in requires a second factor.
- Password-only, anonymous, guest, and public-link access are prohibited.

## Operations

Authentik is critical production infrastructure and requires:

- pinned versions and tested upgrades
- PostgreSQL backups and restore tests
- working email delivery for verification and recovery
- monitoring and alerting
- protected secrets
- documented break-glass administration

Yearclock does not store customer passwords, passkeys, MFA secrets, or recovery credentials.

## Application session

- The browser starts an OpenID Connect authorization-code flow with PKCE, state, and nonce.
- Authentik ID tokens are signature checked against the provider JWKS and validated for issuer, audience, expiry, nonce, subject, and explicitly verified email.
- The backend reaches Authentik over the Compose network (`OIDC_INTERNAL_BASE_URL`, plain HTTP) and sends the public issuer's `Host` and `X-Forwarded-Proto`, so Authentik reports the same HTTPS issuer and endpoint URLs that `OIDC_ISSUER` names; without the scheme, discovery returns `http://` URLs and the issuer check fails.
- Yearclock persists one User Account for each stable issuer-and-subject pair. Email and display name remain profile attributes rather than identity keys.
- A successful callback creates a random, HTTP-only, same-site Yearclock session whose database record stores only a token hash.
- Missing, expired, or revoked sessions fail closed. Logout revokes the Yearclock session before redirecting through Authentik logout.
- Authentik accepts `post_logout_redirect_uri` only with `id_token_hint`, so each session keeps its ID token (migration `0029`) and logout sends it with `client_id`, then clears it. The provider registers `FRONTEND_URL` and `FRONTEND_URL/platform` as logout redirect URIs. A session without a stored token (created before `0029`) ends on Authentik's own logout page.
- The account-class database constraint and login boundary prevent the same User Account from carrying both customer and platform authority.

Authentik 2026.8 honours `X-Forwarded-*` headers only from `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS` (default: private ranges, set through `AUTHENTIK_TRUSTED_PROXY_CIDRS`), so the Compose network that holds `backend` and `caddy` must stay inside it (ADR-0036). `AUTHENTIK_WEB__BASE_URL` (`AUTHENTIK_BASE_URL`) names the public identity origin and is required from 2026.11. Upgrades follow `docs/runbooks/authentik-upgrade.md`.

## Sign-in pages (ADR-0039)

Authentik's flow pages (sign-in, enrolment, recovery, consent) import the web application's stylesheet and show
no background image. The default brand carries the custom CSS (an `@import` of `AUTHENTIK_THEME_CSS_URL`, then
`authentik/blueprints/yearclock-brand.css`), a 68-byte flow background, and the light theme, all applied by
`authentik/blueprints/yearclock-brand.yaml`. `AUTHENTIK_THEME_CSS_URL` is `<FRONTEND_URL>/theme.css` in production
(the build publishes the stylesheet there; the frontend serves it with `no-cache`, and serves `/assets/*` with
`Access-Control-Allow-Origin: *` so the identity origin can load the fonts) and the Vite dev server locally. If
the stylesheet cannot be loaded the pages keep the bridge's fallback colors. See `docs/design/ui-foundation.md`.

## MCP clients (ADR-0037, ADR-0038)

Agents sign in through a second Authentik provider, `Yearclock MCP`, created by the blueprint
`authentik/blueprints/yearclock-mcp-application.yaml`: a confidential client with PKCE,
authorization-code and refresh-token grants, explicit consent, and strict redirect URIs. It
uses the same authentication flows, so the password-plus-second-factor policy applies unchanged.

- Authentik does not implement RFC 8707 resource indicators, so the access token's audience is
  the provider's client id (`MCP_OIDC_CLIENT_ID`). `app/mcp_server/verifier.py` accepts only a
  JWT signed with that provider's keys whose issuer is `MCP_OIDC_ISSUER` and whose audience is
  that client id; the signing keys are fetched from the provider's JWKS over the Compose network
  like the web login does.
- The MCP issuer is an alias of the issuer accounts are stored under. The `sub` is the same in
  both providers (`hashed_user_id`), so `app/mcp_server/identity.py` looks the account up under
  the canonical `OIDC_ISSUER`. Only that one configured issuer is aliased, MCP never creates an
  account, and only customer accounts may use it.
- Clients are pre-registered and never register themselves. Dynamic client registration is not
  enabled (in Authentik 2026.8 it needs a token the client does not have and creates a provider,
  with its own issuer, per client). The client id and secret are given to the person connecting;
  the one secret is shared by every Organization, so it does not separate customers.
- Refresh tokens and access-token lifetimes are Authentik's provider settings; a token that has
  been revoked in Authentik stays valid until it expires, since it is verified locally.

Local Authentik setup and the strong-authentication acceptance checklist are documented in `docs/runbooks/authentik-local.md`.

## Platform sign-in

- Operators enroll staff with `python -m app.platform_admin enroll --email
  ... --role platform_admin|support_agent` (valid seven days by default).
- A sign-in started with `audience=platform` accepts an existing Platform
  User, or creates one from an unused enrollment whose email matches the
  verified identity email. An identity that already belongs to a customer
  account is refused, so the two account classes never merge.
- Customer sign-ins refuse Platform Users. Session checks are per account
  class: customer routes and platform routes each accept only their own class.
- Both audiences use the same OIDC callback; the login attempt stores the
  audience, so Authentik needs no extra redirect URI.

## Organization entry

- After login, a customer account with one Organization proceeds to that Organization.
- An account with several Organizations chooses one from an Organization selector.
- The last visited Organization may be offered as a convenience, but Organization context remains explicit in routes and authorization.
- Creating another Organization repeats the Organization-specific signup and billing flow without creating another User Account.
