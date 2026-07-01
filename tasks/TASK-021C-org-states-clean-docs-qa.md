# TASK-021C Org States Clean Docs And QA

## Source Plan

Approved plan: document the Clean Organisation States behavior after backend
and frontend implementation, and provide manual QA guidance and PR-ready
verification notes.

This task exists so implementation scope in `TASK-021A` and `TASK-021B` stays
small while documentation and verification guidance remain explicit.

## Goal

Update relevant documentation to describe the organisation-state cleanup
endpoint and user flow accurately after implementation, and capture the manual
QA steps needed for review and PR preparation.

This task must not introduce application behavior changes.

## Requirements

- Depends on:
  - `TASK-021A Org States Clean Backend`
  - `TASK-021B Org States Clean Frontend`
- Update documentation to describe the implemented cleanup behavior.
- Document the cleanup endpoint in the Organisation States domain docs:
  - `POST /api/v1/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/clean`
- Document the implemented response shape:
  - `{ "cleaned": <n> }`
- Document the implemented mutation rules:
  - cleanup uses soft-delete semantics
  - protected scenarios cannot be cleaned through normal backend flows
  - scenario `initial_state_id` is cleared when the initial state is cleaned
- Update local usage or QA notes if manual testing steps are documented there.
- Add or update a concise manual QA checklist for the PR flow.
- Do not modify application code.
- Do not add tests.
- Do not add a database migration.
- Do not claim authentication or authorization was implemented as part of this
  task set.

## Acceptance Criteria

- [ ] Relevant docs describe the cleanup endpoint path and response shape.
- [ ] Relevant docs describe cleanup as soft-delete behavior rather than hard
      delete.
- [ ] Relevant docs describe protected-scenario cleanup blocking consistently
      with implementation.
- [ ] Relevant docs mention initial-state reference clearing when applicable.
- [ ] Manual QA steps cover success, protected-scenario rejection and no-op
      cleanup behavior.
- [ ] Documentation does not claim auth or authorization was added by this work.
- [ ] No application code is modified.
- [ ] No migration is added.

## Out Of Scope

- Backend implementation.
- Frontend implementation.
- Auth or authorization design.
- Database schema documentation changes unless implementation changed a schema
  fact in another approved task.
- New ADR unless implementation revealed a genuine architecture decision.
- Diagram updates unless implementation changed ownership, relationships or
  architectural flow enough to require them.

## Implementation Notes

- Depends on `TASK-021A` and `TASK-021B` being implemented first.
- Read these before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-001-tech-stack.md
docs/domains/ORG_STATES.md
docs/concepts/SCENARIO.md
docs/concepts/ORGANISATION_STATE.md
docs/LOCAL-DEVELOPMENT.md
docs/TESTING.md
```

- Use the implemented behavior as the source of truth. Do not document planned
  behavior that did not ship.
- Keep language aligned with existing repo rules:
  - protected scenario mutation returns `409`
  - cleanup uses soft-delete semantics
  - auth remains a future concern
- Update only the documents that materially improve clarity for future humans
  and AI agents.

## Testing

Required:

- [ ] Manual verification

Not applicable:

- [ ] Frontend tests: documentation-only task.
- [ ] Backend tests: documentation-only task.
- [ ] Integration tests: documentation-only task.
- [ ] Lint: no documentation-specific lint command is required by default.
- [ ] Build: documentation-only task.
- [ ] Typecheck: documentation-only task.

Commands:

```bash
# No backend or frontend test commands are required for documentation-only changes.
```

Manual verification should cover:

- verify updated Markdown formatting and links
- verify endpoint paths match implemented backend routes
- verify described UI flow matches implemented frontend behavior
- verify QA checklist is usable for PR review

## Documentation

Expected documentation targets:

- `docs/domains/ORG_STATES.md`
- `docs/concepts/SCENARIO.md`
- `docs/concepts/ORGANISATION_STATE.md`
- `docs/LOCAL-DEVELOPMENT.md`, if local verification steps need updating

Update diagrams or data docs only if implemented behavior changed those facts in
an approved task.

## Notes For AI Agent

- Lue `AGENTS.md` ja `ARCHITECTURE.md` ennen toteutusta.
- Lue relevantit domain-, concept-, local-development- ja testing-dokumentit
  ennen toteutusta.
- Toteuta vain taman taskin scope.
- Ala muuta sovelluskoodia, testejä tai migraatioita tassa taskissa.
- Ala dokumentoi toteuttamatonta behavioria.
- Kerro lopuksi mita dokumentaatiota muutettiin ja miten tarkistit tyon.
