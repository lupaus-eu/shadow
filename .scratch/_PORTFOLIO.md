# Shadowin feature-portfolio

> Tämä näkymä muodostetaan `.scratch`-tiedostojen `Status:`-riveistä ja hyväksymiskriteerien valintaruuduista. Päivitä se komennolla `python3 scripts/scratch-status.py > .scratch/_PORTFOLIO.md` aina, kun feature tai ticket etenee.

| Feature | Toteutustila | Ticketit | Seuraava ticket | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [Feature: All AI use happens in the user's own agent](agent-owned-ai/PRD.md) | implemented | 5/5 | — | — |
| [Feature: Sign in with Authentik](authentik-sign-in/PRD.md) | implemented | 5/5 | — | — |
| [Feature: Model timeline (Base line, events and scenarios)](model-timeline/PRD.md) | ready for implementation | 1/11 | [02 migrate versions to lines](model-timeline/issues/02-migrate-versions-to-lines.md) — ready-for-agent | — |
| [Feature: Shadow models (digital twin of an organisation)](shadow-models/PRD.md) | implemented (written after the fact, 2026-11-07; the features were built in | 0/0 | — | — |
| [Feature: Structure canvas (full-width drawing tool)](structure-canvas/PRD.md) | ready for implementation | 0/9 | [01 Full-width layout and collapsible panels](structure-canvas/issues/01-full-width-layout.md) — ready-for-agent | — |
| [Feature: Companies (tenants) and roles](tenants-and-roles/PRD.md) | needs decision | 2/11 | [03 Company access, session and sign-in accounts (080C)](tenants-and-roles/issues/03-tenant-access.md) — needs-info | — |

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
| [02 migrate versions to lines](model-timeline/issues/02-migrate-versions-to-lines.md) | ready-for-agent | 3 | kyllä | — |
| [03 read api lines events state](model-timeline/issues/03-read-api-lines-events-state.md) | ready-for-agent | 3 | ei | 02 |
| [04 metrics simulations analysis by line](model-timeline/issues/04-metrics-simulations-analysis-by-line.md) | ready-for-agent | 3 | ei | 03 |
| [05 event write routes with chain validation](model-timeline/issues/05-event-write-routes-with-chain-validation.md) | ready-for-agent | 4 | ei | 03 |
| [06 scenarios and positions](model-timeline/issues/06-scenarios-and-positions.md) | ready-for-agent | 3 | ei | 05 |
| [07 canvas edit routes and in use](model-timeline/issues/07-canvas-edit-routes-and-in-use.md) | ready-for-agent | 3 | ei | 05 |
| [08 adopt scenario mcp tools and retire versions](model-timeline/issues/08-adopt-scenario-mcp-tools-and-retire-versions.md) | ready-for-agent | 3 | ei | 06, 07 |
| [09 frontend event list and scenario picker](model-timeline/issues/09-frontend-event-list-and-scenario-picker.md) | ready-for-agent | 3 | ei | 04, 06, 07 |
| [10 performance and limits](model-timeline/issues/10-performance-and-limits.md) | ready-for-agent | 2 | ei | 05, 06 |
| [11 documentation and vocabulary](model-timeline/issues/11-documentation-and-vocabulary.md) | ready-for-agent | 1 | ei | 08, 09 |

### Feature: Structure canvas (full-width drawing tool)

| Ticket | Tila | Avoimia kriteerejä | Aloitettavissa | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [01 Full-width layout and collapsible panels](structure-canvas/issues/01-full-width-layout.md) | ready-for-agent | 5 | kyllä | — |
| [02 Adopt diagram-js with the graph domain layer and useGraphState](structure-canvas/issues/02-adopt-diagram-js.md) | ready-for-agent | 7 | ei | 01 |
| [03 Navigation (zoom, fit, pan, keyboard)](structure-canvas/issues/03-navigation.md) | ready-for-agent | 5 | ei | 02 |
| [04 Type list, filter and search](structure-canvas/issues/04-type-list-and-filter.md) | ready-for-agent | 6 | ei | 02, 03 |
| [05 Drawing (new nodes, connecting, deleting, multi-select, undo and redo)](structure-canvas/issues/05-drawing.md) | ready-for-agent | 8 | ei | 03, 04 |
| [06 Hover popovers, label shortening and node metrics](structure-canvas/issues/06-hover-labels-and-metrics.md) | ready-for-agent | 4 | ei | 02 |
| [07 Snap, align, auto layout, minimap and export](structure-canvas/issues/07-layout-tools-minimap-export.md) | ready-for-agent | 5 | ei | 05 |
| [08 Time control (scenario picker, event list, edits into the selected event)](structure-canvas/issues/08-time-control.md) | ready-for-agent | 6 | ei | 02, 05 |
| [09 Accessibility, texts, browser test and documentation](structure-canvas/issues/09-accessibility-texts-docs.md) | ready-for-agent | 5 | ei | 01, 02, 03, 04, 05, 06, 07 |

### Feature: Companies (tenants) and roles

| Ticket | Tila | Avoimia kriteerejä | Aloitettavissa | Odottaa ticketejä |
| --- | --- | ---: | --- | --- |
| [03 Company access, session and sign-in accounts (080C)](tenants-and-roles/issues/03-tenant-access.md) | needs-info | 3 | kyllä | — |
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
