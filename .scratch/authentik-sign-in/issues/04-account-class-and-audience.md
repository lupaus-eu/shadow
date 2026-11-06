# Ticket 04: Account class and login audience (079C, reduced)

Status: implemented

## Goal

Accounts carry a class and a locale and the session dependencies can separate customer and platform accounts, without changing what current Users can do.

## Implementation

- Migration 026: `users.account_class` (`customer` default, `platform`) and `users.locale` (`en` default, `fi`).
- `auth/dependencies.py`: `require_customer_session` for the business routes, `require_platform_session` (403 for customers; no platform account can sign in yet).
- `/auth/login` accepts `audience=customer|platform`, carried in the login transaction; `platform` is refused until step 7.
- Unchanged: no account is created at login (moved to step 080B, see the design); `users.role` stays.
- `CONTEXT.md`: account class and platform account move from *Under specification* where ADR-016 has fixed them; `docs/architecture/domains/USERS.md` and `data/DATA-MODEL.md`.

## Acceptance criteria

- [x] Existing Users are `customer` with `en`; nothing about their access changes (all existing authorization tests pass unchanged).
- [x] A `platform` account cannot use the business routes, and a customer cannot use `require_platform_session` routes (403).
- [x] `audience=platform` is rejected at login for now; an unknown audience is a `422`.
- [x] Migration 026 up and down with data present.

## Testing

- [x] Backend/API — dependencies per class, login audience validation, locale default
- [x] Migration/integration — 026 up/down with rows
- [x] Frontend/Browser — not applicable

## Ajetut tarkistukset

- [x] `ruff check .`, `pyright` (yksi ennestään oleva virhe `ai_change_sets/service.py:381`), `pytest` koko sarja PostgreSQL 18:aa vasten — 1715 passed, 7 skipped.
- [x] Kaikki `/api/v1`-business-reitit (molemmissa konfiguraatioissa) platform-tilillä → 403; platform-tili ei pääse sisään eikä saa identiteettiä linkitetyksi; olemassa oleva platform-identiteetti ei päivitä `last_login_time`ia; MCP-grantit ja Users API eivät huomioi platform-tilejä; migraatio 026 ylös/alas, oletukset, CHECK:t ja aiemmin olleet rivit.
- Ei ajettu: oikea selain; platform-konsoli (vaihe 7).

## AI review

- [x] Tuore subagentti (opus), taso high, 1 kierros. Ei korkean vakavuuden löydöksiä; 2 keskitasoa, 1 matala–keskitaso, 4 matalaa:
  1. medium, MCP-tokenit eivät huomioineet `account_class`ia — **fixed** (`_active_user` rajaa customer-tileihin; koodin lunastus, refresh ja access-token; testit).
  2. medium, Users API hallitsi platform-tilejä (lista, luku, muutos, poisto; sähköpostin vaihto → identiteetin linkitys) — **fixed** (kaikki rajattu customer-tileihin, platform-id → 404; testi).
  3. low–medium, hylätty platform-kirjautuminen kirjasi identiteettilinkin / `last_login_time`n — **fixed** (`resolve_identity` rajaa luokkaan ennen linkitystä ja kirjausta; testit myös valmiiksi linkitetylle tilille ja koodin toistolle).
  4. low, audience ei kulje login-transaktiossa — **kirjattu** (vain validoidaan ja `platform` evätään; tallennus vaiheessa 7 kun `platform` otetaan käyttöön).
  5. low, testiaukot (aiemmin olleet rivit migraatiossa, transaktion kulutus) — **fixed**.
  6. low, `require_admin` käyttämätön ja kosketti sessiota ennen luokkatarkistusta — **fixed** (poistettu); `require_platform_session` tarvitsee vaiheessa 7 CSRF-version — kirjattu designiin.
  7. low, dokumentit (`DATA-MODEL.md`, väite "kaikki reitit") — **fixed**.
  Ei toista kierrosta; korjaukset varmistettu testeillä. Yksi kierros kolmesta.

## Documentation effects

- [x] Update `CONTEXT.md` — termi *Account class*, *Platform account* viittaa siihen
- [x] Update architecture or ADR — `docs/architecture/domains/USERS.md`, `docs/architecture/data/DATA-MODEL.md`, `docs/architecture/data/DATABASE.md`, `db-physical-schema.puml` + SVG, `db/migrations/README.md`

## Blocked by

- 03

## Completion record

- Migraatio 026, tililuokka ja locale, luokkatarkistukset kaikissa sovelluksen riippuvuuksissa, MCP-grantit ja Users API rajattu customer-tileihin, `audience`-parametri. Poikkeamat: audience ei tallennu login-transaktioon (vain validointi; `platform` evätään), `require_admin` poistettu (käyttämätön), Users API ei näe platform-tilejä. Commit: `feat: authentik-sign-in 04`.

## Comments

- Lähde: Yearclock `6848e72` (`authentik/`, `docker-compose.yml`, `docs/runbooks/authentik-*.md`, `backend/app/oidc.py`); kirjaa käytetyt lähdetiedostot lopussa.
