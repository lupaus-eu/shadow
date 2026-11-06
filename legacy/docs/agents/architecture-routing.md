# Architecture and design routing

Read the mandatory documents in `AGENTS.md`, `CONTEXT.md`, and relevant ADRs.
Before planning a change, select the sources below that match its shape.

| Change | Read before planning | Update when implemented |
| --- | --- | --- |
| Domain, lifecycle, or terminology | `CONTEXT.md`, `docs/architecture/domains/` (owning domain), `docs/architecture/concepts/` (affected concept), relevant ADRs | `CONTEXT.md`, the domain and concept documents, and ADRs as appropriate |
| Database, migration, or data ownership | `docs/architecture/data/DATA-MODEL.md`, `DATABASE.md`, `db/migrations/README.md`, ADR-002 | Paired SQL migration, data documents, DB diagrams, and ADRs as appropriate |
| API, role, or authorization | The owning domain document, `docs/architecture/overview.md`, ADR-004 (authentication), ADR-015 (MCP) | Domain and authorization documentation, `docs/admin/`, and ADRs as appropriate |
| UI, view, accessibility, or user workflow | `docs/design/README.md`, `docs/architecture/overview.md` (frontend), applicable `docs/user/` guidance | `docs/design/`, `docs/user/`, and frontend architecture documentation as appropriate |
| Service, container, environment, or deployment | `docs/architecture/deployment.md`, `docs/architecture/stack.md`, `docs/operations/`, `docs/runbooks/production.md`, ADR-013 | Deployment and operations docs, runbook, and `.env.example`; ADR for a durable decision |
| Authentication, billing, email, or another external integration | Relevant ADRs (ADR-004, ADR-013, ADR-015 and their successors), `docs/architecture/deployment.md`, `docs/operations/` | Architecture, operations, privacy (`docs/gdpr/`), legal (`docs/legal/`), and ADR documentation as appropriate |
| AI via MCP | ADR-015, `docs/architecture/domains/AI.md`, `docs/architecture/concepts/AI_CHANGE_SET.md`, `docs/architecture/diagrams/likec4/` | The same documents, the plugin and skills in `backend/app/mcp/plugin/`, and the MCP QA checklist |
| Worker or asynchronous processing | ADR-012, `docs/architecture/domains/FORECASTING.md`, `docs/operations/` | Worker, operations, and architecture documentation as appropriate |
| New dependency or major service boundary | `docs/architecture/stack.md`, `docs/architecture/project-layout.md`, relevant ADRs | Stack, project layout, deployment docs, and an ADR (dependencies need human approval) |

This routing complements a ticket's `Documentation effects`; it does not
remove the need to inspect other documentation when a change spans rows.
