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

# Initial Concepts

## Customer

Meaning:

- asiakas tai asiakasorganisaatio, johon järjestelmän muut tiedot voivat liittyä

Owned By:

- Customer Domain

Related Document:

- `docs/concepts/CUSTOMER.md`

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
