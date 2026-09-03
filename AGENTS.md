# AGENTS.md

Tämä tiedosto antaa AI-agenteille välttämättömän kontekstin ennen muutosten tekemistä.

Lue tämä ennen koodin kirjoittamista.

Laajempi prosessi on dokumentoitu tiedostossa `AI-FIRST-ENGINEERING-HANDBOOK.md`.

---

# Project

Projektin nimi: Schatten

Status: MVP / project bootstrap

Schatten on AI-first ohjelmistoprojekti. Tuotteen tarkka tavoite, kohderyhmä ja ongelma täsmennetään projektin ensimmäisissä task- ja ADR-dokumenteissa.

---

# Product Goal

TBD.

Kun tuotteen suunta päätetään, päivitä tähän:

- mitä rakennetaan
- kenelle rakennetaan
- mikä ongelma ratkaistaan
- mikä on ensimmäisen MVP:n rajaus

---

# Current Status

Projektissa ollaan aloitusvaiheessa.

Ensimmäiset tavoitteet:

1. AI-first kehitysmallin dokumentointi
2. paikallisen kehitysympäristön kuvaus
3. CI-baselinen käyttöönotto
4. ensimmäisten feature-taskien määrittely

---

# Tech Stack

Status: decided in `docs/decisions/ADR-001-tech-stack.md`

Päätetty teknologiapino:

- frontend: React, TypeScript, Vite, pnpm, Vitest, ESLint hakemistossa `frontend/`
- backend: Python, FastAPI, Pydantic, uv, pytest, pyright, Ruff hakemistossa `backend/`
- database: PostgreSQL
- ORM: SQLAlchemy
- migrations: repository-owned Python/Psycopg runner and paired SQL migrations
- authentication: repository-managed Authentik locally and Microsoft Entra ID
  in production; optional local Authentik-to-Entra federation is defined by
  ADR-006/TASK-040
- local runtime: frontend, backend ja database omissa Docker-konteissaan
- production-only deployment: Coolify Docker Compose, with portable
  frontend/backend images and the one-shot migration job defined by
  ADR-003/ADR-005

---

# Source Of Truth

Yleinen lähdejärjestys:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `docs/decisions/*.md`
4. `docs/domains/DOMAIN.md`
5. relevantit `docs/domains/<DOMAIN>.md` -tiedostot
6. `docs/concepts/CONCEPTS.md`
7. relevantit `docs/concepts/<CONCEPT>.md` -tiedostot
8. `docs/data/DATA-MODEL.md` ja `docs/data/DATABASE.md`, jos muutos koskee dataa tai skeemaa
9. `tasks/*.md`
10. `README.md`

Jos dokumentit ovat ristiriidassa:

- ADR voittaa vanhemman toteutuksen.
- `ARCHITECTURE.md` voittaa `README.md`:n.
- Domain-dokumentit määrittävät datan, APIen ja liiketoimintasääntöjen omistajuuden.
- Concept-dokumentit määrittävät käsitteiden merkityksen, invariantit ja lifecyclet.
- Data-dokumentit määrittävät loogisen ja fyysisen datamallin.
- Taskin scope määrittää toteutettavan työn.
- Jos vastausta ei löydy, kysy ihmisen päätös.

---

# Per Task Reading Order

Kun toteutat yksittäistä taskia, käytä tätä kevyempää käytännön järjestystä:

1. Lue `AGENTS.md`.
2. Lue `tasks/TASK-*.md`.
3. Lue `ARCHITECTURE.md`.
4. Lue relevantit ADR:t, jos muutos koskee teknologiaa, arkkitehtuuria, tietokantaa, autentikointia, integraatioita tai deploymentia.
5. Lue relevantit domain-dokumentit vain, jos muutos koskee domainin dataa, APIeja tai sääntöjä.
6. Lue relevantit concept-dokumentit vain, jos muutos koskee käsitteen kenttiä, suhteita, invariantteja tai lifecycleä.
7. Lue `docs/data/` ja `db/`-ohjeet vain, jos muutos koskee tietomallia, skeemaa, migraatioita tai init-skriptejä.
8. Lue `docs/TESTING.md`, jos muutos koskee sovelluskoodia tai testejä.
9. Toteuta muutos.
10. Aja relevantit tarkistukset.
11. Kerro lopuksi mitä muutettiin ja miten työ tarkistettiin.

Älä lue kaikkia dokumentteja jokaista pientä muutosta varten. Käytä lisädokumentteja silloin, kun taskin scope sitä koskee.

---

# Development Workflow

Kaikki merkittävä työ tehdään tämän putken kautta:

```text
Idea -> AI Implementation Plan -> Developer Approval -> Task(s) -> AI Implementation -> AI Review -> Human Review -> Pull Request -> Developer Merge -> Deploy
```

GitHubin työnhallintaa ei käytetä työn lähteenä. Hyväksytystä AI-suunnitelmasta luodut taskit määrittävät toteutuksen scopin.

---

# Agent Rules

## Always

- Toteuta vain taskissa määritelty scope.
- Lue arkkitehtuuri ja relevantit ADR:t ennen toteutusta.
- Lue relevantit domain-dokumentit ennen domainin dataan, APIeihin tai sääntöihin koskevia muutoksia.
- Lue relevantit concept-dokumentit ennen käsitteen kenttiin, suhteisiin, invariantteihin tai lifecycleen koskevia muutoksia.
- Lue `docs/data/` ja `db/`-ohjeet ennen tietomalli- tai skeemamuutoksia.
- Lue `docs/TESTING.md` ennen sovelluskoodin tai testien muuttamista.
- Päivitä `docs/diagrams/` PlantUML-lähteet ja generoidut SVG:t, jos muutos vaikuttaa arkkitehtuurikuviin, domain-kuviin tai workflow-kuviin.
- Lisää tai päivitä testit, kun muutos koskee sovelluskoodia.
- Jos et lisää testejä sovelluskoodin muutokselle, perustele miksi.
- Päivitä dokumentaatio tarvittaessa.
- Tallenna jokainen Step 13 AI-review-kierros validina, redaktoituna JSON-
  recordina `docs/ai-reviews/`-hakemistoon ja noudata
  `docs/AI-REVIEW-RECORDS.md`:n schemaa sekä analyysin advisory-rajausta.
- Käytä olemassa olevia abstrahointeja.
- Suosi pieniä muutoksia.
- Kerro lopuksi mitä muutit ja miten tarkistit työn.

## Never

- Älä commitoi salaisuuksia.
- Älä lisää uusia riippuvuuksia ilman hyväksyntää.
- Älä poista testejä ilman hyväksyntää.
- Älä muuta tuotantotietokantaa käsin.
- Älä muuta arkkitehtuuria ilman ADR:ää.
- Älä mergaa main-haaraan.
- Älä tee tuotantojulkaisua ilman ihmisen hyväksyntää.

---

# Branch And PR Rules

Branch-nimi:

```text
feature/TASK-001-short-name
fix/TASK-002-short-name
docs/TASK-003-short-name
chore/TASK-004-short-name
refactor/TASK-005-short-name
```

Jokaisen PR:n tulee:

- liittyä yhteen taskiin
- sisältää testit tai perustella miksi testejä ei tarvita
- läpäistä CI, kun CI on käytössä
- olla reviewattavissa kohtuullisessa ajassa

Suositus:

- alle 500 riviä reviewattavaa muutosta

---

# Database Rules

Kaikki skeemamuutokset:

- migraatioina
- versionhallinnassa
- taskissa ja tarvittaessa ADR:ssä kuvattuina
- pareina: `NNN_name.sql` ja `NNN_name.down.sql`

Jokaisen uuden up-migraation mukana pitää lisätä saman muutoksen peruuttava down-migraatio.
Migraatiot ajetaan `backend/migrate.py`-työkalulla ADR-002:n mukaisesti.

Kielletty:

```sql
ALTER TABLE production ...
```

manuaalisesti tuotantoympäristössä.

---

# Security Rules

Pakollista:

- input validation
- authentication checks
- authorization checks backendissä
- parameterized SQL tai ORM:n turvalliset kyselyt
- salaisuudet ympäristömuuttujissa tai secret managerissa

Kielletty:

- hardcoded secrets
- API-avaimet repositoryssa
- testidatan käyttö tuotannossa
- sensitiivisen datan lokittaminen

---

# Documentation Rules

Päivitä dokumentaatio jos:

- arkkitehtuuri muuttuu
- tietomalli muuttuu
- domain boundary tai domain ownership muuttuu
- conceptin merkitys, invariantit tai lifecycle muuttuu
- arkkitehtuurikuva, domain-kuva tai workflow-kuva muuttuu
- integraatio muuttuu
- deployment muuttuu
- uusi toimintamalli lisätään

Luo uusi ADR kun:

- valitaan uusi teknologia
- muutetaan arkkitehtuuria
- vaihdetaan tietokantastrategiaa
- muutetaan deployment-mallia
- lisätään merkittävä uusi ulkoinen integraatio

---

# Human Ownership

AI voi:

- kirjoittaa koodia
- kirjoittaa testejä
- tehdä rajattuja refaktorointeja
- päivittää dokumentaatiota
- ehdottaa arkkitehtuuripäätöksiä

Ihmiset omistavat:

- tuotteen suunnan
- arkkitehtuurin
- tietoturvan
- tuotantojulkaisut
- lopulliset hyväksynnät

---

# Definition Of Done

Työ on valmis kun:

- hyväksymiskriteerit täyttyvät
- testit läpäisevät, kun testit ovat relevantteja
- CI on vihreä, kun CI on käytössä
- review tehty
- dokumentaatio päivitetty tarvittaessa
- PR mergeattu

---

# Final Rule

Jos olet epävarma:

Älä arvaa.

Tarkista:

1. Task
2. Architecture
3. ADR:t
4. Handbook

Jos vastausta ei löydy, pyydä ihmisen päätös.
