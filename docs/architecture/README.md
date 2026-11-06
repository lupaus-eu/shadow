# Yearclock architecture

This directory holds Yearclock's durable technical context. It complements
`CONTEXT.md`, which owns the business glossary, and `.scratch/`, which owns
feature-specific and changing plans.

## Contents

- [Technology stack](stack.md)
- [Project layout](project-layout.md)
- [Docker and local services](docker.md)
- [Database and isolation](database.md)
- [API](api.md), [authentication](authentication.md), and
  [organization authorization](organization-authorization-matrix.md)
- [Frontend](frontend.md), [events](events.md), [recurrence](recurrence.md),
  [date and time](date-and-time.md), and [localization](localization.md)
- [Billing](billing.md), [email](email.md), [workers](workers.md),
  [audit](audit.md), and [support access](support-access.md)
- [Deployment](deployment.md) and [lifecycle defaults](lifecycle-defaults.md)
- Models:
  - the [C4 model](c4/README.md) (LikeC4): system context, containers,
    components, flows, and deployment;
  - the [database model](dbml/README.md) (DBML), generated from the migrated
    schema.

Accepted, durable decisions belong in [`docs/adr/`](../adr/README.md).
Feature-specific technical designs and tickets belong in
[`.scratch/`](../../.scratch/README.md).
