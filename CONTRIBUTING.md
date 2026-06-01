# Contributing

Tämä projekti käyttää AI-first kehitysmallia.

Lue ennen työn aloittamista:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `AI-FIRST-ENGINEERING-HANDBOOK.md`
4. `docs/domains/DOMAIN.md`
5. relevantti domain-dokumentti tiedostosta `docs/domains/`
6. `docs/concepts/CONCEPTS.md`
7. relevantti concept-dokumentti tiedostosta `docs/concepts/`
8. `docs/data/DATA-MODEL.md`, jos muutos koskee dataa
9. relevantti task tiedostosta `tasks/`

---

# Workflow

```text
Issue -> Issue Context / Task -> Branch -> AI Implementation -> Review -> Pull Request -> Merge
```

---

# 1. Create Or Pick Issue

Kaikki työ alkaa GitHub Issuesta.

Pieni muutos voi käyttää pelkkää issuea.

Jos käytät pelkkää issuea, agentille pitää antaa issuen sisältö joko kopioimalla se promptiin tai antamalla agentille toimiva GitHub-työkalu, esimerkiksi `gh issue view`.

Luo lisäksi `tasks/TASK-XXX-*.md`, jos työ:

- on monivaiheinen
- koskee useampaa moduulia
- muuttaa tietomallia
- vaikuttaa arkkitehtuuriin
- annetaan AI-agentille itsenäisesti toteutettavaksi

---

# 2. Give Issue Or Task Context

Agentti ei näe GitHub Issuea automaattisesti.

Käytä jotain näistä:

- Kopioi issuen title, body ja acceptance criteria agentin promptiin.
- Anna agentille lupa lukea issue GitHub CLI:llä: `gh issue view <number> --comments`.
- Tee issuesta task-tiedosto `tasks/TASK-XXX-*.md`.

Jos issue on epäselvä, tee task ennen koodausta.

Task-numeron oletus:

- Käytä task-numerona GitHub Issuen numeroa.
- Esimerkki: Issue `#42` -> `tasks/TASK-042-user-profile.md`.
- Branch: `feature/TASK-042-user-profile`.
- Jos yhdestä issuesta tulee useita taskeja, käytä suffiksia: `TASK-042A-*`, `TASK-042B-*`.

---

# 3. Create Branch

```bash
git checkout main
git pull origin main
git checkout -b feature/TASK-001-short-name
```

Jos taskia ei ole:

```bash
git checkout -b feature/ISSUE-042-short-name
```

Branch-prefixit:

```text
feature/
fix/
docs/
chore/
refactor/
```

---

# 4. Use AI Agent

Hyvä prompti:

```text
Lue AGENTS.md, ARCHITECTURE.md ja tasks/TASK-001-short-name.md.
Toteuta vain taskissa määritelty scope.
Älä lisää uusia riippuvuuksia ilman hyväksyntää.
Lisää testit ja päivitä dokumentaatio tarvittaessa.
Lopuksi kerro mitä muutettiin ja mitkä tarkistukset ajoit.
```

Jos käytät pelkkää issuea:

```text
Lue AGENTS.md ja ARCHITECTURE.md.
Toteuta alla oleva GitHub Issue #42.
Toteuta vain issuen scope.
Jos hyväksymiskriteerit ovat epäselvät, pysähdy ja kysy tarkennus.

[liitä issue tähän]
```

---

# 5. Verify Locally

Kun stack on päätetty, aja ennen PR:ää:

```bash
npm run lint
npm test
npm run build
```

Jos stack on vielä `TBD`, noudata taskissa määriteltyjä tarkistuksia.

---

# 6. Update Branch

```bash
git fetch origin
git rebase origin/main
```

---

# 7. Open Pull Request

Käytä `.github/PULL_REQUEST_TEMPLATE.md` -templatea.

PR:n pitää:

- liittyä yhteen issueen tai taskiin
- kuvata mitä tehtiin
- kertoa miten testattiin
- nostaa riskit esiin

---

# Commit Convention

Käytetään Conventional Commits -mallia:

```text
feat(scope): description
fix(scope): description
docs(scope): description
refactor(scope): description
test(scope): description
chore(scope): description
```

---

# Merge

Main-haaraan ei pushata suoraan.

Käytetään:

```text
Squash and Merge
```

Lopullisen mergen hyväksyy ihminen.
