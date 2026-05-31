# Contributing

Tämä projekti käyttää AI-first kehitysmallia.

Lue ennen työn aloittamista:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `AI-FIRST-ENGINEERING-HANDBOOK.md`
4. relevantti task tiedostosta `tasks/`

---

# Workflow

```text
Issue -> Task -> Branch -> AI Implementation -> Review -> Pull Request -> Merge
```

---

# 1. Create Or Pick Issue

Kaikki työ alkaa GitHub Issuesta.

Pieni muutos voi käyttää pelkkää issuea.

Luo lisäksi `tasks/TASK-XXX-*.md`, jos työ:

- on monivaiheinen
- koskee useampaa moduulia
- muuttaa tietomallia
- vaikuttaa arkkitehtuuriin
- annetaan AI-agentille itsenäisesti toteutettavaksi

---

# 2. Create Branch

```bash
git checkout main
git pull origin main
git checkout -b feature/TASK-001-short-name
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

# 3. Use AI Agent

Hyvä prompti:

```text
Lue AGENTS.md, ARCHITECTURE.md ja tasks/TASK-001-short-name.md.
Toteuta vain taskissa määritelty scope.
Älä lisää uusia riippuvuuksia ilman hyväksyntää.
Lisää testit ja päivitä dokumentaatio tarvittaessa.
Lopuksi kerro mitä muutettiin ja mitkä tarkistukset ajoit.
```

---

# 4. Verify Locally

Kun stack on päätetty, aja ennen PR:ää:

```bash
npm run lint
npm test
npm run build
```

Jos stack on vielä `TBD`, noudata taskissa määriteltyjä tarkistuksia.

---

# 5. Update Branch

```bash
git fetch origin
git rebase origin/main
```

---

# 6. Open Pull Request

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
