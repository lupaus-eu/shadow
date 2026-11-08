# Ticket 10: Row-level security and isolation tests (080G)

Status: wontfix

Closed with the feature: superseded by the Yearclock platform base (see the PRD note).

## Goal

The database itself refuses cross-company access for the application role.

## Implementation

- (from ticket 02 review) Secondary foreign keys can point into another company because FK checks bypass row-level security (e.g. `graph_edges.source_graph_node_id/target_graph_node_id`, `graph_nodes.node_type_id` and `timeserie_id`, `allowed_connections.*`, `type_attributes.owner_*`, `ai_change_sets.scenario_id`, `scenarios.source_scenario_id/initial_state_id`, `derived_metrics_equations.derived_timeserie_id`): add same-company check triggers or composite FKs and tests.
- Migration 029 policies as in the technical design; ADR-016 amendment (as built).
- A test that fails when a route reads a company table through the login-role session.
- Cross-company isolation test suite per table.

## Acceptance criteria

- [ ] With no, own or foreign context, each table behaves as designed for read and write; worker scope works; default Metamodel readable by all.
- [ ] Policies are `FORCE`d and the isolation suite passes through the real routes.

## Testing

- Backend/API — policy tests per table, route-level isolation, full suite
- Compose/runtime — local stack run through Caddy

## Documentation effects

- ADR-016 amendment
- `docs/architecture/DATABASE.md`, `overview.md`
- `docs/operations/testing.md`

## Blocked by

- 04
- 05
- 06
- 07
- 08

## Completion record

(filled in when implemented: executed checks, AI review, deviations)
