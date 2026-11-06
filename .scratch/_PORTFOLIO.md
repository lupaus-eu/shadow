# Shadow'n feature-portfolio

> Tämä näkymä muodostetaan `.scratch`-tiedostojen `Status:`-riveistä ja hyväksymiskriteerien valintaruuduista. Päivitä se komennolla `python3 scripts/scratch-status.py > .scratch/_PORTFOLIO.md` aina, kun feature tai ticket etenee.

| Feature | Toteutustila | Ticketit | Seuraava ticket | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [Feature: Sign in with Authentik](authentik-sign-in/PRD.md) | implemented | 5/5 | — | — |
| [Feature: Companies (tenants) and roles](tenants-and-roles/PRD.md) | needs decision | 0/11 | [01 Tenants and memberships (080A)](tenants-and-roles/issues/01-tenants-and-memberships.md) — needs-info | — |

## Tekniset työt

> Tekninen työ seurataan omana listanaan; se ei muuta tuotefeatureiden toteutusastetta.

| Tekninen työ | Toteutustila | Ticketit | Seuraava ticket | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [Technical design: Platform foundation (backend)](tech-platform-foundation/technical-design.md) | implemented | 4/4 | — | — |

## Avoimet ticketit

> *Aloitettavissa* tarkoittaa, että kaikki ticketin estäjät ovat `implemented` tai `resolved`. *Avoimia kriteerejä* laskee ticketin rastittamattomat hyväksymiskriteerit.

### Feature: Companies (tenants) and roles

| Ticket | Tila | Avoimia kriteerejä | Aloitettavissa | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [01 Tenants and memberships (080A)](tenants-and-roles/issues/01-tenants-and-memberships.md) | needs-info | 3 | kyllä | — |
| [02 Company id on company data (080B)](tenants-and-roles/issues/02-tenant-id-on-company-data.md) | needs-info | 4 | ei | 01 |
| [03 Company access, session and sign-in accounts (080C)](tenants-and-roles/issues/03-tenant-access.md) | needs-info | 3 | ei | 01, 02 |
| [04 Company routes: Organisations and Customers (080D, part 1)](tenants-and-roles/issues/04-routes-organisations-and-customers.md) | needs-info | 3 | ei | 03 |
| [05 Company routes: scenarios, states, structure, metrics (080D, part 2)](tenants-and-roles/issues/05-routes-scenarios-and-structure.md) | needs-info | 2 | ei | 03 |
| [06 Company routes: predictions, change sets, prediction worker (080D, part 3)](tenants-and-roles/issues/06-routes-predictions-change-sets-and-worker.md) | needs-info | 3 | ei | 03 |
| [07 MCP company context (080E)](tenants-and-roles/issues/07-mcp-company-context.md) | needs-info | 2 | ei | 04, 05, 06 |
| [08 Members API (080F)](tenants-and-roles/issues/08-members-api.md) | needs-info | 3 | ei | 03 |
| [09 Frontend company context (080F, UI)](tenants-and-roles/issues/09-frontend-company-context.md) | needs-info | 3 | ei | 04, 05, 06, 07, 08 |
| [10 Row-level security and isolation tests (080G)](tenants-and-roles/issues/10-row-level-security.md) | needs-info | 2 | ei | 04, 05, 06, 07, 08 |
| [11 Drop users.role (080G, cleanup)](tenants-and-roles/issues/11-drop-users-role.md) | needs-info | 1 | ei | 07, 08, 09 |

## Tilan tulkinta

- **implemented**: kaikki ticketit ovat `implemented` tai `resolved`.
- **in progress**: vähintään yksi ticket on varattu (`claimed`).
- **needs decision**: vähintään yksi ticket odottaa liiketoiminta-, suunnittelu- tai ympäristöpäätöstä (`needs-info`, `ready-for-human`).
- **ready for implementation**: ticketit ovat valmiita toteutukseen (`ready-for-agent`), eikä mikään odota päätöstä.
- **Seuraava ticket**: ensimmäinen toimenpidettä odottava ticket, jonka estäjät ovat valmiit; jos sellaista ei ole, ensimmäinen toimenpidettä odottava ticket.

Tekniset työt ovat erillään tuotefeatureista, jotta niiden tila ei sekoita tuotetoimituksen edistymistä.
