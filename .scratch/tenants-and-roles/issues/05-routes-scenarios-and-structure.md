# Ticket 05: Company routes: scenarios, states, structure, metrics (080D, part 2)

Status: wontfix

Closed with the feature: superseded by the Yearclock platform base (see the PRD note).

## Goal

The 37 operations under `/organisations/{key}/scenarios…` move under the company prefix.

## Implementation

- Same method as ticket 04 for the scenario, state, event, graph, timeseries, equation and metamodel routers.
- Metamodel reads include the default Metamodel (NULL company).

## Acceptance criteria

- [ ] Isolation and unchanged behaviour as in ticket 04 for every operation.
- [ ] The default Metamodel is readable by every company and not writable through the API.

## Testing

- Backend/API — isolation tests, authorization sweep, full suite

## Documentation effects

- `docs/architecture/domains/ORGANISATIONS.md`, `data/DATA-MODEL.md`, API docs

## Blocked by

- 03

## Completion record

(filled in when implemented: executed checks, AI review, deviations)
