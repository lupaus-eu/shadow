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
2. teknologiapinon päätös ADR:llä
3. paikallisen kehitysympäristön kuvaus
4. CI-baselinen käyttöönotto
5. ensimmäisten feature-taskien määrittely

---

# Tech Stack

Status: TBD

Älä lukitse teknologioita tähän ennen ADR-päätöstä.

Kun päätös tehdään, päivitä:

- `docs/decisions/ADR-001-tech-stack.md`
- `ARCHITECTURE.md`
- tarvittaessa tämä tiedosto

Mahdolliset WIP-suositukset eivät ole vielä päätöksiä.

---

# Source Of Truth

Lue lähteet tässä järjestyksessä:

1. `AGENTS.md`
2. `ARCHITECTURE.md`
3. `docs/decisions/*.md`
4. `tasks/*.md`
5. `README.md`

Jos dokumentit ovat ristiriidassa:

- ADR voittaa vanhemman toteutuksen.
- `ARCHITECTURE.md` voittaa `README.md`:n.
- Taskin scope määrittää toteutettavan työn.
- Jos vastausta ei löydy, kysy ihmisen päätös.

---

# Development Workflow

Kaikki merkittävä työ tehdään tämän putken kautta:

```text
Issue -> Task -> AI Implementation -> AI Review -> Human Review -> Pull Request -> Merge -> Deploy
```

Pieni yksiselitteinen muutos voi käyttää pelkkää GitHub Issuea. Laajempi tai AI-agentille itsenäisesti annettava työ tarvitsee task-tiedoston.

---

# Agent Rules

## Always

- Toteuta vain taskissa tai issuessa määritelty scope.
- Lue arkkitehtuuri ja relevantit ADR:t ennen toteutusta.
- Lisää tai päivitä testit, kun muutos koskee sovelluskoodia.
- Päivitä dokumentaatio tarvittaessa.
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

- liittyä yhteen issueen tai taskiin
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
