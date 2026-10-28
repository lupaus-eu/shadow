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
docs/concepts/AI_CHANGE_SET.md
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

Current authenticated application mutations populate nullable audit-user
relationships consistently: `created_by` for creation, `modified_by` for
updates and domain mutation actions, and `deleted_by` for persistence soft
deletion. Historical, seed and pre-authentication null values remain valid and
are not backfilled.

Organisation-scoped relationships below define data ownership, not current
user membership. Under ADR-004's internal-tool trust boundary, both active
roles may use all non-Users concepts across every organisation; Users
administration remains `admin`-only.

## User And Authentication Persistence

Meaning:

- application user allowlist entry, durable external identity binding,
  short-lived login transaction and opaque server-side session

Owned By:

- Users Domain

Related Document:

- `docs/concepts/USER.md`

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

## AI Change Set

Status: accepted design in ADR-015; schema and engine implemented by
TASK-069I; MCP write and change-set read tools implemented by TASK-069J;
review API implemented by TASK-069K; review UI pending TASK-069M

Meaning:

- organisation-scoped, ordered list of typed operations staged by a user's AI
  client through MCP, applied or rejected only by a human in Schatten

Owned By:

- AI Domain

Related Document:

- `docs/concepts/AI_CHANGE_SET.md`

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

Status: unplanned candidate outside ADR-015's MCP scope

Meaning:

- AI:n tuottama rakenteinen poiminta lähdedatasta

Owned By:

- AI Domain

Related Document:

- `docs/concepts/AI_EXTRACTION.md`
