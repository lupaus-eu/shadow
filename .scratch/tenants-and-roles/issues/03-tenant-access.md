# Ticket 03: Company access, session and sign-in accounts (080C)

Status: needs-info

## Goal

A request can be bound to one company of the signed-in person, with the role known, and every transaction of it runs as `shadow_app` with the company context.

## Implementation

- `app/core/tenancy.py`: `get_tenant_session` (membership lookup, 404 otherwise, `after_begin` hook applying role and `RequestContext` at every transaction), `TenantAccess`, `require_tenant_member/admin/owner`.
- `GET /api/v1/tenants`; `/auth/session` returns `tenants`.
- Account creation at first verified sign-in with no company (`AUTH_CREATE_ACCOUNTS`, default true; false restores refusal); audit `account.created`.
- `.env.example`, `docker-compose.yml`, production contract.

## Acceptance criteria

- [ ] A member reaches a probe route under `/api/v1/tenants/{id}/…`; a non-member and an unknown id get the same 404; roles are enforced by the three dependencies.
- [ ] Statements in the session run as `shadow_app` with the right GUCs after every commit within one request.
- [ ] A verified unknown email signs in and gets an account with no company; with the flag off sign-in is refused; concurrent first sign-ins create one account.

## Testing

- Backend/API — dependency, hook (multiple commits per request) and sign-in tests
- Compose/runtime — `docker compose config`

## Documentation effects

- `docs/architecture/overview.md`, authentication sequence diagram, `domains/USERS.md`
- `docs/admin/`, `docs/user/`
- `docs/architecture/deployment.md`, `.env.example`

## Blocked by

- 01
- 02

## Completion record

(filled in when implemented: executed checks, AI review, deviations)
