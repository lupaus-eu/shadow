# Diagrams

Tämä hakemisto sisältää projektin versionhallittavat diagrammilähteet.

Diagrammien ensisijainen formaatti on PlantUML.

Generoidut kuvat tallennetaan hakemistoon:

```text
docs/diagrams/generated/
```

---

# Diagram Rules

## Architecture Diagrams

Arkkitehtuurikuvat piirretään C4 frameworkilla käyttäen PlantUML:ää.

Käytä C4-tasoja:

- C4 Level 1: System Context
- C4 Level 2: Container
- C4 Level 3: Component
- C4 Level 4: Code, vain jos siitä on selkeä hyöty

Pidä C4-kuvat synkassa `ARCHITECTURE.md`:n ja ADR-dokumenttien kanssa.

## Domain And Concept Diagrams

Domain- ja concept-tason kuvissa saa käyttää myös muita PlantUML-kaaviotyyppejä, kun ne kuvaavat asiaa paremmin:

- state diagrams domain- tai concept-lifecycleen
- sequence diagrams cross-domain workflow'hin
- activity diagrams prosessikuvauksiin
- component diagrams domainien välisiin riippuvuuksiin

Domain-kuvien tulee vastata `docs/domains/`-dokumentaatiota.

## Mermaid

Mermaid on sallittu vain silloin, kun se on tarkoituksenmukaisempi kuin PlantUML.

Tällä hetkellä Mermaid `gitGraph` on sallittu Git-branchien visualisointiin, koska PlantUML:ssä ei ole vastaavaa natiivia gitGraph-kaaviota.

---

# Directory Layout

```text
docs/diagrams/
├── README.md
├── c4-l1-system-context-<scope>.puml
├── c4-l2-container-<scope>.puml
├── c4-l3-component-<scope>.puml
├── data-logical-model.puml
├── db-physical-schema.puml
├── state-<domain>-<concept>.puml
├── sequence-<workflow>.puml
└── generated/
    ├── c4-l1-system-context-<scope>.svg
    ├── c4-l2-container-<scope>.svg
    ├── c4-l3-component-<scope>.svg
    ├── data-logical-model.svg
    ├── db-physical-schema.svg
    ├── state-<domain>-<concept>.svg
    └── sequence-<workflow>.svg
```

---

# Naming Convention

Käytä lowercase kebab-case -nimiä.

## C4 Diagrams

```text
c4-l1-system-context-<scope>.puml
c4-l2-container-<scope>.puml
c4-l3-component-<scope>.puml
c4-l4-code-<scope>.puml
```

Esimerkkejä:

```text
c4-l1-system-context-schatten.puml
c4-l2-container-schatten.puml
c4-l3-component-customer-domain.puml
```

## Domain And Concept Diagrams

```text
domain-<domain>-overview.puml
state-<domain>-<concept>.puml
concept-<domain>-<concept>.puml
sequence-<workflow>.puml
activity-<workflow>.puml
```

Esimerkkejä:

```text
domain-customer-overview.puml
state-document-lifecycle.puml
concept-ai-extraction-result.puml
sequence-create-customer.puml
activity-ai-document-classification.puml
```

## Data And Database Diagrams

```text
data-logical-model.puml
db-physical-schema.puml
db-<domain>-schema.puml
```

Esimerkkejä:

```text
data-logical-model.puml
db-physical-schema.puml
db-customer-schema.puml
```

## Generated SVGs

Generoidun SVG:n nimi on sama kuin PlantUML-lähteen nimi:

```text
docs/diagrams/c4-l1-system-context-schatten.puml
docs/diagrams/generated/c4-l1-system-context-schatten.svg
```

Älä muokkaa generoituja SVG-tiedostoja käsin. Muokkaa `.puml`-lähdettä ja renderöi SVG uudelleen.

---

# C4 PlantUML Template

Käytä C4-PlantUML-syntaksia, kun kuvaat C4-tasoja.

Esimerkki:

```plantuml
@startuml
!include <C4/C4_Context>

title Schatten - System Context

Person(user, "User", "Primary user")
System(schatten, "Schatten", "AI-first application")
System_Ext(github, "GitHub", "Source control and pull requests")

Rel(user, schatten, "Uses")
Rel(schatten, github, "Integrates with")

@enduml
```

Jos PlantUML-ympäristö ei tue C4-kirjastoa suoraan, lisää projektiin tai renderöintiympäristöön tarvittava C4-PlantUML-tuki ennen diagrammin muuttamista.

---

# Rendering

Project diagrams can be rendered through the Docker Compose docs profile:

```bash
docker compose --profile docs build diagram-renderer
docker compose --profile docs run --rm diagram-renderer
```

By default, `diagram-renderer` renders:

```text
docs/diagrams/db-physical-schema.puml
```

to:

```text
docs/diagrams/generated/db-physical-schema.svg
```

Render the logical data model with an explicit source argument:

```bash
docker compose --profile docs run --rm diagram-renderer \
  -tsvg -o generated data-logical-model.puml
```

Jos paikallinen PlantUML-serveri on käytössä portissa `9000`, renderöi SVG:t serverin kautta.

Projektissa käytetty oletus:

```text
http://localhost:9000
```

Kun lisäät uuden diagrammin:

1. Luo `.puml` tiedostoon `docs/diagrams/`.
2. Renderöi vastaava `.svg` tiedostoon `docs/diagrams/generated/`.
3. Linkitä SVG Markdownista suhteellisella polulla.
4. Commitoi sekä `.puml` että `.svg`, jos SVG:tä käytetään dokumentaatiossa.
