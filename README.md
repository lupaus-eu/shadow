# schatten
Varjo:n inkarnaatio

Schatten on AI-first ohjelmistoprojekti.

## Aloita tästä

Lue dokumentit tässä järjestyksessä:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `AI-FIRST-ENGINEERING-HANDBOOK.md`
4. `docs/AI-DEVELOPMENT-WORKFLOW.md`
5. `docs/LOCAL-DEVELOPMENT.md`

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
