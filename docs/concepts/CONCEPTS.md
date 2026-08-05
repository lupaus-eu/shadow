# Concept Overview

Tämä dokumentti kuvaa järjestelmän keskeiset liiketoimintakäsitteet.

Status: initial concept model

Concept-dokumenttien tarkoitus on vastata kysymykseen:

```text
Mitä tämä käsite tarkoittaa järjestelmässä?
```

Domain-dokumentit vastaavat eri kysymykseen:

```text
Kuka omistaa tämän vastuun, datan ja API:n?
```

---

# Why Concepts Exist

Concept-dokumentteja käytetään, kun sama termi voi tarkoittaa eri asioita eri yhteyksissä tai kun käsitteellä on tärkeitä sääntöjä.

Ne auttavat:

- kehittäjiä
- AI-agentteja
- domain-mallin suunnittelua
- datamallin ymmärtämistä
- testien kirjoittamista

---

# Concept Documentation Rules

Jokaisella merkittävällä käsitteellä tulee olla oma dokumentti:

```text
docs/concepts/CUSTOMER.md
docs/concepts/INVOICE.md
docs/concepts/DOCUMENT.md
docs/concepts/AI_EXTRACTION.md
docs/concepts/ORGANISATION.md
docs/concepts/SCENARIO.md
docs/concepts/ORGANISATION_STATE.md
docs/concepts/METAMODEL.md
```

Uuden conceptin dokumentti luodaan mallista:

```text
docs/concepts/CONCEPT-TEMPLATE.md
```

AI-agentin tulee lukea relevantti concept-dokumentti ennen muutosta, joka koskee:

- käsitteen lifecycleä
- käsitteen invariantteja
- käsitteen kenttiä tai suhteita
- käsitteen tulkintaa eri domaineissa

---

# Core Concepts

## Organisation

Meaning:

- tenant-like organisation boundary for scenarios and organisation-specific metamodels

Owned By:

- Organisations Domain

Related Document:

- `docs/concepts/ORGANISATION.md`

## Scenario

Meaning:

- versioned planning or analysis context inside one organisation

Owned By:

- Organisation States Domain

Related Document:

- `docs/concepts/SCENARIO.md`

## Organisation State

Meaning:

- named scenario-specific snapshot of an organisation at a target date or version

Owned By:

- Organisation States Domain

Related Document:

- `docs/concepts/ORGANISATION_STATE.md`

## Metamodel

Meaning:

- default or organisation-specific type model defining allowed organisation twin nodes, edges and attributes

Owned By:

- Organisation Twin Structure Domain

Related Document:

- `docs/concepts/METAMODEL.md`

---

# Implemented Customer Domain Concepts

## Customer

Meaning:

- asiakas tai asiakasorganisaatio, johon järjestelmän muut tiedot voivat liittyä

Owned By:

- Customer Domain

Related Document:

- `docs/concepts/CUSTOMER.md`

Related Customer-owned concepts documented in the same file:

- Contact
- Customer Address

---

# Initial Candidate Concepts

## Invoice

Meaning:

- laskutettava tai laskutettu kokonaisuus, joka viittaa asiakkaaseen

Owned By:

- Billing Domain

Related Document:

- `docs/concepts/INVOICE.md`

## Document

Meaning:

- järjestelmään ladattu tiedosto tai tiedostosta muodostettu dokumenttiolio

Owned By:

- Document Domain

Related Document:

- `docs/concepts/DOCUMENT.md`

## AI Extraction

Meaning:

- AI:n tuottama rakenteinen poiminta lähdedatasta

Owned By:

- AI Domain

Related Document:

- `docs/concepts/AI_EXTRACTION.md`
