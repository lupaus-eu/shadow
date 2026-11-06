# Ticket 03: Background jobs and worker (078C)

Status: implemented

## Goal

Erillinen `worker`-prosessi ajaa durable-jonon jobit ja outbox-viestit idempotentisti.

## Implementation

- Migraatio 023 (`background_jobs`, `outbox_messages`).
- `app/platform/work_queue.py`, `jobs.py` (job-tyyppi- ja scheduler-rekisteri), `worker.py` (`python -m app.platform.worker`). `notifications.cleanup` siirtyy tickettiin 04 (ilmoitustaulu syntyy siinä); tässä testit käyttävät omia käsittelijöitään.
- Compose-palvelu `worker` dev- ja production-composeen (ei tuotantokäyttöönottoa); `prediction-worker` ennallaan.
- Päivitetään `verify-production-*`-skriptit ja CI.

## Acceptance criteria

- [x] Job: onnistuu, epäonnistuu, uudelleenyritys viiveellä, idempotenssiavain estää tuplan.
- [x] Kaksi workeria ei käsittele samaa riviä (`SKIP LOCKED`).
- [x] `make dev-up` käynnistää workerin terveenä; production-compose-tarkistukset läpi.

## Testing

- [x] Backend — jobin elinkaari, rekisteri
- [x] Migraatio/integraatio — jonon poiminta rinnakkain
- [x] Compose/runtime — dev-stack ja `.github/scripts/verify-production-*.sh`
- [x] Frontend/E2E — ei sovellu

## Ajetut tarkistukset

- [x] `ruff check .` — passed.
- [x] `pyright` — yksi virhe `ai_change_sets/service.py:381`, sama ilman muutoksiani.
- [x] `pytest` koko sarja PostgreSQL 18:aa vasten — 1456 passed, 7 skipped.
- [x] Dev-stack, oikeat kontit eristetyllä Compose-projektilla (`-p shadowverify`, oma verkko ja volyymit, poistettu ajon jälkeen): `database` + migraatiot 001–023 + `worker` → worker `healthy` (`docker inspect`), lisätty `probe`-job kirjautui lokiin ja jäi uudelleenyritykseen ("no handler"). Koko `make dev-up` -polkua (Entra-asetukset, backend, Caddy) ei ajettu.
- [x] `docker compose config` dev ja production; `.github/scripts/verify-production-compose.sh` ajettiin bash 3 -yhteensopivalla kopiolla (alkuperäinen vaatii bash 4:n, jota koneella ei ole) — läpi, mukaan lukien uudet `worker`-profiilin tarkistukset.
- Ei ajettu: `verify-production-runtime.sh` ja `verify-release-compose-failure.sh` (vaativat Linux-isännän/bash 4:n); `worker` on profiilin takana, joten niiden palveluluettelot eivät muutu. CI ajaa ne.

## AI review

- [x] Tuore subagentti (opus), taso medium–high, 1 kierros. Löydökset:
  1. **high**, dev-`worker` ei yltänyt tietokantaan (puuttuva `local`-verkko) — **fixed**; todennettu oikeassa kontissa (ks. yllä).
  2. medium, ei fencingiä: pitkään ajava job otettiin uudelleen — **fixed** (rivilukko `FOR UPDATE` handlerin ajan, claimin omistajuus tarkistetaan `attempts`-arvolla; testit).
  3. medium, idempotenssiavain globaali / tenant-sokea — **fixed** (`UNIQUE NULLS NOT DISTINCT (tenant_id, idempotency_key)`, haku tenantilla; testit).
  4. medium, virheitä ei lokitettu, tietokantavirhe tappoi workerin — **fixed** (varoitus ilman viestiä/payloadia; silmukka toipuu, `--once` heittää; testit).
  5. medium, `WORKER_*`/`QUEUE_*` eivät välittyneet composeen — **fixed** (molemmat compose-tiedostot + verify-skripti).
  6. low, kellojen sekoitus — **fixed** (claim ja retry palvelimen kellolla; injektoitu `now` vain testeille).
  7. low, laajuus: `notifications.cleanup` ja `app.worker` — **kirjattu** (siirtyy tickettiin 04; entry point `app.platform.worker`).
  8. low, health-check ei todista silmukan elossaoloa — **accepted risk**, dokumentoitu (sykelippu myöhemmin).
  9. low, verify-skriptin worker-tarkistukset ja echon paikka — **fixed**.
  10. low, claim-indeksi ja valmiiden rivien siivous — indeksi **fixed** (osittainen indeksi); valmiiden rivien siivous **accepted risk**, dokumentoitu `DATABASE.md`:ssä.
  11. low, SIGKILL grace-ajan jälkeen ja virheelliset kokonaisluvut — **fixed** (selkeä ValueError) / dokumentoitu at-least-once.
  Ei toista kierrosta; korjaukset varmistettu testeillä ja oikealla konttiajolla. Yksi kierros kolmesta.

## Documentation effects

- [x] Update `docs/operations/` — `docs/operations/local-development.md`
- [x] Update architecture or ADR — `docs/architecture/deployment.md`, `overview.md`, `data/DATABASE.md`, `project-layout.md`, `diagrams/db-physical-schema.puml` + SVG, `docs/adr/0019-…` (worker/outbox-osa), `db/migrations/README.md`
- [x] Update `.env.example` ja production-kontrahti (`deployment.md`), `docker-compose.yml`, `docker-compose.production.yml`, `Makefile`

## Blocked by

- 01

## Completion record

- Migraatio 023, jonot, job-rekisteri, worker ja compose-palvelut valmiit. Poikkeamat: `app/platform/worker.py`, `notifications.cleanup` → 04, production-`worker` profiilin `worker` takana (ei käynnisty deploy-komennoilla), jonon stale-claim-palautus ja tenant-kohtainen idempotenssi lisätty Yearclockiin verrattuna. Korjasin myös ticketin 01 aiheuttaman `verify-production-compose.sh`-assertion (prediction-workerin ympäristö sisältää nyt poolimuuttujat). Commit: `feat: platform-foundation ticket 03`.

## Comments

- Lähde: Yearclock `6848e72`; kirjaa ticketin lopussa käytetyt lähdetiedostot ja commit.
