# Technical design: Platform foundation (backend)

Status: accepted

Vaihe 1 kokonaissuunnitelmasta `.scratch/saas-platform/PLAN.md` (tehtävät 078A–D).
Tekninen työ: ei käyttäjälle näkyvää toimintaa, siksi ei PRD:tä (`FEATURE_WORKFLOW.md`).
Grillattu 2026-11-06; päätökset Q1–Q10 alla kohdassa *Options and decision*.

## Goal and scope

Tuodaan Yearclockista (`../yearclock`, lähde-commit `6848e72`) Shadowin backendiin
alustan runko, jonka päälle tenanttius, laskutus, legal ja kutsut rakentuvat:
pyyntökonteksti ja sovellusrooli, audit log, taustatyöt (worker + outbox) sekä
sähköposti ja ilmoitusten perusmekanismi.

**Ei kuulu tähän:** `tenants`-taulu ja tenant-FK:t (080A), RLS-politiikat (080G),
nykyisten reittien siirto tenanttikontekstiin (080C–E), audit-kutsut nykyisiin
mutaatioihin, ilmoitustyypit ja preferenssit, frontend, Authentik, tuotannon
käyttöönotto (vaihe 9–10).

**Esiehto:** ADR-016 (tenant-käsite, roolit, tililuokat, RLS) on hyväksytty
2026-11-06 (`docs/adr/0016-…`). Tämä design olettaa:
tenantti = `tenant`, GUC `app.current_tenant_id`, sovellusrooli `shadow_app`.

## Current and target state

- **Current:** `backend/app/core/database.py` tarjoaa synkronisen `get_db_session`:n
  (15 reitin dependency), joka ajaa omistajakäyttäjällä ilman roolia tai kontekstia.
  Ei auditia, ei yleistä jonoa eikä sähköpostia. Ainoa taustaprosessi on
  `prediction-worker` (`python -m app.api.v1.predictions.worker`, advisory lock).
  Migraatiot on numeroitu 001–020; `httpx2` on jo riippuvuus.
- **Target:** uusi koodi ajaa `SET LOCAL ROLE shadow_app` + GUC:t
  `transaction_session`:in kautta; uusi `worker`-prosessi käsittelee
  `background_jobs`- ja `outbox_messages`-rivit; audit-tapahtumat ja ilmoitukset
  tallentuvat omiin tauluihinsa; nykyiset reitit ja `prediction-worker` toimivat ennallaan.

## Domain

Alustatason kyvykkyyksiä, eivät uusi bisnesdomain. Omistava dokumentti syntyy
ADR-016:n yhteydessä (`docs/domains/TENANTS.md`); tässä vaiheessa kuvaukset
lisätään `docs/architecture/overview.md`:iin ja uuteen `docs/architecture/domains/PLATFORM.md`:aan.

## Database

Kolme migraatioparia (`NNN_*.sql` + `.down.sql`, ADR-002); numero varataan
ticketin alussa (nyt vapaana 021–024).

Yleiset linjat (Q3, Q6):
- Uudet alustataulut käyttävät UUID-avaimia (`id UUID PRIMARY KEY`); viittaukset
  `users`-tauluun ovat `BIGINT … REFERENCES users(user_id)`. Aikasarakkeet `*_time`.
- `tenant_id UUID NULL` ilman vierasavainta ja ilman RLS:ää; 080A lisää FK:n ja
  NOT NULL -ehdon, 080G politiikat.

| Migraatio | Sisältö |
|---|---|
| 021 `create_application_role` | `shadow_app` (NOLOGIN NOBYPASSRLS) + `GRANT shadow_app TO <omistajarooli>` + oletusgrantit; ei politiikkoja. |
| 022 `create_audit_events` | `audit_events` (actor `user_id`, `tenant_id`, `support_access_id` ilman FK:ta toistaiseksi, `action`, `target_type`, `target_id`, `request_id`, `change_summary jsonb`, `created_time`), append-only-trigger (UPDATE/DELETE estetty), grantit `shadow_app`:lle (INSERT, SELECT). |
| 023 `create_background_queue` | `background_jobs`, `outbox_messages` (status, attempts, `available_time`, `idempotency_key` UNIQUE, `tenant_id`, payload jsonb), indeksit jonon poimintaan (`FOR UPDATE SKIP LOCKED`). |
| 024 `create_notifications` | `notifications` (`tenant_id`, `user_id`, `type`, `params jsonb`, `read_time`, `created_time`). Ei preferenssitaulua (Q9). |

Tarkka sarakeluettelo kirjataan ticketeissä Yearclockin `models.py`:stä sovitettuna.
Päivitettävät: `docs/architecture/data/DATA-MODEL.md`, `DATABASE.md`, DB-kaavio.

## Backend (API ja koodi)

Kopio Yearclockista, nimet säilytetään (`organization` → `tenant`, `user_account_id` → `user_id`):

- `app/core/database.py`: lisätään `RequestContext`, `apply_request_context`,
  `transaction_session` (`elevated` tulee tickettiin 04, ks. Yearclock `notifications.py`); `get_db_session` säilyy ennallaan (Q7).
- `app/core/audit.py` (`AuditEventDraft`, `record_audit_event`, `audit_source`).
  Ei kutsuja nykyisissä mutaatioissa (Q8).
- `app/core/work_queue.py`, `app/worker.py`, `app/jobs.py`: job-tyyppirekisteri,
  jossa `notifications.cleanup` ja testikäsittelijä (Q10). Uudelleenyritys,
  viive ja idempotenssi kuten Yearclockissa.
- `app/core/email_delivery.py` (Scaleway TEM, `httpx2`), outbox-toimittaja
  workerissa. Kehityksessä SMTP→Mailpit tai lokiin; tuotannossa TEM.
- `app/core/notifications.py` (vain `notify_many`, siivous), `notification_routes.py`:
  `GET /api/v1/notifications`, merkintä luetuksi. Parametrit tallennetaan; tekstin
  kielistys myöhemmin. Reitit vaativat nykyisen session; tenantittomat toistaiseksi
  (käyttäjäkohtaiset), tenant-suodatus 080B:ssä.

Virheet: sama muoto kuin nykyisissä routeissa (RFC 7807-tyyliset, jos käytössä; tarkistetaan ticketissä).

## Frontend

Ei muutoksia.

## Authentication and authorization

Vaiheessa 1 vain nykyinen sessio ja CSRF. Ilmoitus-API palauttaa vain kirjautuneen
käyttäjän omat rivit. `shadow_app`-rooli ei vielä rajoita mitään (ei politiikkoja).

## Testing

- Backend: yksikkö- ja API-testit jokaiselle moduulille; `transaction_session`
  asettaa GUC:t, ei vuoda transaktioiden yli.
- PostgreSQL-integraatio: migraatio ylös/alas, append-only-trigger estää
  UPDATE/DELETE, `shadow_app`-grantit, `SKIP LOCKED`-poiminta kahdella
  kilpailevalla workerilla, idempotenssiavain.
- Worker: job-elinkaari (onnistuu, epäonnistuu, uudelleenyritys, viive),
  outbox-toimitus TEM-fakea vasten.
- Compose: dev-stack käynnistyy `worker`- ja Mailpit-palvelujen kanssa
  (`make dev-up`); `verify-production-*`-skriptit läpi uudella `worker`-palvelulla.
- Frontend/E2E: ei sovellu.

## Configuration

Uudet muuttujat `.env.example`:iin ja `docs/architecture/deployment.md`:n
tuotantokontrahtiin: `SCW_SECRET_KEY`, `SCW_DEFAULT_PROJECT_ID`,
`SCW_TEM_DEFAULT_SENDER_EMAIL`, `SCW_TEM_DEFAULT_SENDER_NAME`, `SCW_TEM_REGION`,
`EMAIL_BACKEND` (`log|smtp|scaleway`), `SMTP_HOST/PORT` (dev), `NOTIFICATION_RETENTION_DAYS`,
`DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`. Nimet tarkennetaan ticketeissä.

## Architecture effects

- Uusi compose-palvelu `worker` dev-composeen ja `docker-compose.production.yml`:ään
  (ADR-013:n hardening-taso). Tuotannossa sitä ei oteta käyttöön erikseen ennen
  vaihetta 9/10 (Q5). Dev-composeen lisätään Mailpit (Q4).
- `prediction-worker` säilyy erillisenä.
- Päivitettävät kaaviot (PlantUML): komponentti-/deployment-kaavio worker + mailpit; uusi sekvenssi outbox → sähköposti.

## Documentation effects

- [x] `docs/architecture/` — overview, deployment, data (`DATA-MODEL.md`, `DATABASE.md`), uusi `domains/PLATFORM.md`, kaaviot + SVG:t (tickets 01–04)
- [x] `docs/operations/` — `local-development.md` (worker, Mailpit), `testing.md`
- [x] `docs/adr/` — ADR-016 ennen toteutusta (esiehto); ADR-019 (worker, outbox, TEM, ilmoitukset, audit) kirjoitetaan ticketin 02 yhteydessä
- [x] `.env.example` ja production-konfiguraatiokontrahti
- [ ] `docs/user/`, `docs/admin/`, `docs/gdpr/`, `docs/legal/`, `docs/design/`, `CONTEXT.md` — ei vaikutusta tässä vaiheessa (CONTEXT.md päivittyy ADR-016:n yhteydessä)

## Options and decision

| # | Päätös | Valittu |
|---|---|---|
| Q1 | Dokumentin laji | Tekninen suunnitelma + ticketit, ei PRD:tä |
| Q2 | ADR-016 ennen vaihetta 1 | Kirjoitetaan ja hyväksytään ensin; ADR 017–022 vaiheittain |
| Q3 | `tenant_id` ennen `tenants`-taulua | Nullable UUID ilman FK:ta; 080A viimeistelee |
| Q4 | Sähköposti kehityksessä | Mailpit dev-composeen |
| Q5 | `worker` tuotanto-composessa | Lisätään, ei käyttöönottoa ennen vaihetta 9/10 |
| Q6 | Tunnisteet | UUID uusille alustatauluille, BIGINT `user_id`-viittaukset, Shadowin sarakenimet |
| Q7 | `shadow_app` | Vain uusi koodi; nykyiset reitit `get_db_session`:ssa 080C–E asti |
| Q8 | Audit-kutsut | Ei nykyisiin mutaatioihin; lisätään vaiheissa 3 ja 6 |
| Q9 | Ilmoitukset | Vain yleinen mekanismi; tyypit ja preferenssit myöhemmin |
| Q10 | Job-tyypit | Rekisteri; `notifications.cleanup` + testikäsittelijä |

## Tickets

01 request-context-and-app-role (078A) → 02 audit-log (078B) → 03 background-jobs (078C) → 04 email-and-notifications (078D).

## Implementation notes (all four tickets implemented 2026-11-06)

Differences from the design above, recorded when the tickets closed:

- **Location:** the code is in `backend/app/platform/` (not `app/core/`), apart from `RequestContext` and `transaction_session`, which are in `app/core/database.py`. The worker entry point is `python -m app.platform.worker`.
- **Audit:** `target_id` is text (Shadow keys are bigint); provenance is stored under the reserved `change_summary.source` key; writing an event without a `transaction_session` context raises. `apply_request_context` sets the marker `app.request_context`.
- **Queue:** idempotency keys are unique per tenant (`UNIQUE NULLS NOT DISTINCT (tenant_id, idempotency_key)`); stale claims are recovered after `QUEUE_CLAIM_TIMEOUT_SECONDS` while a running job's row lock prevents takeover; retries use the database clock.
- **Worker in production:** defined behind the Compose profile `worker` (not started by any deploy command); `EMAIL_BACKEND=scaleway` there. Dev Compose runs it with Mailpit.
- **Email:** the Scaleway client uses the standard library (`urllib`), so no HTTP dependency was added; permanent failures (4xx except 408/429, bad headers) fail at once; delivery is at-least-once.
- **Notifications:** generic mechanism only, as decided (Q9); `elevated` is the `app.notification_write` setting. The cleanup job and its scheduler (`notifications.cleanup`) arrived with ticket 04, not 03, and also delete finished outbox rows after `OUTBOX_RETENTION_DAYS` (default 7).
- **Not done (follow-ups):** tenant foreign keys and RLS on the new tables (080A/080G), notification types and preferences, frontend inbox, audit calls in existing mutations, a worker heartbeat for the health check, cleanup of finished `background_jobs` rows, and the GDPR inventory when production adopts the worker.
