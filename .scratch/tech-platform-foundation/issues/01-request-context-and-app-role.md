# Ticket 01: Request context and application role (078A)

Status: implemented

## Goal

Uusi koodi voi ajaa transaktion `shadow_app`-roolilla ja pyyntökontekstilla; nykyiset reitit toimivat ennallaan.

## Implementation

- Migraatio 021: `shadow_app` (NOLOGIN, NOBYPASSRLS), grantit, omistajaroolin jäsenyys.
- `core/database.py`: `RequestContext` (`user_id`, `tenant_id`, `support_access_id`, `invitation_token_hash`, `worker_scope`), `apply_request_context`, `transaction_session`, engine-poolin koko ympäristömuuttujista.
- Ei muuteta `get_db_session`:a eikä yhtään nykyistä reittiä. Ei politiikkoja.

## Acceptance criteria

- [x] Migraatio 021 ylös ja alas puhtaasti.
- [x] `transaction_session` ajaa `SET LOCAL ROLE shadow_app` ja asettaa GUC:t transaktion ajaksi.
- [x] GUC:t ja rooli eivät vuoda seuraavaan transaktioon.
- [x] `make backend-check` ja nykyiset testit läpi ilman muutoksia reitteihin.

## Testing

- [x] Backend — GUC-asetus, tyhjä konteksti, rooli
- [x] Migraatio/integraatio — rooli ja grantit PostgreSQL:ssä, GUC:ien nollautuminen
- [x] Frontend/E2E — ei sovellu

## Ajetut tarkistukset

- [x] `ruff check .` (backend) — passed.
- [x] `pytest` koko sarja, `MIGRATION_TEST_DATABASE_URL` PostgreSQL 18.3:een (paikallinen, portti 55432) — passed lopullinen ajo korjausten jälkeen 1410 passed, 7 skipped (skipped: ei-PostgreSQL-ympäristön testit).
- [x] `pyright` — yksi virhe `ai_change_sets/service.py:381`, sama ilman tämän ticketin muutoksia (väliaikaisen venvin uudempi SQLAlchemy kuin `uv.lock`); uusia virheitä ei.
- [x] `docker compose config` (dev) ja production-compose renderöitynä — poolimuuttujat näkyvät `backend`- ja `prediction-worker`-palveluissa, `migration`-palvelun env ennallaan. `.github/scripts/verify-production-compose.sh` ei ajettavissa tällä koneella (vaatii bash 4, macOS:ssä 3.2); CI ajaa sen.
- Ympäristörajoitus: `uv` puuttui koneelta, joten `make backend-check` ajettiin väliaikaisella venvillä (scratchpad), samoilla ruff-, pytest- ja pyright-komennoilla.

## AI review

- [x] Tuore subagentti (opus), taso `high`, 1 kierros; sai vain ticketin, ADR:n ja diffin. Ei korkean vakavuuden löydöksiä. Löydökset:
  1. medium, ennestään olevan `shadow_app`-roolin attribuuttien tarkistus puuttui — **fixed** (`ALTER ROLE … NOBYPASSRLS NOLOGIN …` aina; testi).
  2. medium, poolimuuttujat eivät välittyneet composessa — **fixed** (dev- ja production-compose).
  3. low, `max_overflow`-oletus 5 muutti nykykäytöstä — **fixed** (oletus 10). Lisäksi: virheellisen arvon validointi `config.py`:ssä — **accepted risk** (virhe `ValueError` heti ensimmäisellä engine-käytöllä; ei muutu tässä ticketissä).
  4. medium, up→down→up-testi puuttui — **fixed** (kaksi uutta migraatiotestiä).
  5. low, rollback-polun vuototesti ja sisäisen commitin suojaus — **fixed** (testit, pool_size=1 ja pid-vertailu).
  6. low, tyhjä GUC-merkkijono vs. politiikkojen `::uuid` — **fixed** (dokumentoitu `DATABASE.md`:ssä, testi).
  7. low, `schema_migrations`-oikeudet — **fixed** (REVOKE).
  8. low, roolin luonnin kilpa-ajo — **fixed** (`EXCEPTION WHEN duplicate_object`); ADMIN-oikeus dokumentoitu.
  9. low, `overview.md` puuttui — **fixed**.
  Korjausten jälkeen ei toista katselmointikierrosta; korjaukset varmistettu testeillä (ks. yllä). Ihmiselle: tämä on yhden kierroksen review, ei kolmen.

## Documentation effects

- [x] Update architecture or ADR — `docs/architecture/data/DATABASE.md`, `docs/architecture/overview.md`, `db/migrations/README.md`
- [x] Update `.env.example` — `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`; `docs/architecture/deployment.md`, `docker-compose.yml`, `docker-compose.production.yml`

## Blocked by

- ADR-016 (hyväksytty 2026-11-06)

## Completion record

- Migraatio 021, `RequestContext`/`transaction_session`, testit ja dokumentaatio valmiit; kriteerit täyttyvät. Nykyiset reitit ja `get_db_session` koskematta. Commit: `feat: platform-foundation ticket 01` (git log).

## Comments

- Lähde: Yearclock `6848e72`; kirjaa ticketin lopussa käytetyt lähdetiedostot ja commit.
