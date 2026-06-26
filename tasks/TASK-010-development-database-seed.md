# TASK-010 Development Database Seed

## Source Plan

Approved plan: add local development seed data after the relational database schema exists.

This task seeds a dummy admin user and the default metamodel from the repo-local `db/init/metamodel_state_##default##.json` file.

## Goal

Make an empty local development database usable after schema creation by adding minimal non-production seed data.

The seed must create a dummy admin user when `users` is empty and import the Varjo default metamodel as Schatten's default metamodel with `metamodels.organisation_id = NULL`.

## Requirements

- Add a dev/local seed script under `db/init/`.
- Seed a dummy admin user only when `users` is empty.
- Seed the default metamodel only when no active default metamodel exists.
- Use the repo-local copy of Varjo's default metamodel source file:
  - `db/init/metamodel_state_##default##.json`
- Store the default metamodel in `metamodels` with:
  - `organisation_id = NULL`
  - `version` from the JSON root `version` field
- Seed the JSON `node_types` array into `node_types`.
- Seed each node type's `attributes` array into `type_attributes`.
- Seed the JSON `edge_types` array into `edge_types`.
- Seed each edge type's `attributes` array into `type_attributes`.
- Seed each edge type's `allowed_connections` into `allowed_connections`.
- Expand allowed connection arrays into one row per source/target pair.
- Preserve Varjo stable IDs in:
  - `node_types.node_type_key`
  - `edge_types.edge_type_key`
  - `type_attributes.attribute_key`
- Map node type UI values:
  - `ui.color` to `node_types.ui_color`
  - `ui.shape` to `node_types.ui_shape`
- Map edge type UI values:
  - `ui.style` to `edge_types.ui_style`
  - `ui.source_end` to `edge_types.ui_source_end`
  - `ui.target_end` to `edge_types.ui_target_end`
- Map node type timeserie metadata when present:
  - `timeserie.timeserie_id` to `node_types.timeserie_id`
  - `timeserie.timeserie_secundary_id` to `node_types.timeserie_secondary_id`
  - `timeserie.timeserie_id_rule` to `node_types.timeserie_id_rule`
- Keep the seed idempotent.
- Keep the seed clearly non-production.

## Acceptance Criteria

- [ ] Running the seed on an empty database creates one dummy admin user.
- [ ] Re-running the seed does not create duplicate dummy admin users.
- [ ] Running the seed creates one active default metamodel with `organisation_id IS NULL`.
- [ ] Re-running the seed does not create duplicate active default metamodels.
- [ ] Seeded node types match the Varjo default metamodel JSON count and stable IDs.
- [ ] Seeded edge types match the Varjo default metamodel JSON count and stable IDs.
- [ ] Seeded node and edge type attributes match the Varjo default metamodel JSON.
- [ ] Seeded allowed connections match the expanded source/target combinations from the JSON.
- [ ] The seed does not create organisations, scenarios, org states, events, graphs, graph nodes, graph edges, timeseries or timeserie values.
- [ ] Documentation explains that the seed is local/dev-only.

## Out Of Scope

- Database schema changes.
- Docker database runtime setup.
- Backend models or API code.
- Importing scenario, organisation, org state, graph, event or timeserie data from Varjo.
- Production seed data.
- Authentication integration with Microsoft Entra ID.
- Password-based login behavior.

## Implementation Notes

- This task depends on `TASK-009 Core Database Schema`.
- If `TASK-008 Database Runtime Baseline` is complete, document how to run the seed against the local Docker database.
- Prefer a SQL seed script if it can remain readable and idempotent.
- If parsing the metamodel JSON directly in SQL becomes too awkward, stop and ask for approval before introducing a script-based seed approach or new tooling.
- Do not commit secrets.
- The dummy admin should be obviously non-production.
- Suggested dummy admin values:
  - `name = 'Development Admin'`
  - `role = 'admin'`
- Use nullable audit fields for seed rows unless a seeded user is available and appropriate.
- Do not copy Varjo's document-table persistence model.
- Do not modify the Varjo repository.

## Testing

Required:

- [ ] Manual database verification
- [ ] Seed idempotency verification
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

# Apply schema first, if not already applied.
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/migrations/001_create_core_schema.sql

# Run seed script. Adjust file name if needed.
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/init/002_seed_development_data.sql
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/init/002_seed_development_data.sql
```

Manual checks:

```bash
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -c "SELECT user_id, name, role FROM users;"
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -c "SELECT metamodel_id, organisation_id, version FROM metamodels WHERE organisation_id IS NULL AND deleted_time IS NULL;"
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -c "SELECT node_type_key, display_name FROM node_types ORDER BY node_type_key;"
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -c "SELECT edge_type_key, display_name FROM edge_types ORDER BY edge_type_key;"
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -c "SELECT COUNT(*) FROM type_attributes;"
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -c "SELECT COUNT(*) FROM allowed_connections;"
```

## Documentation

Update:

- `db/init/README.md`, if the seed naming or local usage needs clarification
- `docs/LOCAL-DEVELOPMENT.md`, if local seed commands are added
- `docs/data/DATABASE.md`, if seed behavior should be documented alongside the schema

No ADR is required because this task adds local/dev seed data only.

## Notes For AI Agent

- Lue `AGENTS.md`, `ARCHITECTURE.md`, `docs/decisions/ADR-001-tech-stack.md`, `docs/data/DATABASE.md`, `docs/data/DATA-MODEL.md`, `db/migrations/README.md`, `db/init/README.md`, `docs/TESTING.md`, `TASK-009 Core Database Schema` ja tämä task ennen toteutusta.
- Toteuta vain tämän taskin scope.
- Älä muuta skeemaa tässä taskissa.
- Älä muuta Varjo-repositoryä.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Jos repo-local metamodel JSON -tiedostoa ei ole saatavilla toteutusympäristössä, pysähdy ja pyydä ihmisen päätös seed-lähteen lisäämisestä tai vaihtoehtoisesta seed-tavasta.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
