# Ticket 01: Tenants and memberships (080A)

Status: implemented

## Goal

The database and code know companies and their members; the existing data belongs to one company; the domain vocabulary is documented.

## Implementation

- Migration 027 `tenants`, `tenant_memberships` (+ down) as in the technical design, `users.role` nullable, backfill of the company "Reflector Oy" (D1) and memberships (D3) when users, Organisations or Customers exist.
- `app/platform/tenants.py`: models and a service (create company, add/change/remove membership with the last-Owner rule under row locks, list memberships of a person).
- Dev seed (`db/init/002_seed_development_data.sql`) creates "Development Company"; `bootstrap_admin.py` creates the account and, when no company exists, the company with the person as Owner.
- `CONTEXT.md` (Company/Tenant, Membership, Role), `docs/architecture/domains/TENANTS.md`.

## Acceptance criteria

- [ ] Migration up/down works on an empty and on a populated database; the backfill maps roles as D3.
- [ ] A second owner-less state is impossible: the service and the constraint trigger refuse removing or demoting the last Owner, also concurrently.
- [ ] Dev seed and bootstrap produce a company with an Owner.

## Testing

- Backend/API — service and migration tests on PostgreSQL 18, concurrency test for the last Owner
- Documentation — link check

## Documentation effects

- `docs/architecture/data/DATA-MODEL.md`, `DATABASE.md`, `domains/TENANTS.md`, DB diagram
- `CONTEXT.md`
- `docs/operations/local-development.md` (seed company)

## Blocked by

- none

## Completion record

## Ajetut tarkistukset

- [x] `ruff check`, `pyright` (yksi ennestään oleva virhe `ai_change_sets/service.py:381`), `pytest` koko sarja PostgreSQL 18:aa vasten: ks. ticket 02 (ajettu yhdessä). Migraatio 027 up/down ja backfill, last-Owner-sääntö (myös rinnakkain), bootstrap ja kehitysseed ajettu oikeaa tietokantaa vasten.

## AI review

- [x] Tuore subagentti (opus), 1 kierros. Löydökset: H1 backfill saattoi tehdä poistetusta/platform-tilistä Ownerin — **fixed** (vain aktiiviset `customer`-tilit; testi); M2 rinnakkaisuus: constraint trigger ei ollut rotuturvallinen — **fixed** (yrityksen rivilukko triggerissä); M4 trigger ja palvelu laskivat Ownerit eri tavoin — **fixed** (trigger laskee vain aktiiviset); M5 down-migraatio pudotti admin-oikeudet — **fixed** (omistaja/admin-jäsenyys → `role='admin'`); L6 bootstrapin yritysvalinta ilman ORDER BY — **fixed**; L7b duplikaattijäsenyys antoi IntegrityErrorin — **fixed** (savepoint → `already_member`). M3 (käyttäjän pehmeä poisto ohittaa Owner-säännön) — **jätetty**: kuuluu members-API:lle/käyttäjäpoistolle (ticket 08), kirjattu tiedetyksi aukoksi. L7a DELETE ilman `expected_version` — päätetään tickettissä 08. L8 (READ COMMITTED) — dokumentoitu moduulin docstringiin.
- Yksi kierros kolmesta.

## Documentation effects (tehty)

- [x] `CONTEXT.md`, `docs/architecture/domains/TENANTS.md`, `docs/architecture/data/DATA-MODEL.md`
