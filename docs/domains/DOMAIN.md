# Domain Overview

Tämä dokumentti kuvaa järjestelmän domainit ja niiden omistajuudet.

Status: initial candidate domain map

Tavoite:

- auttaa kehittäjiä
- auttaa AI-agentteja
- määritellä domain boundaryt
- selkeyttää datan ja APIen omistajuutta

Kun domain-malli muuttuu, päivitä tämä tiedosto ja relevantti domain-kohtainen dokumentti.

---

# Domain Documentation Rules

Jokaisella domainilla tulee olla oma tarkentava dokumentti:

```text
docs/domains/CUSTOMER.md
docs/domains/BILLING.md
docs/domains/DOCUMENT.md
docs/domains/AI.md
docs/domains/FORECASTING.md
docs/domains/USERS.md
docs/domains/ORGANISATIONS.md
docs/domains/ORG_STATES.md
docs/domains/ORG_TWIN_STRUCTURE.md
```

Uuden domainin dokumentti luodaan mallista:

```text
docs/domains/DOMAIN-TEMPLATE.md
```

AI-agentin tulee lukea domain-dokumentti ennen muutoksia, jotka koskevat:

- domainin omistamia tauluja
- domainin APIeja
- domainin sääntöjä
- domainien välisiä riippuvuuksia

---

# Core Domains

The core domain model covers users, organisations, scenarios, organisation states, organisation twin structure and metamodels.

These domains define the MVP source of truth for access-facing identities, tenant-like organisation boundaries and the graph-based organisation twin data model.

ADR-004's implemented initial authorization model treats every active User as
trusted across every organisation. Users administration is `admin`-only; both
roles may use every other business domain. Organisation relationships remain
data ownership boundaries and do not imply membership authorization. Every
authenticated unsafe request uses the shared Origin/CSRF guard, and mutation
services receive the authenticated User explicitly for audit writes.

## Users Domain

Responsible for:

- application user records
- user role data
- future Entra ID identity mapping

Owns:

- users

Does NOT Own:

- organisations
- scenarios
- organisation twin structure

Depends On:

- Microsoft Entra ID, when authentication is implemented

Primary APIs:

- `/users`

Related Documents:

- `docs/domains/USERS.md`

## Organisations Domain

Responsible for:

- organisation records
- active organisation name uniqueness
- organisation-level scenario boundaries
- organisation-specific metamodel ownership

Owns:

- organisations

Does NOT Own:

- users
- scenario-owned state snapshots
- graph nodes or graph edges

Depends On:

- Users Domain for audit references

Primary APIs:

- `/organisations`

Related Documents:

- `docs/domains/ORGANISATIONS.md`

## Organisation States Domain

Responsible for:

- scenarios
- organisation state snapshots
- events
- scenario-owned timeseries

Owns:

- scenarios
- org_states
- events
- timeseries
- timeserie_values

Does NOT Own:

- organisations
- graph structure inside an organisation state
- metamodel type definitions

Depends On:

- Organisations Domain
- Users Domain for audit references

Primary APIs:

- `/scenarios`
- `/org-states`
- `/events`
- `/timeseries`

Related Documents:

- `docs/domains/ORG_STATES.md`

## Organisation Twin Structure Domain

Responsible for:

- metamodels
- node and edge type definitions
- allowed graph connections
- scenario graph history, graph nodes and graph edges

Owns:

- metamodels
- node_types
- edge_types
- type_attributes
- allowed_connections
- graph_nodes
- graph_edges

Does NOT Own:

- organisations
- scenarios
- organisation state lifecycle
- timeseries values

Depends On:

- Organisations Domain
- Organisation States Domain
- Users Domain for audit references

Primary APIs:

- `/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph`
- `/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/types`
- `/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/nodes`
- `/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/edges`
- `/organisations/{organisation_key}/scenarios/{scenario_key}/org-states/{org_state_key}/graph/positions`

Related Documents:

- `docs/domains/ORG_TWIN_STRUCTURE.md`

## Forecasting Domain

Status: accepted in ADR-007; implementation is deferred to TASK-041B and
TASK-041C.

Responsible for:

- immutable derived prediction versions
- target-metric prediction records and per-model result metadata
- dated prediction points and model/source-input audit snapshots

Owns:

- planned prediction version and result tables

Does NOT Own:

- organisations, scenarios, events or timeserie values
- graph nodes, graph edges or metamodels
- manually entered Reality data

Depends On:

- Organisations Domain
- Organisation States Domain for Reality values, target scenarios and events
- Organisation Twin Structure Domain for target-scenario graph history
- Users Domain for audit references

Primary APIs:

- planned organisation-scoped prediction preflight, creation, list and detail
  APIs; public routes are defined in TASK-041B

Related Documents:

- `docs/decisions/ADR-007-predictions-forecasting-domain.md`
- `docs/domains/FORECASTING.md`

---

# Customer Domain

Responsible for:

- customer profiles
- contacts
- addresses
- customer lifecycle

Owns:

- customers
- contacts
- customer_addresses

Does NOT Own:

- invoices
- payments
- subscriptions

Depends On:

- None

Primary APIs:

- `/customers`
- `/customers/{customer_id}/contacts`
- `/customers/{customer_id}/addresses`

Related Documents:

- `docs/domains/CUSTOMER.md`

---

# Billing Domain

Responsible for:

- invoices
- invoice lines
- payments
- subscriptions

Owns:

- invoices
- invoice_lines
- payments
- subscriptions

Does NOT Own:

- customer profile data

Depends On:

- Customer Domain

Primary APIs:

- `/invoices`
- `/payments`

Related Documents:

- `docs/domains/BILLING.md`

---

# Document Domain

Responsible for:

- uploaded documents
- document metadata
- document lifecycle

Owns:

- documents
- document_versions

Does NOT Own:

- customer data
- billing data

Depends On:

- Customer Domain

Primary APIs:

- `/documents`

Related Documents:

- `docs/domains/DOCUMENT.md`

---

# AI Domain

Responsible for:

- AI classifications
- AI summaries
- AI extractions

Owns:

- ai_classifications
- ai_summaries
- ai_extractions

Does NOT Own:

- customer data
- document data
- billing data

Depends On:

- Customer Domain
- Document Domain

Primary APIs:

- `/ai/classify`
- `/ai/extract`
- `/ai/summarize`

Related Documents:

- `docs/domains/AI.md`
