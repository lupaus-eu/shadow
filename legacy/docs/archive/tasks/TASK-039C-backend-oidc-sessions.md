# TASK-039C Backend OIDC And Application Sessions

Status: Planned

## Source Plan

Approved TASK-039 plan: FastAPI is a confidential OIDC relying party and owns
the complete provider interaction. React receives only a same-origin opaque
application-session cookie.

## Goal

Implement provider-neutral login, callback, session lookup and logout behavior
against either Authentik or single-tenant Entra ID. Establish the reusable
authenticated-user dependency without yet applying it to every business route.

## Requirements

- Depends on TASK-039B and accepted ADR-004.
- Add Authlib as the only approved new backend runtime dependency and update the
  uv lockfile. Do not add a frontend OIDC library.
- Add validated configuration for discovery URL, independently configured exact
  issuer, client ID, client secret, scopes, public origin, callback path,
  allowed origin, trusted Caddy peer CIDRs, cookie security, allowed ID-token
  signing algorithms (`RS256` initially), 30-minute idle timeout and eight-hour
  absolute lifetime. Derive the one allowed Host from the configured public
  origin rather than configuring it independently. Outside tests, missing
  required configuration must fail closed with a clear startup/configuration
  error. Production CORS is disabled; local development may allow only the
  exact configured app origin with credentials.
- Implement:
  - `GET /api/v1/auth/login?return_to=/...`
  - `GET /api/v1/auth/callback`
  - `GET /api/v1/auth/session`
  - `POST /api/v1/auth/logout`
- Login must accept only local absolute paths beginning with one `/`; reject
  protocol-relative, external, malformed or control-character return targets.
- Persist ten-minute state, nonce and S256 PKCE transaction data from TASK-039B.
  Set an independent 256-bit pre-authentication browser cookie when absent and
  reuse a still-valid binding for up to five live transactions. Persist only its
  hash in each transaction. Callback requires both state and that cookie,
  atomically consumes the matched transaction, deletes the other transactions
  bound to that cookie, expires the cookie and creates an unrelated fresh
  application session. Reject expired, mismatched, swapped or replayed
  callbacks.
- Use discovery and Authlib validation for ID-token signature, exact issuer,
  audience, expiry and nonce. Require discovery's issuer to exactly equal the
  separately configured issuer, accept only the configured asymmetric
  algorithm allowlist, and reject `none` and symmetric algorithms. Do not
  implement JWT validation manually or select algorithms from the token alone.
- Normalize validated claims into an internal `issuer`, `subject`, `email`,
  `name` shape. Provider-specific claims remain inside this adapter.
- Resolve identity atomically:
  - prefer an existing exact `(issuer, subject)` binding
  - otherwise link only one active user with matching normalized email and no
    identity for that issuer
  - deny missing/ambiguous/already-bound/inactive cases generically
  - persist the binding once and never auto-relink it
- Entra may use its validated email assertion only for guarded first-link
  discovery; Authentik fixture identities must assert verified email. Neither
  email nor name becomes the durable identity.
- Create an independent CSPRNG-generated 256-bit opaque session ID, persist only
  its SHA-256 hash, rotate at login, and set the cookie according to ADR-004.
  Compare CSRF and browser-binding secrets in constant time. Enforce the
  30-minute idle and eight-hour absolute timeouts; coalesce last-activity writes
  for no more than five minutes. Store and return only the CSRF token needed by
  the application; do not expose provider tokens.
- `GET /auth/session` returns the current active user (`id`, `name`, `email`,
  `role`) and a session-bound CSRF token, or the agreed anonymous `401` shape.
- Implement reusable dependencies for active authenticated user and admin.
  Recheck user soft-delete and current role on every authenticated request.
- Implement a reusable unsafe-request guard that requires the session CSRF
  header and exact configured `Origin`, rejects missing or `null` origins, and
  compares the CSRF token in constant time. Apply it to logout here; TASK-039D
  applies the same guard to every business `POST`, `PUT`, `PATCH` and `DELETE`.
- Logout must pass that guard, delete the local session and expire the
  cookie. Return `{ "logoutUrl": <string-or-null> }`, where a non-null URL is a
  backend-constructed provider end-session URL using only discovered/configured
  values and an exact configured post-logout URI. Local logout succeeds even
  when no provider logout URL is available; never accept a logout target from
  the browser.
- Expired transactions and sessions are removed opportunistically during login
  and session creation; no scheduler is introduced.
- Apply bounded-memory, fixed-window limits using `X-Shadow-Client-IP` only
  when the immediate peer is inside the configured trusted Caddy CIDRs; reject
  the header from every other peer. Allow 20 login starts and 60 callback
  attempts per minute per address and return `429` before provider or token-
  endpoint interaction. This baseline is for the single backend replica
  selected by the current deployment; multiple replicas require a shared
  limiter before rollout.
- Construct callback, post-login and logout redirects from the fixed configured
  public origin and validated relative paths, never request Host or forwarded
  headers. Reject requests whose Host does not exactly match the configured
  public host.
- Send `Cache-Control: no-store` on every auth/session response. Every callback
  with valid state and browser binding, including a provider error, atomically
  consumes the transaction and returns `303 See Other` to a clean validated
  relative success or error path. Invalid callbacks return `303 See Other` to
  one fixed generic local error path without consuming a transaction located
  only by attacker-controlled data. No callback renders a page containing query
  values or third-party content.
- Do not retain access, refresh or ID tokens, call UserInfo/Graph, protect all
  business routes, or populate audit actor columns in this task.

## Acceptance Criteria

- [ ] Both providers can use the same backend contract by changing
      configuration only.
- [ ] Valid callback creates one guarded identity binding and an opaque
      server-side session; no provider token reaches browser storage or API
      responses.
- [ ] Invalid state, nonce, PKCE, issuer, audience, signature, expiry, replay,
      browser binding, algorithm, Host, return path and identity-link cases fail
      closed.
- [ ] Session expiry, rotation, soft-deleted users and role refresh behave as
      specified.
- [ ] Unsafe logout requires valid CSRF and exact Origin; the reusable guard
      rejects missing and `null` origins.
- [ ] Logout returns only a trusted backend-constructed provider URL or null,
      and local session termination does not depend on provider availability.
- [ ] Cookie attributes match ADR-004, including production
      `SameSite=Strict`.
- [ ] Logs contain no codes, tokens, client secrets, cookies or personal email.
- [ ] Auth responses are non-cacheable, successful callbacks redirect with 303
      to a clean path, and public endpoint rate/transaction caps return 429.

## Out Of Scope

- Applying auth dependencies to business APIs.
- Fine-grained organisation authorization.
- Audit-column actor propagation.
- Frontend login UX.
- Authentik Compose and Entra resource creation.
- Refresh tokens, Microsoft Graph and back-channel logout.

## Implementation Notes

- Read ADR-004, Users Domain/data docs, `docs/operations/testing.md`, current FastAPI
  composition and TASK-039B before implementation.
- Keep route handlers thin and isolate provider protocol/claim handling from
  application identity and session services.
- Tests must use a fake discovery/token/JWKS boundary and generated test keys;
  they must not depend on internet access or real provider credentials.

## Testing

Required:

- [ ] Backend unit and API integration tests
- [ ] Generated-key token-validation tests
- [ ] Security failure, pre-auth binding, timeout, rate-limit, cache/redirect and
      log-redaction tests
- [ ] Backend Ruff, pytest and pyright

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

## Documentation

Update backend configuration examples and `docs/operations/testing.md` only as needed for
the implemented auth test harness. Final architecture/operator documentation is
owned by TASK-039G.

## Notes For AI Agent

- Authlib on tassa taskissa nimenomaisesti hyvaksytty uusi riippuvuus; ala
  lisaa muita riippuvuuksia.
- Ala ota business-reitteja suojauksen piiriin tassa taskissa.
- Ala tallenna provider-tokenia tai raakaa session tunnistetta.
