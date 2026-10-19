# Contributing

Tämä projekti käyttää AI-first kehitysmallia.

Lue ennen työn aloittamista:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `AI-FIRST-ENGINEERING-HANDBOOK.md`
4. `docs/decisions/ADR-001-tech-stack.md`
5. relevantti task tiedostosta `tasks/`
6. relevantit domain-, concept- ja data-dokumentit, jos muutos koskee niitä

---

# Workflow

```text
Idea -> AI Implementation Plan -> Developer Approval -> Task(s) -> Branch -> AI Implementation -> Review -> Pull Request -> Developer Merge
```

---

# 1. Ask AI For An Implementation Plan

Kaikki työ alkaa ideasta ja AI-agentin tekemästä toteutussuunnitelmasta.

Hyvä suunnitteluprompti:

```text
Tee toteutussuunnitelma seuraavasta ideasta.

Idea:
[kuvaa tavoite, ongelma, rajaukset ja tunnetut taustatiedot]

Lue AGENTS.md, ARCHITECTURE.md ja relevantit ADR:t ennen suunnitelmaa.
Älä muuta tiedostoja. Ehdota tarvittavat taskit ja hyväksymiskriteerit.
```

Kehittäjä hyväksyy suunnitelman tai pyytää siihen muutoksia ennen taskien luontia.

---

# 2. Create Task Context

Hyväksytystä suunnitelmasta luodaan yksi tai useampi task-tiedosto:

```text
tasks/TASK-XXX-short-name.md
```

Task-numeron oletus:

- Käytä seuraavaa vapaata `TASK-XXX`-numeroa.
- Branch käyttää samaa numeroa: `feature/TASK-042-user-profile`.
- Jos yksi hyväksytty suunnitelma jaetaan läheisesti liittyviin osiin, käytä suffiksia: `TASK-042A-*`, `TASK-042B-*`.

Task on toteutuksen pysyvä scope-lähde.

---

# 3. Create Branch

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

# 4. Use AI Agent

Hyvä toteutusprompti:

```text
Lue AGENTS.md, ARCHITECTURE.md, relevantit ADR:t ja tasks/TASK-001-short-name.md.
Toteuta vain taskissa määritelty scope.
Älä lisää uusia riippuvuuksia ilman hyväksyntää.
Lisää testit ja päivitä dokumentaatio tarvittaessa.
Lopuksi kerro mitä muutettiin ja mitkä tarkistukset ajoit.
```

---

# 5. Verify Locally

Tietokantamuutoksessa lisää aina pari:

```text
db/migrations/NNN_name.sql
db/migrations/NNN_name.down.sql
```

Älä muuta jo hyväksyttyä migraatiota. Testaa up ja down disposable-tietokannassa
`backend/migrate.py`-työkalulla ja lue ADR-002 ennen migraatiostrategian
muuttamista.

Backendin oletustarkistukset:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Valinnaisena repository-juuren Make-käyttöliittymä kokoaa samat tarkistukset:

```bash
make backend-check
make frontend-check
make check
```

`make install` asentaa backend- ja frontend-riippuvuudet eksplisiittisesti.
Tarkistustargetit eivät asenna riippuvuuksia automaattisesti. Säilytä yllä
olevat suorat komennot ensisijaisena dokumentoituna lähteenä ja käytä
`make help`-komentoa paikallisten, turvallisten kehitystargetien tarkasteluun.

Frontendin oletustarkistukset:

```bash
cd frontend
pnpm format:check
pnpm lint
pnpm test
pnpm build
```

Aja `pnpm format` (tai `make frontend-format`) ennen frontend-muutosten
commitointia. CI hylkää `frontend/`-hakemiston muotoilemattomat `.ts`-, `.tsx`-,
`.js`-, `.css`-, `.html`- ja `.json`-tiedostot.

Repository-juuren `.git-blame-ignore-revs` listaa commitit, jotka ovat
pääosin mekaanista muotoilua, kuten TASK-066B:n Prettier-muotoilun. GitHub
ohittaa ne blame-näkymässä automaattisesti. TASK-066B:n squash-commit sisältää
myös taskin CI-, `Makefile`- ja dokumentaatiomuutokset, joten blame ohittaa
nekin ja voi näyttää niille aiemman, asiaan liittymättömän commitin. Ota sama
asetus käyttöön paikallisesti:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

Näet ohitettujen rivien todellisen commitin ilman listaa:

```bash
git blame --ignore-revs-file="" <file>
```

Kun typecheck-scripti on lisätty frontendiin, aja myös se ennen PR:ää.

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

- liittyä yhteen taskiin
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

Lopullisen mergen tekee kehittäjä human reviewn jälkeen. AI-agentti ei mergaa main-haaraan.
