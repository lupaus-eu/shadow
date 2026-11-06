# TASK-039B Authentication Identity And Session Schema

Status: Planned

## Source Plan

Approved TASK-039 plan: persist provider-neutral identities and opaque
application sessions, and support guarded first-login discovery through a
pre-created Shadow user email. This task owns the schema, models and existing
Users management surface needed by later authentication tasks.

## Goal

Add the persistence contract for external identities, login transactions and
server-side sessions. Extend Users management so administrators can assign the
unique email required for a later guarded identity link.

## Requirements

- Depends on accepted ADR-004 from TASK-039A.
- Add paired migration `009_add_auth_identity_session_schema.sql` and
  `009_add_auth_identity_session_schema.down.sql`.
- Migration 009 assumes there is no retained user data. Do not add a temporary
  nullable state, placeholder default or legacy-email backfill; developers with
  existing local databases must discard/reset them before applying migration
  009.
- Add non-nullable `users.email` with trimmed non-blank shape and a
  partial unique index on `lower(email)` for active users.
- Add `user_identities` owned by Users Domain with:
  - bigint identity primary key starting at `101`
  - required `user_id`, exact `issuer`, `subject`, `created_time` and
    `last_login_time`
  - non-blank constraints for issuer and subject
  - uniqueness for `(issuer, subject)` and `(user_id, issuer)`
- Add `oidc_login_transactions` with a hashed state key, hashed
  pre-authentication browser-binding key, nonce, PKCE verifier, validated
  relative return path, creation time and a ten-minute expiry. State, nonce,
  PKCE verifier and browser-binding values are independent CSPRNG values with at
  least 256 bits of entropy. It must contain no provider token and support
  atomic single-use deletion. Index expiry and the browser-binding hash so the
  backend can expire old rows and enforce at most five live transactions per
  browser.
- Add `auth_sessions` with hashed session identifier, `user_id`, a random
  session-bound CSRF token, creation, last-activity and absolute-expiry
  timestamps. Session identifiers and CSRF tokens are independent CSPRNG values
  with at least 256 bits of entropy. Persist the session identifier only as a
  SHA-256 hash. Do not persist a raw session ID, provider token or client secret.
  The CSRF token may be stored directly because it is returned to same-origin
  JavaScript and is not sufficient without the separate HttpOnly session
  cookie.
- Add matching SQLAlchemy models using existing PostgreSQL/SQLite conventions.
- Extend Users backend schemas/service/API with email:
  - email is required and normalized for newly created users
  - patch supports changing email
  - responses expose `email: string`
  - duplicate active normalized email returns the existing conflict format
- Extend the Users frontend form, DTOs and tests to create and edit email and
  display a clear value.
- Update development seed users with distinct `@example.local` emails. Do not
  add external identity or session rows to the application seed.
- Do not implement OIDC, session cookies, route protection or role enforcement.

## Acceptance Criteria

- [ ] Migration 009 applies after migration 008 and its down migration removes
      only the new auth tables/index/column.
- [ ] Active user emails are case-insensitively unique.
- [ ] Identity uniqueness prevents two subjects from the same issuer binding
      to one user and prevents one subject binding to multiple users.
- [ ] Raw session identifiers and provider tokens cannot be stored by the
      defined models.
- [ ] A login transaction requires separate state and initiating-browser hashes,
      and schema indexes support the five-live-flow cap and expiry cleanup.
- [ ] Sessions contain the timestamps required for both the 30-minute idle and
      eight-hour absolute timeouts.
- [ ] New and existing users API/UI requires email.
- [ ] Backend and frontend user tests cover normalization; rejection of
      omitted, null and blank required emails; duplicate active email; and
      soft-delete email reuse.
- [ ] Domain, concept, data and diagram documentation matches the schema.

## Out Of Scope

- OIDC network calls and Authlib.
- Login/callback/session/logout endpoints.
- Authentication or authorization dependencies on business routes.
- Authentik or Entra configuration.
- Organisation membership or provider group mapping.

## Implementation Notes

- Read ADR-004, `docs/architecture/domains/USERS.md`, User concept documentation if present,
  `docs/architecture/data/DATA-MODEL.md`, `docs/architecture/data/DATABASE.md`, migration/init READMEs,
  `docs/operations/testing.md` and this task.
- Normalize email once in the trusted service boundary using trim plus
  case-insensitive comparison; preserve a sensible display form if existing
  conventions require it.
- Do not use email as a session or authorization key. It is only candidate
  discovery before the permanent `(issuer, subject)` binding exists.

## Testing

Required:

- [ ] Backend model, schema, API and constraint tests
- [ ] Frontend Users API/component tests
- [ ] Disposable PostgreSQL migration up/down and empty-database
      upgrade-from-008 verification
- [ ] Backend Ruff, pytest and pyright
- [ ] Frontend lint, tests and build
- [ ] Diagram regeneration

Commands:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright

cd ../frontend
pnpm lint
pnpm test
pnpm build

cd ..
docker compose --profile docs build diagram-renderer
docker compose --profile docs run --rm diagram-renderer
```

## Documentation

Update Users Domain/concept documentation, `docs/architecture/data/DATA-MODEL.md`,
`docs/architecture/data/DATABASE.md`, migration/local-development instructions, development
seed guidance, and logical/physical PlantUML sources plus generated SVGs.

## Notes For AI Agent

- Kaikki skeemamuutokset tehdaan migration 009 up/down -parina.
- Ala toteuta OIDC-flowta tai suojaa business-reitteja tassa taskissa.
- Ala lisaa uusia riippuvuuksia.
