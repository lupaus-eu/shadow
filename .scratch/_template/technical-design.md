# Technical design: <name>

Status: needs-triage

## Current and target state

- **Current state:** <Implemented behavior, API, or document that supports this>
- **Target state:** <What does this work change?>

## Domain

- <Concept and relationship; owning domain from `docs/architecture/domains/`>

## Database

- <Tables, fields, indexes, row-level security, and the paired SQL migrations
  `db/migrations/NNN_name.sql` / `NNN_name.down.sql` (ADR-002)>

## API

- <Method and route>
- <Request/response and errors>

## Frontend

- <Views, components, and state>

## Authentication and authorization

- <Who can do what?>

## Testing

- <Backend/API tests or why they do not apply>
- <Frontend/UI tests or why they do not apply>
- <Browser/E2E validation or why it does not apply>
- <Migration, integration, or architecture validation or why it does not apply>

Select checks using [`docs/agents/testing.md`](../../docs/agents/testing.md).
Every implementation ticket records its executed commands and results.

## Configuration

- <New environment variables, or no changes>

## Architecture effects

- <Effects on services, ports, data ownership, or integrations>

## Documentation effects

- [ ] Update `docs/user/`
- [ ] Update `docs/admin/`
- [ ] Update `docs/operations/` or `docs/runbooks/`
- [ ] Update `docs/gdpr/`
- [ ] Update `docs/legal/`
- [ ] Update `docs/architecture/` (including domains, concepts, data model, and diagrams)
- [ ] Update `docs/design/`
- [ ] Add or update `docs/adr/`
- [ ] Update `CONTEXT.md`
- [ ] Update `.env.example`
- [ ] No durable documentation effect

Name the affected paths and the ticket that makes each update. Use
[`architecture routing`](../../docs/agents/architecture-routing.md) to select
the applicable source documents.

## Options and decision

- <Options considered and chosen approach>
