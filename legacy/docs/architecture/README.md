# Shadow architecture

This directory holds Shadow's durable technical context: what is decided and
implemented now. It complements `CONTEXT.md`, which owns the business
glossary, and `.scratch/`, which owns feature-specific and changing plans.

## Contents

- [Architecture overview](overview.md) — the full description of the current system
- [Technology stack and status](stack.md)
- [Project layout](project-layout.md)
- [Deployment](deployment.md) — release topology, configuration contract, backups, and operator commands
- Domains: [domain overview](domains/DOMAIN.md) and one document per domain in
  [`domains/`](domains/) (data, API, and business-rule ownership)
- Concepts: [concept overview](concepts/CONCEPTS.md) and one document per concept in
  [`concepts/`](concepts/) (meaning, invariants, and lifecycle)
- Data: [logical data model](data/DATA-MODEL.md) and [physical database](data/DATABASE.md)
- Diagrams: [PlantUML and LikeC4 sources and generated SVGs](diagrams/README.md)

Templates for new domain and concept documents are
[`domains/DOMAIN-TEMPLATE.md`](domains/DOMAIN-TEMPLATE.md) and
[`concepts/CONCEPT-TEMPLATE.md`](concepts/CONCEPT-TEMPLATE.md).

Accepted, durable decisions belong in [`docs/adr/`](../adr/README.md).
Feature-specific technical designs and tickets belong in
[`.scratch/`](../../.scratch/README.md).
