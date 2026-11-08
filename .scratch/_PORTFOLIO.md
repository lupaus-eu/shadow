# Shadowin feature-portfolio

> Tämä näkymä muodostetaan `.scratch`-tiedostojen `Status:`-riveistä ja hyväksymiskriteerien valintaruuduista. Päivitä se komennolla `python3 scripts/scratch-status.py > .scratch/_PORTFOLIO.md` aina, kun feature tai ticket etenee.

| Feature | Toteutustila | Ticketit | Seuraava ticket | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [Feature: All AI use happens in the user's own agent](agent-owned-ai/PRD.md) | implemented | 5/5 | — | — |
| [Feature: Sign in with Authentik](authentik-sign-in/PRD.md) | implemented | 5/5 | — | — |
| [Feature: Model timeline (Base line, events and scenarios)](model-timeline/PRD.md) | ready for implementation | 11/12 | [12 start row in the change list](model-timeline/issues/12-start-row-in-the-change-list.md) — ready-for-agent | — |
| [Feature: Shadow models (digital twin of an organisation)](shadow-models/PRD.md) | implemented (written after the fact, 2026-11-07; the features were built in | 0/0 | — | — |
| [Feature: Structure canvas (full-width drawing tool)](structure-canvas/PRD.md) | implemented | 9/9 | — | — |
| [Feature: Companies (tenants) and roles](tenants-and-roles/PRD.md) | wontfix | 2/11 | — | — |

## Tekniset työt

> Tekninen työ seurataan omana listanaan; se ei muuta tuotefeatureiden toteutusastetta.

| Tekninen työ | Toteutustila | Ticketit | Seuraava ticket | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [Technical design: Change terminology (rename event to Change, change to Edit)](tech-change-terminology/technical-design.md) | ready for implementation | 1/3 | [02 rename frontend](tech-change-terminology/issues/02-rename-frontend.md) — ready-for-agent | — |
| [Technical design: Compose file for local development with live reload](tech-dev-compose/technical-design.md) | implemented | 1/1 | — | — |
| [Technical design: Platform foundation (backend)](tech-platform-foundation/technical-design.md) | implemented | 4/4 | — | — |

## Avoimet ticketit

> *Aloitettavissa* tarkoittaa, että kaikki ticketin estäjät ovat `implemented` tai `resolved`. *Avoimia kriteerejä* laskee ticketin rastittamattomat hyväksymiskriteerit.

### Feature: Model timeline (Base line, events and scenarios)

| Ticket | Tila | Avoimia kriteerejä | Aloitettavissa | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [12 start row in the change list](model-timeline/issues/12-start-row-in-the-change-list.md) | ready-for-agent | 4 | kyllä | — |

### Technical design: Change terminology (rename event to Change, change to Edit)

| Ticket | Tila | Avoimia kriteerejä | Aloitettavissa | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [02 rename frontend](tech-change-terminology/issues/02-rename-frontend.md) | ready-for-agent | 3 | kyllä | — |
| [03 documents and vocabulary sweep](tech-change-terminology/issues/03-documents-and-vocabulary-sweep.md) | ready-for-agent | 2 | ei | 02 |

## Tilan tulkinta

- **implemented**: kaikki ticketit ovat `implemented` tai `resolved`.
- **in progress**: vähintään yksi ticket on varattu (`claimed`).
- **needs decision**: vähintään yksi ticket odottaa liiketoiminta-, suunnittelu- tai ympäristöpäätöstä (`needs-info`, `ready-for-human`).
- **ready for implementation**: ticketit ovat valmiita toteutukseen (`ready-for-agent`), eikä mikään odota päätöstä.
- **Seuraava ticket**: ensimmäinen toimenpidettä odottava ticket, jonka estäjät ovat valmiit; jos sellaista ei ole, ensimmäinen toimenpidettä odottava ticket.

Tekniset työt ovat erillään tuotefeatureista, jotta niiden tila ei sekoita tuotetoimituksen edistymistä.
