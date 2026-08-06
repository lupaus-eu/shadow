# TASK-XXX Short Name

Create this task from a developer-approved AI implementation plan.

Use the next free task number by default:

```text
TASK-001-short-name
TASK-002-short-name
TASK-003-short-name
```

If one accepted plan is split into closely related tasks, use suffixes:

```text
TASK-042A-api
TASK-042B-ui
TASK-042C-tests
```

## Source Plan

Kirjaa lyhyesti hyväksytty suunnitelma tai sen olennainen osa, josta tämä task syntyi.

## Goal

Kuvaa yhdellä tai kahdella kappaleella mitä tällä tehtävällä halutaan saavuttaa.

## Requirements

- Requirement 1
- Requirement 2
- Requirement 3

## Acceptance Criteria

- [ ] Hyväksymiskriteeri 1
- [ ] Hyväksymiskriteeri 2
- [ ] Hyväksymiskriteeri 3

## Out Of Scope

- Asia joka ei kuulu tähän tehtävään
- Asia joka tehdään myöhemmin

## Implementation Notes

Kirjaa tekniset huomiot, tiedostot, rajaukset ja mahdolliset riippuvuudet.

Jos toteutus edellyttää arkkitehtuuripäätöstä, luo ADR ennen toteutusta.

Jos toteutus koskee tiettyä domainia, linkitä relevantti domain-dokumentti:

```text
docs/domains/<DOMAIN>.md
```

Jos toteutus koskee liiketoimintakäsitettä, linkitä relevantti concept-dokumentti:

```text
docs/concepts/<CONCEPT>.md
```

Jos toteutus muuttaa tietomallia tai skeemaa, linkitä:

```text
docs/data/DATA-MODEL.md
docs/data/DATABASE.md
db/migrations/README.md
```

Jokainen uusi `db/migrations/NNN_name.sql` pitää lisätä yhdessä vastaavan
`db/migrations/NNN_name.down.sql`-migraation kanssa. Lisää hyväksymiskriteerit
molempien suuntien ajolle disposable PostgreSQL -ympäristössä.

## Testing

Kuvaa miten työ tarkistetaan. Katso myös `docs/TESTING.md`.

Required:

- [ ] Frontend tests
- [ ] Backend tests
- [ ] Integration tests
- [ ] Manual verification
- [ ] Lint
- [ ] Build
- [ ] Typecheck

Not applicable:

- [ ] Reason:

Commands:

```bash
# Frontend, if applicable
cd frontend
pnpm lint
pnpm test
pnpm build

# Backend, if applicable
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

## Documentation

Päivitä tarvittaessa:

- `AGENTS.md`
- `ARCHITECTURE.md`
- `README.md`
- `docs/AI-DEVELOPMENT-WORKFLOW.md`
- `docs/LOCAL-DEVELOPMENT.md`
- `docs/TESTING.md`
- `docs/domains/DOMAIN.md`
- `docs/domains/<DOMAIN>.md`
- `docs/concepts/CONCEPTS.md`
- `docs/concepts/<CONCEPT>.md`
- `docs/data/DATA-MODEL.md`
- `docs/data/DATABASE.md`
- `docs/diagrams/*.puml`
- `docs/diagrams/generated/*.svg`
- `db/migrations/*.sql`
- `db/init/*.sql`
- `docs/decisions/*.md`

## Notes For AI Agent

- Lue `AGENTS.md` ja `ARCHITECTURE.md` ennen toteutusta.
- Lue relevantit ADR:t ennen teknologiaan, arkkitehtuuriin, tietokantaan, autentikointiin, integraatioihin tai deploymentiin koskevia muutoksia.
- Lue relevantit domain-dokumentit ennen domainin dataan, APIeihin tai sääntöihin koskevia muutoksia.
- Lue relevantit concept-dokumentit ennen käsitteen kenttiin, suhteisiin, invariantteihin tai lifecycleen koskevia muutoksia.
- Lue `docs/data/` ja `db/`-ohjeet ennen tietomalli- tai skeemamuutoksia.
- Toteuta vain tämän taskin scope.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Lisää testit, kun muutos koskee sovelluskoodia.
- Jos et lisää testejä sovelluskoodin muutokselle, perustele miksi.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.
