# Architecture

Tämä dokumentti kuvaa Schatten-projektin nykyisen arkkitehtuurin.

Tämän tiedoston tulee kuvata päätettyä tai toteutettua nykytilaa. Tulevaisuuden suunnitelmat, vaihtoehdot ja päätösten perustelut kirjataan ADR-dokumentteihin.

---

# Current Status

Status: project bootstrap

Sovelluksen varsinainen tekninen arkkitehtuuri on vielä päättämättä.

Tärkeimmät avoimet päätökset:

- teknologiapino
- frontend-rakenne
- backend-rakenne
- tietokantastrategia
- autentikointi ja valtuutus
- deployment-malli

Nämä päätetään ADR-dokumenteilla ennen toteutusta.

---

# System Overview

Tuotteen nimi: Schatten

Kuvaus: TBD

Kun tuotesuunta täsmentyy, lisää tähän lyhyt kuvaus:

- mitä järjestelmä tekee
- ketkä ovat käyttäjiä
- mitkä ovat MVP:n keskeiset käyttötapaukset

---

# Target Shape

Tämä on alustava tavoiterakenne, ei vielä toteutettu arkkitehtuuripäätös:

```text
Frontend
   |
   v
Backend/API
   |
   +--> Database
   |
   +--> External integrations
```

Kun stack on päätetty, päivitä tämä kaavio vastaamaan todellista toteutusta.

---

# Frontend

Status: TBD

Frontend-teknologiaa ei ole vielä päätetty.

Kun frontend päätetään, kirjaa tähän:

- framework
- hakemistorakenne
- state management -linjaus
- API-kutsujen sijainti
- autentikoinnin käsittely frontendissä
- testauskäytännöt

## Frontend Principles

Frontend ei saa olla järjestelmän turvallisuusraja.

Frontend ei:

- tee suoria tietokantakutsuja
- sisällä ensisijaista authorization-logiikkaa
- ohita backendin validointia

Kaikki luotettava data ja oikeustarkistus kulkee backendin kautta.

---

# Backend

Status: TBD

Backend-teknologiaa ei ole vielä päätetty.

Kun backend päätetään, kirjaa tähän:

- runtime ja framework
- API-rakenne
- moduulirakenne
- validointikäytäntö
- autentikointi- ja authorization-malli
- virheenkäsittely
- testauskäytännöt

## Backend Principles

Backend on järjestelmän luotettava sovelluskerros.

Backend vastaa:

- liiketoimintalogiikasta
- input validationista
- autentikoinnista
- valtuutuksesta
- tietokantaoperaatioista
- integraatioiden eristämisestä

---

# Database

Status: TBD

Tietokantaa ja ORM:ää ei ole vielä päätetty.

Kun tietokantapäätös tehdään, päivitä:

- `docs/decisions/ADR-002-database.md`
- tämä dokumentti
- paikallisen kehityksen ohjeet

## Database Principles

- Yksi ensisijainen totuuden lähde.
- Kaikki skeemamuutokset tehdään migraatioina.
- Migraatiot versionhallitaan.
- Tuotantotietokantaa ei muuteta käsin.

## Candidate Core Entities

Nämä ovat alustavia mahdollisia entiteettejä, eivät vielä lopullinen tietomalli:

```text
User
Organization
Membership
AuditEvent
```

Lopullinen tietomalli määritellään taskien ja ADR:ien kautta.

---

# Authentication

Status: TBD

Autentikointimalli päätetään ADR:llä.

Kirjaa päätöksen jälkeen:

- kirjautumistapa
- sessio- tai token-malli
- salasanapolitiikka, jos relevantti
- tokenien voimassaolo
- käyttäjän poistaminen ja deaktivointi

---

# Authorization

Status: TBD

Periaate:

- Kaikki resurssikohtaiset oikeudet tarkistetaan backendissä.
- Frontendin tarkistuksia käytetään vain käyttökokemukseen, ei turvallisuusmekanismina.
- Organization- ja membership-malli päätetään ennen käyttäjäkohtaisia resursseja.

---

# API Design

Status: TBD

Kun API-tyyli päätetään, kirjaa tähän:

- REST, GraphQL, RPC tai muu valittu malli
- endpointien nimeämiskäytäntö
- request/response-malli
- virheformaatti
- versionointikäytäntö, jos tarpeen

Alustava virheformaattisuositus:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Email is required"
  }
}
```

---

# Integrations

Status: TBD

Ulkoiset integraatiot kirjataan tähän, kun niitä lisätään.

## Integration Principles

Integraatiot eristetään adaptereihin tai palveluihin.

Ei:

```text
Business Logic -> direct third-party API call
```

Kyllä:

```text
Business Logic -> Domain Service -> Integration Adapter
```

Uusi merkittävä integraatio vaatii taskin ja tarvittaessa ADR:n.

---

# Background Jobs

Status: TBD

Jos projektiin lisätään ajastettuja töitä, queue tai worker-prosesseja, päätös dokumentoidaan ADR:llä.

Mahdollisia käyttötapauksia:

- sähköpostit
- raportit
- integraatiosynkronoinnit
- audit trail -prosessointi

---

# Observability

Status: TBD

## Logging

Tuotannossa sovellus kirjoittaa lokit stdoutiin.

Lokeihin ei saa kirjoittaa:

- salasanoja
- API-avaimia
- access tokeneita
- tarpeetonta henkilötietoa

## Metrics

Mahdollisia mittareita myöhemmin:

- request count
- error count
- response time
- job failure count

---

# Security

Pakolliset periaatteet:

- HTTPS tuotanto- ja staging-ympäristöissä
- input validation
- backend authorization checks
- secrets ympäristömuuttujissa tai secret managerissa
- parameterized SQL tai ORM:n turvalliset kyselyt

Kielletty:

- hardcoded secrets
- SQL injection -riskit
- sensitiivisen datan lokitus
- tuotantodatan käyttö testidatana ilman hyväksyntää

---

# Deployment

Status: TBD

Deployment-malli päätetään ADR:llä.

Alustava tavoite:

```text
GitHub
   |
   v
GitHub Actions
   |
   v
Build artifact / Docker image
   |
   +--> staging
   |
   +--> production
```

## Infrastructure Principles

Sovellusta ei sidota tarpeettomasti yhteen alustaan.

Ympäristöjen tulee käyttää:

- versionhallittua konfiguraatiota
- ympäristömuuttujia
- toistettavaa build- ja deployment-prosessia
- dokumentoitua tietokantayhteyttä

---

# ADR References

Päivitettävä, kun päätökset tehdään:

```text
ADR-001 Tech Stack
ADR-002 Database
ADR-003 Authentication
ADR-004 Deployment
```

---

# Architecture Constraints

AI-agenttien tulee noudattaa seuraavia sääntöjä.

## Do

- Noudata olemassa olevia kerroksia.
- Lisää uudet ominaisuudet oikeaan paikkaan.
- Käytä olemassa olevia palveluita ja abstrahointeja.
- Ehdota ADR:ää, jos toteutus vaatii arkkitehtuuripäätöksen.

## Don't

- Älä lisää uusia kerroksia ilman ADR:ää.
- Älä ohita backend-logiikkaa frontendistä.
- Älä lisää uusia infrastruktuurikomponentteja ilman päätöstä.
- Älä lukitse teknologiaa taskin sivutuotteena.

---

# Future Changes

Kun arkkitehtuuri muuttuu:

1. Lisää tai päivitä ADR tarvittaessa.
2. Päivitä tämä tiedosto.
3. Päivitä `AGENTS.md`, jos agenttien sääntöihin tai lukujärjestykseen tulee muutos.

Tämän dokumentin tulee aina kuvata järjestelmän nykytila.
