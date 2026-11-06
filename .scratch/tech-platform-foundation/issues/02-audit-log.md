# Ticket 02: Audit log (078B)

Status: implemented

## Goal

Audit-tapahtuma voidaan kirjoittaa append-only-tauluun kutsujan transaktiossa, MCP-provenance mukaan lukien.

## Implementation

- Migraatio 022 (`audit_events`, append-only-trigger, grantit).
- `core/audit.py`: `AuditEventDraft`, `record_audit_event`, `audit_source`.
- Ei audit-kutsuja nykyisiin mutaatioihin. ADR-019:n luonnos (audit).

## Acceptance criteria

- [x] Tapahtuma tallentuu kontekstin GUC:eista johdetuin toimijoin.
- [x] UPDATE ja DELETE epäonnistuvat triggeriin.
- [x] `audit_source()` yhdistyy `change_summary`:iin.

## Testing

- [x] Backend — draft → rivi, provenance
- [x] Migraatio/integraatio — append-only, `shadow_app`-oikeudet
- [x] Frontend/E2E — ei sovellu

## Ajetut tarkistukset

- [x] `ruff check .` — passed.
- [x] `pyright` — yksi virhe `ai_change_sets/service.py:381`, sama ilman muutoksiani (väliaikaisen venvin SQLAlchemy-versio). Korjasin samalla ticketin 01 testien pyright-virheet.
- [x] `pytest` koko sarja PostgreSQL 18:aa vasten (`MIGRATION_TEST_DATABASE_URL`) — 1433 passed, 7 skipped.
- [x] Kaavion renderöinti: `docker build` ja `docker run … -tsvg db-physical-schema.puml` (compose-profiili `docs` vaatii paikalliset Entra-asetukset, joten renderöijä ajettiin suoraan samalla Dockerfilellä).
- Ympäristörajoitus: ei `uv`, väliaikainen venv.

## AI review

- [x] Tuore subagentti (opus), taso `high`, 1 kierros. Ei korkean vakavuuden löydöksiä; 3 medium, 6 low:
  1. medium, tapahtuma ilman pyyntökontekstia tallentui hiljaa ilman toimijaa — **fixed** (`app.request_context`-merkki; `record_audit_event` heittää RuntimeErrorin; testi).
  2. medium, provenance ja payload samassa avaruudessa — **fixed** (provenance varatussa avaimessa `source`; draft ei saa käyttää sitä; testit). Poikkeaa Yearclockin litteästä yhdistämisestä.
  3. medium, ContextVar-säie/reset-riskit ja muokattava dict — **fixed** (muuttumaton kopio, `current_source()` palauttaa kopion, JSON-validointi kutsukohdassa; dokumentoitu rajoitus raakasäikeistä). MCP-polun läpi menevä testi kuuluu ticketille 080J.
  4. low, request_id ei-tyhjä, target_id-pituus — **fixed** (checkit + testit).
  5. low, eksplisiittinen GRANT SELECT, INSERT — **fixed** (+ TRUNCATE-testi sovellusroolille).
  6. low, append-only vain triggerillä, ei roolilla (`RESET ROLE`) — **accepted risk**; ADR-019:n sanamuoto tarkennettu.
  7. low, vanhentunut kommentti mallissa — **fixed**.
  8. low, ei-JSON-arvot myöhään — **fixed** (sama kuin 3).
  9. low, poikkeamat ticketistä (`app/platform/`, `DATABASE.md`) — kirjattu alle.
  Ei toista kierrosta; korjaukset varmistettu testeillä. Yksi kierros kolmesta.

## Documentation effects

- [x] Update architecture or ADR — `docs/architecture/data/DATABASE.md` (ei `DATA-MODEL.md`; fyysinen taulu), `docs/architecture/diagrams/db-physical-schema.puml` + SVG, `docs/architecture/project-layout.md`, uusi `docs/adr/0019-platform-services-worker-audit-email.md` (audit-osa, `proposed`), `db/migrations/README.md`

## Blocked by

- 01

## Completion record

- Migraatio 022, `app/platform/{models,audit}.py`, testit ja dokumentaatio valmiit. Poikkeamat: koodi `app/platform/` (ei `core/`), `target_id` TEXT, provenance avaimessa `source`, `app.request_context`-merkki lisätty ticketin 01 `apply_request_context`iin. Commit: `feat: platform-foundation ticket 02`.

## Comments

- Lähde: Yearclock `6848e72`; kirjaa ticketin lopussa käytetyt lähdetiedostot ja commit.
