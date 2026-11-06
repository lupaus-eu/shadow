# Ticket 08: Members API (080F)

Status: needs-info

## Goal

Admins and Owners manage the company's members; the global Users API is gone.

## Implementation

- `/api/v1/tenants/{tenant_id}/members` GET, POST, PATCH `/{user_id}`, DELETE `/{user_id}`, POST `/{user_id}/sessions/revoke` with the domain-model rules, optimistic `version`, audit events.
- Remove the global Users API and `require_admin`.

## Acceptance criteria

- [ ] Rules 1–11 of the domain model are enforced and tested (last Owner, only Owner changes Owners, platform accounts never added, version conflicts, 404/403).
- [ ] Audit events exist for every change.
- [ ] Two simultaneous demotions leave one Owner.

## Testing

- Backend/API — service and route tests incl. concurrency

## Documentation effects

- `docs/admin/`, `docs/architecture/domains/USERS.md`, `TENANTS.md`, API docs

## Blocked by

- 03

## Completion record

(filled in when implemented: executed checks, AI review, deviations)
