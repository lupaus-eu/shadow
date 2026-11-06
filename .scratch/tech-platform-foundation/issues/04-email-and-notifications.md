# Ticket 04: Email delivery and notifications (078D)

Status: implemented

## Goal

Outbox-viesti voidaan toimittaa sähköpostina ja käyttäjä voi lukea omat ilmoituksensa.

## Implementation

- Migraatio 024 (`notifications`).
- `app/platform/email_delivery.py` (TEM `urllib`-asiakkaalla — ei uutta riippuvuutta, koska `httpx2` on vain dev-riippuvuus —, backend `log|smtp|scaleway`), outbox-toimitus workerissa.
- `app/platform/notifications.py` (`notify_many`, `elevated`, siivousjob `notifications.cleanup` ja scheduler — siirtyi tänne tickettiä 03:sta), reitit `GET /api/v1/notifications` ja merkintä luetuksi.
- Mailpit dev-composeen. Ei tyyppejä eikä preferenssejä.

## Acceptance criteria

- [x] TEM-asiakas lähettää idempotenssiavaimella ja käsittelee virheet (retry workerissa).
- [x] Kehityksessä viesti näkyy Mailpitissä.
- [x] Käyttäjä näkee vain omat ilmoituksensa; siivous poistaa vanhat.

## Testing

- [x] Backend/API — lähetys (fake TEM), luku, merkintä, siivous, auktorisointi
- [x] Migraatio/integraatio — `notifications`
- [x] Compose — Mailpit käynnistyy
- [x] Frontend/E2E — ei sovellu

## Ajetut tarkistukset

- [x] `ruff check .` — passed.
- [x] `pyright` — yksi virhe `ai_change_sets/service.py:381`, sama ilman muutoksiani.
- [x] `pytest` koko sarja PostgreSQL 18:aa vasten — 1515 passed, 7 skipped.
- [x] Päästä päähän oikeilla konteilla (eristetty Compose-projekti `shadowverify`, poistettu ajon jälkeen): `database` + migraatiot 001–024 + `mailpit` + `worker`; `notify_many` loi ilmoituksen ja outbox-viestin, worker lähetti sen SMTP:llä, Mailpitin API näytti viestin oikealle vastaanottajalle (`shadow@app.localhost` lähettäjänä), outbox-rivi `completed` ja `provider_message_id` asetettu.
- [x] `docker compose config` (dev) ja `.github/scripts/verify-production-compose.sh` bash 3 -kopiolla (alkuperäinen vaatii bash 4) — läpi, `worker`-profiilin ympäristö mukaan lukien `EMAIL_BACKEND=scaleway` ja `OUTBOX_RETENTION_DAYS`.
- [x] Kaavio: `docker run … -tsvg db-physical-schema.puml` (renderöijäkuva `docs/architecture/diagrams/Dockerfile`).
- Ei ajettu: koko `make dev-up` (Entra-asetukset, backend, Caddy) eikä oikea Scaleway-kutsu (ei tunnuksia); Scaleway-asiakasta testattiin paikallista HTTP-palvelinta vasten.

## AI review

- [x] Tuore subagentti (opus), taso medium–high, 1 kierros. Ei korkean vakavuuden löydöksiä; 2 medium, 9 low + testiaukot:
  1. medium, kaksoisdraftit samalle vastaanottajalle ja avaimelle kaatoivat transaktion (ON CONFLICT kahdesti) ja `elevated` peitti virheen — **fixed** (draftit tiivistetään, `elevated` ei palauta lippua virheen jälkeen; testi).
  2. medium, outbox-rivien henkilötiedot (osoite, teksti) säilyivät ikuisesti — **fixed** (`OUTBOX_RETENTION_DAYS`, oletus 7, siivous poistaa valmiit rivit; testi; `docs/gdpr/README.md`).
  3. low, at-least-once-kaksoislähetys — **documented** (ADR-019).
  4. low, pysyvät virheet yritettiin uudelleen — **fixed** (4xx paitsi 408/429, otsakevirheet ja virheellinen payload epäonnistuvat heti; testit).
  5. low, `last_error` otti minkä tahansa poikkeuksen viestin — **fixed** (vain `EmailDeliveryError`-viesti, muuten tyypin nimi; testi).
  6. low, päivärajan kysely ja kilpa-ajo — **fixed** osin (haku rajattu vastaanottajiin); kilpa-ajo **accepted risk** (raja on pehmeä, dokumentoitu).
  7. low, dedupe ei päivittänyt tyyppiä, tuplasähköposti, palautusarvo — **fixed** (tyyppi päivittyy, korvaus ei lähetä uutta sähköpostia paitsi pakollinen, renderöijätarkistus ennen kirjoitusta, palautusarvo = kirjoitetut rivit); osoitteen jäädyttäminen enqueue-hetkellä **accepted risk**.
  8. low, `read_time < created_time` -tarkistus saattoi antaa 500 — **fixed** (`GREATEST(now(), created_time)`; testi).
  9. low, kursori hauras URL-koodauksessa — **fixed** (opaque base64url; testi, myös yhtäsuuret aikaleimat).
  10. low, Scaleway-asiakas seurasi uudelleenohjauksia tokenin kanssa; `repr` paljasti avaimen — **fixed** (ei uudelleenohjauksia, `repr=False`; testit).
  11. low, SMTP useita vastaanottajia — **fixed** (yksi osoite, muuten pysyvä virhe; testit).
  Testiaukot (kaksoisavain, yhtäsuuret aikaleimat, otsake-CRLF, 4xx/5xx) — **fixed**. Subagentin raportoima ainoa epävakaa havainto (`test_every_route_requires_a_session`, virhe rinnakkaisen täyden ajon aikana) ei toistunut kolmessa uusinta-ajossa.
  Ei toista kierrosta; korjaukset varmistettu testeillä ja oikealla konttiajolla. Yksi kierros kolmesta.

## Documentation effects

- [x] Update `docs/operations/` — `docs/operations/local-development.md` (Mailpit, worker)
- [x] Update `docs/gdpr/` — `docs/gdpr/README.md` (Scaleway TEM suunniteltu alikäsittelijä, säilytysajat)
- [x] Update architecture — `docs/architecture/data/DATABASE.md`, `docs/architecture/diagrams/db-physical-schema.puml` + SVG, `docs/architecture/overview.md`, `docs/architecture/deployment.md`, uusi `docs/architecture/domains/PLATFORM.md` + `DOMAIN.md`, `docs/adr/0019-…` (sähköposti- ja ilmoitusosa), `db/migrations/README.md`. Erillistä sekvenssikaaviota ei tehty (ei uutta ulkoista rajapintaa käyttäjän suuntaan; ketju kuvattu ADR:ssä ja PLATFORM.md:ssä).
- [x] Update `.env.example` ja `docker-compose.yml`, `docker-compose.production.yml`, `Makefile`

## Blocked by

- 02
- 03

## Completion record

- Migraatio 024, sähköpostilähettäjät, `notify_many`, outbox-toimitus workerissa, ilmoitus-API ja Mailpit valmiit. Poikkeamat: `urllib` `httpx2`:n sijaan (ei uutta riippuvuutta), siivousjob ja scheduler tässä ticketissä (ei 03), outbox-säilytys ja pysyvien virheiden käsittely lisätty Yearclockiin verrattuna, ei erillistä sekvenssikaaviota. Commit: `feat: platform-foundation ticket 04`.

## Comments

- Lähde: Yearclock `6848e72`; kirjaa ticketin lopussa käytetyt lähdetiedostot ja commit.
