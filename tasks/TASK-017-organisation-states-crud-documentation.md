# TASK-017 Organisation States CRUD Documentation

## Source Plan

Approved plan: document the concrete Organisation States CRUD API and lifecycle behavior after backend CRUD is implemented.

This task captures documentation updates related to `TASK-016 Organisation States Backend CRUD`.

## Goal

Update relevant project documentation so the implemented scenario and organisation state CRUD behavior is clear to humans and AI agents.

The documentation should describe the concrete versioned API paths, lifecycle behavior, protected scenario behavior and validation rules without changing application code.

## Requirements

- Update `docs/domains/ORG_STATES.md` with the concrete CRUD endpoints.
- Update `docs/concepts/SCENARIO.md` with protected scenario backend mutation behavior.
- Update `docs/concepts/ORGANISATION_STATE.md` if the implementation documents target-date uniqueness as an API-level rule.
- Update API or local development documentation if endpoint usage is documented there.
- Keep documentation consistent with `TASK-016` implementation.
- Do not change application code.
- Do not change tests.
- Do not change database migrations.
- Do not update diagrams unless schema, fields, relationships or ownership changed during implementation.

## Acceptance Criteria

- [ ] Organisation States Domain documentation lists the implemented versioned CRUD paths.
- [ ] Organisation States Domain documentation describes scenario soft-delete propagation behavior used by the backend.
- [ ] Scenario concept documentation describes protected scenario mutation behavior.
- [ ] Organisation State concept documentation matches implemented org-state validation and lifecycle behavior.
- [ ] Documentation does not claim scenario copy or org-state graph-date synchronisation is implemented as part of CRUD.
- [ ] Data model and database documentation remain unchanged unless the implemented behavior changed logical or physical data model facts.
- [ ] Diagrams remain unchanged unless implementation changed schema, fields or relationships.
- [ ] No application code is modified.
- [ ] No migration is added.

## Out Of Scope

- Backend CRUD implementation.
- Frontend implementation.
- Scenario copy documentation beyond noting it remains a follow-up.
- Org-state graph-date synchronisation documentation beyond noting it remains a follow-up.
- Database schema documentation changes unless schema changed in another approved task.
- New ADRs unless the implementation introduced an architecture decision.

## Implementation Notes

- Depends on `TASK-016 Organisation States Backend CRUD`.
- Read these before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/decisions/ADR-001-tech-stack.md
docs/domains/ORG_STATES.md
docs/concepts/SCENARIO.md
docs/concepts/ORGANISATION_STATE.md
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
docs/TESTING.md
```

- Use the implemented behavior as the source for concrete endpoint descriptions.
- Preserve domain ownership language: Organisation States Domain owns scenarios, org states, events, timeseries and timeserie values.
- Preserve the architecture rule that other domains may reference another domain's data but may not modify another domain's tables directly.
- Do not invent copy, branching or graph-date synchronisation semantics.

## Testing

Required:

- [ ] Manual verification

Not applicable:

- [ ] Backend tests: documentation-only task.
- [ ] Frontend tests: documentation-only task.
- [ ] Integration tests: documentation-only task.
- [ ] Build: documentation-only task.
- [ ] Typecheck: documentation-only task.
- [ ] Lint: no configured documentation lint command is required unless one exists at implementation time.

Commands:

```bash
# No backend or frontend test commands are required for documentation-only changes.
```

Manual verification should cover:

- review Markdown formatting
- verify links and referenced paths are correct
- verify docs match `TASK-016` implementation

## Documentation

This task is documentation-only. Update only documentation that is relevant to the implemented CRUD behavior.

## Notes For AI Agent

- Toteuta vain taman taskin scope.
- Ala muuta sovelluskoodia.
- Ala muuta testejä.
- Ala muuta migraatioita.
- Ala paivita kaavioita ellei toteutus ole muuttanut skeemaa, kenttia, suhteita tai omistajuutta.
- Kerro lopuksi mita dokumentaatiota muutettiin ja miten tarkistit tyon.
