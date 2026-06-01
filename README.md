# schatten
Varjo:n inkarnaatio

Schatten on AI-first ohjelmistoprojekti.

## Aloita tästä

Päivittäisessä työssä riittää yleensä:

1. `AGENTS.md`
2. `CONTRIBUTING.md`
3. relevantti GitHub Issue tai `tasks/TASK-*.md`

Käytännön lukupolku:

- `README.md`: miten aloitan
- `CONTRIBUTING.md`: miten teen työn
- `docs/AI-DEVELOPMENT-WORKFLOW.md`: tarkempi prosessi tarvittaessa
- `tasks/TASK-*.md`: mitä oikeasti tehdään
- `AI-FIRST-ENGINEERING-HANDBOOK.md`: taustalla oleva käsikirja, jota ei tarvitse lukea joka kerta kokonaan

Lue lisäksi tarpeen mukaan:

- `ARCHITECTURE.md`, kun muutos koskee rakennetta tai järjestelmän osia
- `docs/domains/DOMAIN.md`, kun muutos koskee domainia tai datan omistajuutta
- `docs/concepts/CONCEPTS.md`, kun muutos koskee liiketoimintakäsitettä
- `docs/data/DATA-MODEL.md`, kun muutos koskee dataa tai tietokantaa
- `docs/TESTING.md`, kun muutos koskee sovelluskoodia tai testejä
- `docs/AI-DEVELOPMENT-WORKFLOW.md`, kun haluat tarkemman workflow-ohjeen
- `AI-FIRST-ENGINEERING-HANDBOOK.md`, kun tarvitset koko projektin kehityskäsikirjan

## DEV ympäristön setup

```bash
git clone git@github.com:reflector-oy/schatten.git
cd schatten
cp .env.example .env
```

Jos repository on jo alustettu paikallisesti:

```bash
git remote add origin git@github.com:reflector-oy/schatten.git
git pull origin main
cp .env.example .env
```

Teknologiapino on vielä `TBD`. Varsinaiset install-, dev-, test- ja build-komennot lisätään, kun `docs/decisions/ADR-001-tech-stack.md` hyväksytään.

## Kehitysworkflow

```text
Issue -> Task -> Branch -> AI Implementation -> Review -> Pull Request -> Merge
```

Katso tarkempi ohje:

- `CONTRIBUTING.md`
- `docs/AI-DEVELOPMENT-WORKFLOW.md`
