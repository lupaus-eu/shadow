# TASK-009 Core Database Schema

## Source Plan

Approved plan: create a relational PostgreSQL database baseline for Schatten graph data using the developer specifications adjusted with review suggestions.

This task covers the schema migration, constraints, indexes and schema documentation.

## Goal

Create the first versioned database schema for Schatten.

The schema must support organisations, scenarios, organisation states, events, metamodels, graph snapshots, graph nodes, graph edges and timeseries using PostgreSQL as the source of truth.

## Requirements

- Add a numbered SQL migration in `db/migrations/`, for example `001_create_core_schema.sql`.
- Create these tables:
  - `users`
  - `organisations`
  - `scenarios`
  - `org_states`
  - `events`
  - `metamodels`
  - `node_types`
  - `edge_types`
  - `type_attributes`
  - `allowed_connections`
  - `graphs`
  - `graph_nodes`
  - `graph_edges`
  - `timeseries`
  - `timeserie_values`
- Use bigint identity primary keys starting at 101.
- Use table-specific primary key names:
  - `user_id`
  - `organisation_id`
  - `scenario_id`
  - `org_state_id`
  - `event_id`
  - `metamodel_id`
  - `node_type_id`
  - `edge_type_id`
  - `type_attribute_id`
  - `allowed_connection_id`
  - `graph_id`
  - `graph_node_id`
  - `graph_edge_id`
  - `timeserie_id`
  - `timeserie_value_id`
- Add audit columns to all tables:
  - `created_by BIGINT REFERENCES users(user_id)`
  - `created_time TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `modified_by BIGINT REFERENCES users(user_id)`
  - `modified_time TIMESTAMPTZ NOT NULL DEFAULT now()`
  - `deleted_by BIGINT REFERENCES users(user_id)`
  - `deleted_time TIMESTAMPTZ`
- Add `name TEXT` to all requested tables except:
  - `org_states`
  - `metamodels`
  - `timeserie_values`
  - graph content tables where stable keys and attributes define contents
- Add stable Varjo-compatible key columns where needed:
  - `organisation_key`
  - `scenario_key`
  - `org_state_key`
  - `event_key`
  - `node_type_key`
  - `edge_type_key`
  - `node_key`
  - `edge_key`
  - `timeserie_key`
- Add `users.role TEXT NOT NULL` with allowed values `consultant` and `admin`.
- Add `scenarios` columns:
  - `organisation_id BIGINT NOT NULL REFERENCES organisations(organisation_id)`
  - `description TEXT`
  - `protected BOOLEAN NOT NULL DEFAULT FALSE`
  - `source_scenario_id BIGINT REFERENCES scenarios(scenario_id)`
  - `initial_state_id BIGINT REFERENCES org_states(org_state_id)`
  - `version INT NOT NULL DEFAULT 1`
- Add `org_states` columns:
  - `scenario_id BIGINT NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE`
  - `version INT NOT NULL DEFAULT 1`
  - `description TEXT`
  - `target_date DATE`
- Add `events` columns:
  - `target_date DATE`
  - `version INT NOT NULL DEFAULT 1`
  - `event_details TEXT`
  - `scenario_id BIGINT NOT NULL REFERENCES scenarios(scenario_id) ON DELETE CASCADE`
- Add `metamodels` columns:
  - `organisation_id BIGINT REFERENCES organisations(organisation_id)`
  - `version INT NOT NULL DEFAULT 1`
  - `organisation_id = NULL` represents the default metamodel.
- Add `node_types` columns:
  - `metamodel_id BIGINT NOT NULL REFERENCES metamodels(metamodel_id)`
  - `display_name TEXT NOT NULL`
  - `ui_color TEXT`
  - `ui_shape TEXT`
  - `timeserie_id TEXT`
  - `timeserie_secondary_id TEXT`
  - `timeserie_id_rule TEXT`
- Add `edge_types` columns:
  - `metamodel_id BIGINT NOT NULL REFERENCES metamodels(metamodel_id)`
  - `display_name TEXT NOT NULL`
  - `ui_style TEXT`
  - `ui_source_end TEXT`
  - `ui_target_end TEXT`
- Add `type_attributes` columns:
  - `metamodel_id BIGINT NOT NULL REFERENCES metamodels(metamodel_id)`
  - `owner_kind TEXT NOT NULL CHECK (owner_kind IN ('node_type', 'edge_type'))`
  - `owner_node_type_id BIGINT REFERENCES node_types(node_type_id)`
  - `owner_edge_type_id BIGINT REFERENCES edge_types(edge_type_id)`
  - `attribute_key TEXT NOT NULL`
  - `display_name TEXT NOT NULL`
  - `data_type TEXT NOT NULL`
  - `mandatory BOOLEAN NOT NULL DEFAULT FALSE`
  - `max_length INT`
  - `multiline BOOLEAN`
  - constraint requiring exactly one owner FK matching `owner_kind`
- Add `allowed_connections` columns:
  - `edge_type_id BIGINT NOT NULL REFERENCES edge_types(edge_type_id)`
  - `metamodel_id BIGINT NOT NULL REFERENCES metamodels(metamodel_id)`
  - `source_node_type_id BIGINT NOT NULL REFERENCES node_types(node_type_id)`
  - `target_node_type_id BIGINT NOT NULL REFERENCES node_types(node_type_id)`
- Add `graphs` columns:
  - `org_state_id BIGINT NOT NULL REFERENCES org_states(org_state_id) ON DELETE CASCADE`
  - optional `description TEXT`
- Add `graph_nodes` columns:
  - `graph_id BIGINT NOT NULL REFERENCES graphs(graph_id)`
  - `node_key TEXT NOT NULL`
  - `node_type_id BIGINT NOT NULL REFERENCES node_types(node_type_id)`
  - `create_date DATE`
  - `position_x DOUBLE PRECISION`
  - `position_y DOUBLE PRECISION`
  - `attributes JSONB NOT NULL DEFAULT '{}'::jsonb`
  - `timeserie_id BIGINT REFERENCES timeseries(timeserie_id)`
  - `timeserie_secondary_id BIGINT REFERENCES timeseries(timeserie_id)`
- Add `graph_edges` columns:
  - `graph_id BIGINT NOT NULL REFERENCES graphs(graph_id)`
  - `edge_key TEXT NOT NULL`
  - `edge_type_id BIGINT NOT NULL REFERENCES edge_types(edge_type_id)`
  - `source_graph_node_id BIGINT NOT NULL REFERENCES graph_nodes(graph_node_id)`
  - `target_graph_node_id BIGINT NOT NULL REFERENCES graph_nodes(graph_node_id)`
  - `create_date DATE`
  - `attributes JSONB NOT NULL DEFAULT '{}'::jsonb`
- Add `timeseries` columns:
  - `scenario_id BIGINT NOT NULL REFERENCES scenarios(scenario_id)`
  - `timeserie_key TEXT NOT NULL`
  - `name TEXT NOT NULL`
  - `description TEXT`
  - `unit TEXT`
  - `time_unit TEXT NOT NULL CHECK (time_unit IN ('day', 'week', 'month', 'year'))`
  - `value_unit TEXT NOT NULL CHECK (value_unit IN ('number', 'string', 'boolean'))`
- Add `timeserie_values` columns:
  - `timeserie_id BIGINT NOT NULL REFERENCES timeseries(timeserie_id)`
  - `date DATE NOT NULL`
  - `value JSONB NOT NULL`
- Add indexes for parent lookups, active stable-key uniqueness, graph traversal and timeserie value lookup.

## Acceptance Criteria

- [ ] Migration creates all required tables.
- [ ] All primary keys are bigint identities starting at 101.
- [ ] All required audit columns exist and reference `users(user_id)`.
- [ ] `users.role` allows only `consultant` and `admin`.
- [ ] `org_states`, `metamodels` and `timeserie_values` do not have a `name` column.
- [ ] `metamodels.organisation_id` can be `NULL` for the default metamodel.
- [ ] Only one active default metamodel can exist.
- [ ] Only one active metamodel per organisation can exist.
- [ ] `(organisation_id, version)` uniqueness is enforced for organisation-specific metamodels.
- [ ] Default metamodel version uniqueness is enforced separately for `organisation_id IS NULL`.
- [ ] Graph nodes are unique by active `(graph_id, node_key)`.
- [ ] Graph edges are unique by active `(graph_id, edge_key)`.
- [ ] Graph edges reference relational source and target graph nodes.
- [ ] Deleting a scenario cascades to its `org_states`, `events` and related `graphs`.
- [ ] Timeserie values are unique by `(timeserie_id, date)`.
- [ ] Documentation reflects the new physical schema.
- [ ] No seed data is added in this task.

## Out Of Scope

- Docker database runtime setup.
- Dev seed data.
- Importing Varjo JSON data.
- Backend SQLAlchemy models.
- Backend API endpoints.
- Authentication and authorization behavior.
- Choosing a migration framework.
- Production database deployment.

## Implementation Notes

- Read `docs/data/DATABASE.md`, `docs/data/DATA-MODEL.md`, `db/migrations/README.md` and `db/init/README.md` before implementation.
- Keep migration SQL reviewable and deterministic.
- Use `BIGINT GENERATED BY DEFAULT AS IDENTITY (START WITH 101)` instead of `BIGSERIAL`.
- Use `TIMESTAMPTZ`, not a custom `date_time` type.
- Use partial unique indexes with `WHERE deleted_time IS NULL` for active soft-delete uniqueness.
- Add FK creation order carefully because `scenarios.initial_state_id` references `org_states`, while `org_states.scenario_id` references `scenarios`.
- Do not add extensions unless strictly required.
- If diagram generation tooling is not available, update the PlantUML source and document that SVG regeneration was not run.

## Testing

Required:

- [ ] Manual database verification
- [ ] SQL migration verification
- [ ] Documentation verification

Not applicable:

- [ ] Frontend tests: no frontend changes.
- [ ] Backend tests: no backend code changes.
- [ ] Integration tests: no backend/database integration yet.
- [ ] Lint: SQL/docs only unless tooling is later added.
- [ ] Build: no application build changes.
- [ ] Typecheck: no typed source code changes.

Commands:

```bash
docker compose up -d database

# Example, adjust file name if needed.
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/migrations/001_create_core_schema.sql

PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -c "\dt"
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -c "\d users"
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -c "\d graph_nodes"
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -c "\d graph_edges"
```

Manual checks:

- Insert one user and confirm `user_id = 101`.
- Attempt to insert an invalid user role and confirm it fails.
- Insert two active default metamodels and confirm the second insert fails.
- Insert duplicate active graph node keys in the same graph and confirm the second insert fails.
- Insert duplicate timeserie values for the same date and confirm the second insert fails.

## Documentation

Update:

- `docs/data/DATABASE.md`
- `docs/data/DATA-MODEL.md`
- `docs/diagrams/db-physical-schema.puml`, if present or created
- `docs/diagrams/generated/db-physical-schema.svg`, if diagram generation is available
- `db/migrations/README.md`, only if the migration convention needs clarification

No ADR is required unless implementation needs to change the migration strategy, database technology, ORM decision or architecture.

## Notes For AI Agent

- Lue `AGENTS.md`, `ARCHITECTURE.md`, `docs/decisions/ADR-001-tech-stack.md`, `docs/data/DATABASE.md`, `docs/data/DATA-MODEL.md`, `db/migrations/README.md`, `db/init/README.md`, `docs/TESTING.md` ja tämä task ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä lisää dev seed dataa tässä taskissa.
- Älä valitse tai lisää migraatiotyökalua ilman hyväksyntää.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
