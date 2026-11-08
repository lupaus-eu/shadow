# Ticket 06: Company routes: predictions, change sets, prediction worker (080D, part 3)

Status: wontfix

Closed with the feature: superseded by the Yearclock platform base (see the PRD note).

## Goal

Prediction, prediction-request and AI change-set routes move under the company prefix; the worker runs per company.

## Implementation

- Routes as in ticket 04.
- Prediction worker claims and recovers under `worker_scope='predictions'`, then runs each request in its company's context via `RequestContext`.
- AI change-set services keep working with the tenant session.

## Acceptance criteria

- [ ] Isolation as in ticket 04.
- [ ] A worker run processes requests of two companies and each result lands in its own company.
- [ ] Stale-claim recovery works across companies.

## Testing

- Backend/API — isolation, worker multi-company test, full suite

## Documentation effects

- `docs/architecture/domains/FORECASTING.md`, `AI.md`, `docs/operations/` worker QA

## Blocked by

- 03

## Completion record

(filled in when implemented: executed checks, AI review, deviations)
