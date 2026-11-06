# Ticket 02: Company id on company data (080B)

Status: implemented

## Goal

Every company-owned row carries an immutable `tenant_id` that cannot disagree with its parent; inserts need no code change.

## Implementation

- Migration 028 (+ down): `tenant_id` on the 24 company tables; backfill; roots default from `app_tenant_id()`, children inherit by `BEFORE INSERT` trigger, `BEFORE UPDATE` immutability trigger; NOT NULL except the Metamodel family; helper functions `app_tenant_id()`, `app_user_id()`, `app_worker_scope()`.
- Unique indexes reviewed per table (list the result in the completion record); `organisations` name uniqueness per company; `(tenant_id, …)` list indexes.
- Foreign key `tenant_id` on `audit_events`, `background_jobs`, `outbox_messages`, `notifications` (nullable).
- Services and tests that create Organisations or Customers run with a company context (`RequestContext.tenant_id`); the reference seed writes the default Metamodel with NULL.

## Acceptance criteria

- [ ] After the migration no company row has a NULL `tenant_id` (except default Metamodel rows) and every child equals its parent's value.
- [ ] An insert without company context into a root table fails; a child insert ignores a supplied foreign `tenant_id`; an update of `tenant_id` fails.
- [ ] Two companies may use the same Organisation name; one company may not.
- [ ] The whole existing backend suite passes.

## Testing

- Backend/API — trigger, default, immutability, unique-index tests; migration with data up/down; full suite

## Documentation effects

- `docs/architecture/data/DATA-MODEL.md`, `DATABASE.md`, DB diagram
- `docs/operations/testing.md`

## Blocked by

- 01

## Completion record

## Ajetut tarkistukset

- [x] `ruff check .`, `pyright` (ennestään oleva yksi virhe), `pytest` koko sarja PostgreSQL 18:aa vasten (ks. commit-viesti), uudet testit `test_tenant_data_postgresql_integration.py` (juuri, perintö, immuutti, fail closed, per yritys uniikki nimi, oletusmetamalli, backfill, vieras vanhempi) ja päivitetyt PostgreSQL-fixturet (`tests/tenant_helpers.py`).
- Uniikki-indeksit käyty läpi: vain `ux_organisations_name_active_ci` muuttui `(tenant_id, lower(name))`; muut ovat satunnaisavaimia tai vanhempikohtaisia ja pysyvät globaaleina.

## AI review

- [x] Tuore subagentti (opus), 1 kierros. H1 lapsen yritys eri kuin vanhemman RLS:n piilottaessa vanhemman — **fixed** (puuttuva tai näkymätön vanhempi evätään, ei varayritystä); H2 vanhemman haku temp-taulun kaappaamana — **fixed** (haku skeemakohtaisesti `TG_TABLE_SCHEMA`); H3 vanhemman avaimen muutos siirsi rivin ilman yrityksen vaihtoa — **fixed** (`BEFORE UPDATE OF`-trigger + immuutti); M4 juuririvi toiselle yritykselle — **fixed** (`require_context_tenant_id`); L7 testiaukot — **fixed** (lisätty testit); L8 `audit_events`-FK estää yrityksen poiston — yrityksiä ei poisteta (dokumentoitu TENANTS.md:ssä). **Jätetty / siirretty:** M5 toissijaiset viiteavaimet (esim. `graph_edges.source_graph_node_id`, `graph_nodes.node_type_id`, `ai_change_sets.scenario_id`) voivat viitata toiseen yritykseen, koska FK-tarkistus ohittaa RLS:n — siirretty tickettiin 10 (RLS-politiikat + tarvittaessa komposiitti-FK:t/tarkistustriggerit); L6 triggerit hidastavat massa-INSERTiä ~3x — hyväksytty, mitattu `timeserie_values` 100k riviä 1,75 s vs 0,54 s.
- Yksi kierros kolmesta.

## Documentation effects (tehty)

- [x] `docs/architecture/data/DATA-MODEL.md`, `docs/operations/testing.md`
