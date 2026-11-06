# TASK-026 UI polish


## Source Plan

Small UI tweaks here and there for a cleaner and easier to understand UI.
Planning and task creation and implementation done mostly manually (I ran out of tokens).

## Goal

Make it easier to understand which form fields are mandatory by appending "*" to the field label. Small aestetic imrpovements. 

## Requirements

- Form fields that are mandatory should have a label ending with "*".
- Frontend tests should pass.
- Keep this task scoped to frontend changes.

## Acceptance Criteria

- [ ] Form fields that are mandatory should have a label ending with "*".
- [ ] Form save buttons disabled if not all mandatory fields filled out.
- [ ] No new dependency is added.

## Out Of Scope

- No changes to backend nor documentation.

## Implementation Notes

Only update the frontend.

## Testing

Kuvaa miten työ tarkistetaan. Katso myös `docs/operations/testing.md`.

Required:

- [ ] Frontend tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build

Not applicable:

- [ ] Backend tests: backend code is not changed in this task.
- [ ] Integration tests: frontend unit coverage is the default expected level.
- [ ] Typecheck: no dedicated frontend typecheck command is currently defined
      in the repository workflow.

Commands:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

## Documentation

No documentation updates are expected beyond this task file unless the implementation changes visible workflow details that future agents or humans need to understand.

Do not update architecture, ADR, domain, concept, data, or diagram documentation unless implementation reveals a genuine documentation mismatch.

## Notes For AI Agent

- Lue `AGENTS.md` ja `docs/architecture/overview.md` ennen toteutusta.
- Lue relevantit ADR:t ennen teknologiaan, arkkitehtuuriin, tietokantaan, autentikointiin, integraatioihin tai deploymentiin koskevia muutoksia.
- Lue relevantit domain-dokumentit ennen domainin dataan, APIeihin tai sääntöihin koskevia muutoksia.
- Lue relevantit concept-dokumentit ennen käsitteen kenttiin, suhteisiin, invariantteihin tai lifecycleen koskevia muutoksia.
- Lue `docs/architecture/data/` ja `db/`-ohjeet ennen tietomalli- tai skeemamuutoksia.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Lisää testit, kun muutos koskee sovelluskoodia.
- Jos et lisää testejä sovelluskoodin muutokselle, perustele miksi.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
