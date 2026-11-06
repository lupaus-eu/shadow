# Architecture and design routing

Read the mandatory documents in `AGENTS.md`, `CONTEXT.md`, and relevant ADRs.
Before planning a change, select the sources below that match its shape.

| Change | Read before planning | Update when implemented |
| --- | --- | --- |
| Domain, lifecycle, or terminology | `CONTEXT.md`, `docs/architecture/events.md`, `recurrence.md`, `lifecycle-defaults.md`, relevant ADRs | `CONTEXT.md`, the applicable architecture document, and ADRs as appropriate |
| Database, RLS, or data ownership | `docs/architecture/database.md`, `audit.md`, relevant migration ADRs | Alembic migration, database/audit documentation, and ADRs as appropriate |
| API, role, or authorization | `docs/architecture/api.md`, `authentication.md`, `organization-authorization-matrix.md`, `support-access.md` | API/authorization docs, relevant user/admin guidance, and ADRs as appropriate |
| UI, view, accessibility, or user workflow | `docs/architecture/frontend.md`, `docs/design/README.md`, applicable user guidance | `docs/design/`, `docs/user/`, and frontend architecture documentation as appropriate |
| Service, container, environment, or deployment | `docs/architecture/{docker,deployment,project-layout}.md`, `docs/operations/` | Architecture, operations, and `.env.example`; ADR for a durable decision |
| Authentication, billing, email, or another external integration | Relevant architecture document (`authentication.md`, `billing.md`, or `email.md`), `docs/operations/`, relevant ADRs | Architecture, operations, privacy, and ADR documentation as appropriate |
| Worker or asynchronous processing | `docs/architecture/workers.md`, `audit.md`, `docs/operations/` | Worker, operations, audit, and architecture documentation as appropriate |
| New dependency or major service boundary | `docs/architecture/stack.md`, `project-layout.md`, `docker.md`, relevant ADRs | Stack, project layout, Docker/deployment docs, and an ADR |

This routing complements a ticket's `Documentation effects`; it does not
remove the need to inspect other documentation when a change spans rows.
