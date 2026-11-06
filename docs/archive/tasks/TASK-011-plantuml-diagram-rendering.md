# TASK-011 PlantUML Diagram Rendering

## Source Plan

Approved plan: add a separate Docker-based PlantUML rendering tool for project diagrams and use it to generate the physical database schema SVG.

## Goal

Make PlantUML diagram rendering reproducible through Docker.

This task adds documentation tooling only. PlantUML must stay out of the frontend and application runtime images.

## Requirements

- Add a dedicated diagram rendering Docker image under `docs/architecture/diagrams/`.
- Install the required PlantUML runtime dependencies in that image, including Java and Graphviz.
- Pin the PlantUML version in the Dockerfile instead of using an unpinned latest download.
- Add a Docker Compose service named `diagram-renderer`.
- Keep `diagram-renderer` behind a `docs` profile.
- Configure `diagram-renderer` to mount the repository and render SVG output into `docs/architecture/diagrams/generated/`.
- Render `docs/architecture/diagrams/db-physical-schema.puml` to `docs/architecture/diagrams/generated/db-physical-schema.svg`.
- Update `docs/architecture/diagrams/README.md` with the Docker Compose render command.
- Update `docs/operations/local-development.md` with a short diagram rendering section.

## Acceptance Criteria

- [ ] `docker compose --profile docs build diagram-renderer` succeeds.
- [ ] `docker compose --profile docs run --rm diagram-renderer` generates `docs/architecture/diagrams/generated/db-physical-schema.svg`.
- [ ] The generated SVG is non-empty and contains SVG markup.
- [ ] The generated SVG represents `docs/architecture/diagrams/db-physical-schema.puml`.
- [ ] `docs/architecture/diagrams/README.md` explains how to render diagrams through Docker.
- [ ] `docs/operations/local-development.md` includes the local diagram rendering command.
- [ ] Frontend, database and frontend preview containers keep their existing responsibilities.
- [ ] No application runtime dependency is added.
- [ ] No ADR is added because PlantUML is already the documented primary diagram format.

## Out Of Scope

- Changing the database schema.
- Changing migrations or seed scripts.
- Changing frontend or backend application code.
- Changing the existing `.puml` source unless rendering exposes a syntax issue.
- Adding CI validation for generated diagrams.

## Implementation Notes

- Use a separate docs-oriented Docker image, not `frontend/Dockerfile`.
- Use service name `diagram-renderer`.
- Use Docker Compose profile `docs`.
- The default renderer command should render `docs/architecture/diagrams/db-physical-schema.puml`.
- Keep generated SVG files in `docs/architecture/diagrams/generated/`.
- Do not manually edit generated SVG files.

## Testing

Required:

- [ ] Docker Compose validation
- [ ] Manual diagram verification

Not applicable:

- [ ] Frontend tests: no frontend behavior changes.
- [ ] Backend tests: no backend code changes.
- [ ] Integration tests: no application/database integration changes.
- [ ] Lint: no linted application source code changes.
- [ ] Build: no application build changes.
- [ ] Typecheck: no typed source code changes.

Commands:

```bash
docker compose config
docker compose --profile docs build diagram-renderer
docker compose --profile docs run --rm diagram-renderer
test -s docs/architecture/diagrams/generated/db-physical-schema.svg
```

## Documentation

Update:

- `docs/architecture/diagrams/README.md`
- `docs/operations/local-development.md`

No ADR is required because PlantUML is already the documented primary diagram format.

## Notes For AI Agent

- Read `AGENTS.md`, `docs/architecture/overview.md`, `docs/adr/0001-tech-stack.md`, `docs/architecture/diagrams/README.md`, `docs/operations/local-development.md` and this task before implementation.
- Implement only the scope defined in this task.
- Do not modify database schema, migrations, seed scripts, frontend code or backend code.
- Do not add PlantUML to the frontend runtime image.
- At the end, explain what changed and how the work was verified.
