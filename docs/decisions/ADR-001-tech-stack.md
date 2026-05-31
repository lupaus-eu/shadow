# ADR-001: Tech Stack

Status: Proposed

Date: TBD

---

# Context

Schatten-projekti on bootstrap-vaiheessa. Teknologiapinoa ei ole vielä päätetty.

WIP-dokumenteissa on suosituksia, mutta ne eivät ole vielä sitovia päätöksiä.

---

# Decision

TBD.

Päätä vähintään:

- frontend framework
- backend runtime ja framework
- ohjelmointikieli
- tietokanta
- ORM tai query layer
- testityökalut
- package manager
- local development -malli
- deployment target

---

# Options Considered

Täydennä päätöksen yhteydessä.

Mahdollisia WIP-suosituksissa mainittuja vaihtoehtoja:

- Next.js / React / TypeScript
- Node.js / TypeScript
- PostgreSQL
- Drizzle ORM
- Docker
- GitHub Actions
- Railway stagingiin
- UpCloud tai Scaleway tuotantoon

---

# Consequences

Täydennä päätöksen jälkeen:

- mitä tämä mahdollistaa
- mitä rajoitteita syntyy
- mitä dokumentteja pitää päivittää
- mitä CI-komentoja käytetään

---

# Follow-Up

Kun päätös on tehty:

- päivitä `ARCHITECTURE.md`
- päivitä `AGENTS.md` tarvittaessa
- päivitä `docs/LOCAL-DEVELOPMENT.md`
- ota käyttöön oikea CI-putki
- luo tarvittaessa seuraavat ADR:t tietokannasta, autentikoinnista ja deploymentista
