# Ticket 09: Frontend company context (080F, UI)

Status: wontfix

Closed with the feature: superseded by the Yearclock platform base (see the PRD note).

## Goal

The web application works under a company address and gives Members management to Admins and Owners.

## Implementation

- Routes `/tenants/:tenantId/…`; redirect, chooser, no-company page; header selector; `AuthProvider` with `tenants`; API client prefix; Users tab becomes Members tab; role checks from the membership.
- Requires pnpm/Node (not available in the current agent environment: implement where it is, or the human runs `make frontend-check`).

## Acceptance criteria

- [ ] A one-company person lands in the company; several see the chooser; none see the no-company page.
- [ ] Members tab visible only to Admin/Owner and works against ticket 08.
- [ ] `make frontend-check` and a browser check of the main path pass.

## Testing

- Frontend — vitest, lint, build
- Browser/E2E — sign-in, company routing, member add/role change

## Documentation effects

- `docs/design/`, `docs/user/`, `docs/admin/`

## Blocked by

- 04
- 05
- 06
- 07
- 08

## Completion record

(filled in when implemented: executed checks, AI review, deviations)
