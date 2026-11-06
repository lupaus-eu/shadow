# Ticket 04: Company routes: Organisations and Customers (080D, part 1)

Status: needs-info

## Goal

Organisation and Customer APIs live under `/api/v1/tenants/{tenant_id}/…` and run in the tenant session.

## Implementation

- Prefix the routers, switch their session alias to `get_tenant_session`, role checks to the tenant dependencies; remove the old global paths of these routers.
- Check services for lookups by explicit id that must be company-scoped; fix where a `WHERE` was relying on the single company.
- Update `test_api_authorization.py` for these paths; OpenAPI snapshot if one exists.

## Acceptance criteria

- [ ] Every operation works for a member of the company and answers 404 for another company's data and for non-members.
- [ ] Old paths no longer exist.
- [ ] Role rules unchanged (member/admin/owner as in the matrix).

## Testing

- Backend/API — two-company isolation test per operation family; authorization sweep; full suite

## Documentation effects

- `docs/architecture/domains/ORGANISATIONS.md`, `CUSTOMER.md`, API docs

## Blocked by

- 03

## Completion record

(filled in when implemented: executed checks, AI review, deviations)
