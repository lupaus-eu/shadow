# AI Development Workflow

Tämä dokumentti kuvaa käytännön työnkulun, kun kehittäjä käyttää AI-agenttia toteutuksessa.

Laajemmat säännöt ovat tiedostossa `AI-FIRST-ENGINEERING-HANDBOOK.md`.

---

# Short Version

```text
Issue
-> Task
-> Branch
-> AI implementation
-> Local verification
-> Push
-> Pull Request
-> CI
-> AI review
-> Human review
-> Squash merge
-> Deploy
```

---

# Step By Step

## 1. Select Or Create Issue

Luo GitHub Issue ennen työn aloittamista.

Issue riittää yksin, jos muutos on pieni ja yksiselitteinen.

Luo lisäksi task-tiedosto, jos muutos:

- koskee useampaa osaa sovelluksesta
- muuttaa tietomallia
- lisää integraation
- vaatii useita hyväksymiskriteerejä
- annetaan AI-agentille itsenäisesti toteutettavaksi

## 2. Create Task

Kopioi `tasks/TASK-TEMPLATE.md` uuteen tiedostoon:

```text
tasks/TASK-001-short-name.md
```

Taskin pitää kertoa agentille:

- mitä tehdään
- mitä ei tehdä
- millä kriteereillä työ hyväksytään
- miten työ testataan

## 3. Create Branch

```bash
git checkout main
git pull origin main
git checkout -b feature/TASK-001-short-name
```

Käytä branch-prefixejä:

```text
feature/
fix/
docs/
chore/
refactor/
```

Käytä prefixejä näin:

- `feature/` kun lisäät uuden käyttäjälle tai järjestelmälle näkyvän toiminnon
- `fix/` kun korjaat bugin tai virheellisen toiminnan
- `docs/` kun muutos koskee vain dokumentaatiota
- `chore/` kun teet ylläpitotyötä, joka ei muuta sovelluksen toimintaa
- `refactor/` kun muutat koodin rakennetta ilman tarkoituksellista toiminnallista muutosta

## 4. Prompt AI Agent

Hyvä perusprompti:

```text
Lue AGENTS.md, ARCHITECTURE.md ja tasks/TASK-001-short-name.md.
Toteuta vain taskissa määritelty scope.
Älä lisää uusia riippuvuuksia ilman hyväksyntää.
Lisää testit ja päivitä dokumentaatio tarvittaessa.
Lopuksi kerro mitä muutettiin ja mitkä tarkistukset ajoit.
```

Jos työ koskee tietokantaa, lisää:

```text
Kaikki skeemamuutokset pitää tehdä migraatioina. Älä muuta tuotantotietokantaa.
```

Jos työ koskee arkkitehtuuria, lisää:

```text
Jos toteutus vaatii arkkitehtuurimuutoksen, pysähdy ja ehdota ADR:ää ennen koodausta.
```

## 5. Review Agent Output Locally

Kehittäjä tarkistaa diffistä:

- toteuttaako muutos taskin
- lisäsikö agentti turhaa scopea
- lisäsikö agentti riippuvuuksia
- poistuiko testejä
- jäikö dokumentaatio päivittämättä

## 6. Run Verification

Kun stack on valittu, aja vähintään:

```bash
npm run lint
npm test
npm run build
```

Jos stack on vielä päättämättä, aja taskissa määritellyt tarkistukset.

## 7. Update Branch

Ennen PR:ää:

```bash
git fetch origin
git rebase origin/main
```

Ratkaise konfliktit ja aja tarkistukset uudelleen.

## 8. Push

```bash
git push -u origin feature/TASK-001-short-name
```

## 9. Open Pull Request

Käytä `.github/PULL_REQUEST_TEMPLATE.md` -templatea.

PR:ssä pitää näkyä:

- summary
- related issue/task
- acceptance criteria
- testing
- risks

## 10. AI Review

Pyydä AI-agenttia reviewaamaan diff tai PR.

AI-reviewn pitää etsiä:

- bugeja
- regressioita
- tietoturvaongelmia
- puuttuvia testejä
- dokumentaatiopuutteita
- taskin ulkopuolista scopea

## 11. Human Review

Ihminen tarkistaa lopullisesti:

- scope
- arkkitehtuuri
- turvallisuus
- tietokantamuutokset
- ylläpidettävyys

## 12. Merge

Käytä:

```text
Squash and Merge
```

Squash-commit:

```text
feat(scope): short description
fix(scope): short description
docs(scope): short description
```

---

# Parallel Developer Flow

```mermaid
gitGraph
  commit id: "main: baseline"
  branch dev-a
  checkout dev-a
  commit id: "A: branch TASK-001"
  commit id: "A: AI implements feature"
  commit id: "A: tests and docs"
  checkout main
  branch dev-b
  checkout dev-b
  commit id: "B: branch TASK-002"
  commit id: "B: AI implements fix"
  checkout main
  merge dev-a id: "PR #1 squash merge"
  checkout dev-b
  commit id: "B: rebase on main"
  commit id: "B: resolve feedback"
  checkout main
  merge dev-b id: "PR #2 squash merge"
```

Periaate:

- jokainen kehittäjä tekee oman branchin mainista
- jokainen työ linkitetään issueen tai taskiin
- branch päivitetään mainista ennen PR:ää
- mainiin päätyy vain reviewattu ja squashattu muutos

---

# When To Stop And Ask

Pysähdy ja pyydä ihmisen päätös, jos AI-agentti:

- ehdottaa uutta riippuvuutta
- muuttaa arkkitehtuuria
- muuttaa tietokantastrategiaa
- tarvitsee salaisuuksia tai tuotantopääsyä
- haluaa poistaa testejä
- toteuttaa taskin ulkopuolista scopea
