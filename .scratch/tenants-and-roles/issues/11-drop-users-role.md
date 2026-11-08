# Ticket 11: Drop users.role (080G, cleanup)

Status: wontfix

Closed with the feature: superseded by the Yearclock platform base (see the PRD note).

## Goal

A single source of authority: memberships.

## Implementation

- Migration 030 drops `users.role` (+ down), remove remaining code, seed and docs references.

## Acceptance criteria

- [ ] Nothing reads or writes `users.role`; the full suite passes after the drop; migration down/up works.

## Testing

- Backend/API — full suite, migration up/down

## Documentation effects

- `docs/architecture/data/DATA-MODEL.md`, `domains/USERS.md`

## Blocked by

- 07
- 08
- 09

## Completion record

(filled in when implemented: executed checks, AI review, deviations)
