# Shadowin feature-portfolio

> Tämä näkymä muodostetaan `.scratch`-tiedostojen `Status:`-riveistä ja hyväksymiskriteerien valintaruuduista. Päivitä se komennolla `python3 scripts/scratch-status.py > .scratch/_PORTFOLIO.md` aina, kun feature tai ticket etenee.

| Feature | Toteutustila | Ticketit | Seuraava ticket | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [Feature: All AI use happens in the user's own agent](agent-owned-ai/PRD.md) | implemented | 5/5 | — | — |
| [Feature: Sign in with Authentik](authentik-sign-in/PRD.md) | implemented | 5/5 | — | — |
| [Feature: Model timeline (Base line, events and scenarios)](model-timeline/PRD.md) | ready for implementation | 10/11 | [11 documentation and vocabulary](model-timeline/issues/11-documentation-and-vocabulary.md) — ready-for-agent | — |
| [Feature: Shadow models (digital twin of an organisation)](shadow-models/PRD.md) | implemented (written after the fact, 2026-11-07; the features were built in | 0/0 | — | — |
| [Feature: Structure canvas (full-width drawing tool)](structure-canvas/PRD.md) | ready for implementation | 8/9 | [09 Accessibility, texts, browser test and documentation](structure-canvas/issues/09-accessibility-texts-docs.md) — ready-for-agent | — |
| [Feature: Companies (tenants) and roles](tenants-and-roles/PRD.md) | wontfix | 2/11 | — | — |

## Tekniset työt

> Tekninen työ seurataan omana listanaan; se ei muuta tuotefeatureiden toteutusastetta.

| Tekninen työ | Toteutustila | Ticketit | Seuraava ticket | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [Technical design: Compose file for local development with live reload](tech-dev-compose/technical-design.md) | implemented | 1/1 | — | — |
| [Technical design: Platform foundation (backend)](tech-platform-foundation/technical-design.md) | implemented | 4/4 | — | — |

## Avoimet ticketit

> *Aloitettavissa* tarkoittaa, että kaikki ticketin estäjät ovat `implemented` tai `resolved`. *Avoimia kriteerejä* laskee ticketin rastittamattomat hyväksymiskriteerit.

### Feature: Model timeline (Base line, events and scenarios)

| Ticket | Tila | Avoimia kriteerejä | Aloitettavissa | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [11 documentation and vocabulary](model-timeline/issues/11-documentation-and-vocabulary.md) | ready-for-agent | 1 | kyllä | — |

### Feature: Structure canvas (full-width drawing tool)

| Ticket | Tila | Avoimia kriteerejä | Aloitettavissa | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [09 Accessibility, texts, browser test and documentation](structure-canvas/issues/09-accessibility-texts-docs.md) | ready-for-agent | 5 | kyllä | — |

## Tilan tulkinta

- **implemented**: kaikki ticketit ovat `implemented` tai `resolved`.
- **in progress**: vähintään yksi ticket on varattu (`claimed`).
- **needs decision**: vähintään yksi ticket odottaa liiketoiminta-, suunnittelu- tai ympäristöpäätöstä (`needs-info`, `ready-for-human`).
- **ready for implementation**: ticketit ovat valmiita toteutukseen (`ready-for-agent`), eikä mikään odota päätöstä.
- **Seuraava ticket**: ensimmäinen toimenpidettä odottava ticket, jonka estäjät ovat valmiit; jos sellaista ei ole, ensimmäinen toimenpidettä odottava ticket.

Tekniset työt ovat erillään tuotefeatureista, jotta niiden tila ei sekoita tuotetoimituksen edistymistä.
