# Ticket 03: OIDC against Authentik (079B)

Status: implemented

## Goal

The backend authenticates against Authentik instead of Entra, logs out of both sessions, and requires a verified email.

## Implementation

- `core/config.py`: replace the Entra rules with the Authentik rules (design); `OIDC_INTERNAL_BASE_URL`; `OIDC_REQUIRE_VERIFIED_EMAIL=true` default.
- `api/v1/auth/provider.py`: internal discovery/token calls with public `Host`/`X-Forwarded-Proto`, issuer check, `end-session/` URL with `id_token_hint` and exact `post_logout_redirect_uri`; returns the ID token to the session.
- Migration 025 `auth_sessions.id_token`; `create_session` stores it, session deletion removes it; the log redaction drops `session_state`.
- Compose and `.env.example` give the local backend its `OIDC_*` values for the local Authentik (the Entra-specific `${…:?Run scripts/setup-local-entra.sh}` guards are replaced).
- Not done: account class (04), removal of the Entra scripts and documents (05).

## Acceptance criteria

- [x] Logging in at `https://app.localhost` as a dev user through Authentik works end to end (scripted browser path against the real backend, Caddy and Authentik) and lands in the linked seeded account. **`make dev-up` from a fresh clone still starts the Entra setup (`LOCAL_INIT`) until ticket 05 removes it; the Authentik path was verified with the Compose project started directly.**
- [x] An unverified email, a mismatching issuer, an unexpected origin or a failing discovery fails closed; the generic sign-in failure is unchanged.
- [x] Logout ends the Shadow session and the Authentik session and returns to the application.
- [x] `OIDC_*` validation accepts the Authentik issuer and rejects `http`, userinfo, query, fragment, a different discovery origin and non-`/application/o/<slug>/` paths.
- [x] Migration 025 up and down; the ID token is deleted with its session.

## Testing

- [x] Backend/API — config validation, provider (internal base URL rewrite, issuer mismatch, logout URL), service (verified-email linking, unverified refused, ID token stored/deleted)
- [x] Migration/integration — 025 up/down on PostgreSQL
- [x] Browser/E2E — headless run of the browser path at `https://app.localhost` (`scripts/verify-local-sign-in.py`); no real browser
- [x] Frontend — not applicable

## Ajetut tarkistukset

- [x] `ruff check .`, `pyright` (yksi ennestään oleva virhe `ai_change_sets/service.py:381`), `pytest` koko sarja PostgreSQL 18:aa vasten — 1543 passed, 7 skipped.
- [x] Oikea stack (eristetty Compose-projekti `shadowverify`: tietokanta, Authentik, backend-kontti, Caddy): `python3 scripts/verify-local-sign-in.py` — kirjautuminen salasana + TOTP, koodi callbackiin, sessio linkittyy seedattuun admin-tiliin, uloskirjautuminen päättää Shadow- ja Authentik-sessiot ja palauttaa `/login`, vahvistamaton osoite ja tuntematon vahvistettu henkilö evätään ilman sessiota. `scripts/verify-authentik-local.py` (+ `--enrollment`) uudelleen policy- ja flow-muutosten jälkeen.
- [x] Migraatio 025 ylös/alas ja CHECK PostgreSQL:ssä (`test_migrations_integration.py`); `docker compose config`; tuotanto-compose-verifiointi bash 3 -kopiolla.
- Ei ajettu: oikea selain (ei selainta/virtuaalista authenticatoria automaatioympäristössä), tuotanto; koko `make dev-up` tuoreesta kloonista (Entra-alustus poistuu tickettiin 05).

## AI review

- [x] Tuore subagentti (opus), taso high, 1 kierros; luki myös Authentikin lähdekoodin. Ei korkean vakavuuden löydöksiä; 3 keskitasoa, 6 matalaa:
  M1. medium, Authentik kirjaa `id_token_hint`-GET-pyynnön (ID-token: sähköposti, nimi) omaan lokiinsa jokaisessa uloskirjautumisessa — **accepted risk** (kirjattu ADR-017:ään ja tähän; Caddy redaktoi mutta Authentik ei). Korjaus on POST-lomakeuloskirjautuminen (frontend + API-muoto), jota ei voitu todentaa tässä ympäristössä (ei pnpm/node_modules); jatkotyö.
  M2. medium, tuotannon kova katko (backend hylkää Entra-osoitteet) ei ollut dokumentoitu — **fixed** (julkaisun esto: ADR-017, `production.md`, `deployment.md`).
  M3. medium, "vahvistamaton osoite" -tarkistus olisi mennyt läpi vaikka vahvistusta ei valvottaisi — **fixed** (sähköposti pysyy seedatun käyttäjän, vain `shadow_verified_email` muuttuu; esiehto dokumentoitu).
  L1. low, metadatan päätepisteet eivät aina issuerin originissa — **fixed** (kaikki päätepisteet vaaditaan issuerin originiin; testit).
  L2. low, `OIDC_INTERNAL_BASE_URL` http tuotannossa — **fixed** (tuotannossa http vain yhden labelin Docker-palvelinnimelle; testit).
  L3. low, PKCE-policyn rento haara (avain puuttuu → läpi) — **verified** (Authentik asettaa avaimen aina authorize-pyynnöissä; negatiivinen testi `verify-authentik-local.py` tarkistaa joka ajolla; pidettävä Authentik-päivityksissä).
  L4. low, ID-token selkotekstinä tietokannassa — **accepted risk** (poistuu session mukana; ei palauteta/lokiteta; dokumentoitu `DATABASE.md`).
  L5. low, `make dev-up` vielä Entra-riippuvainen — **kirjattu** (ticket 05).
  L6. low, design vs toteutus (`EMAIL_NOT_VERIFIED`) — **fixed** (design päivitetty: yleinen epäonnistuminen).
  Lisäksi vanha testi (`test_auth_models.py`) kielsi `id_token`-sarakkeen sessioissa; päivitetty tietoisesti ADR-017:n mukaan (access-/refresh-tokenit ja secretit kielletty edelleen). Ei toista kierrosta; korjaukset varmistettu testeillä ja stackin uudelleenajolla. Yksi kierros kolmesta.

## Documentation effects

- [x] Update `docs/operations/` or `docs/runbooks/` — `docs/runbooks/authentik-local.md` (`make sign-in-verify`), `docs/runbooks/production.md` (release block)
- [x] Update architecture or ADR — `docs/architecture/data/DATABASE.md`, `docs/architecture/overview.md` (pointer), `docs/architecture/deployment.md`, `docs/architecture/diagrams/sequence-oidc-login.puml` + SVG, `db-physical-schema.puml` + SVG, ADR-004 note, ADR-017 consequences; komponenttikaavio tickettiin 05
- [x] Update `.env.example`

## Blocked by

- 01

## Completion record

- Backend autentikoi Authentikia vasten: Authentik-issuer-säännöt, sisäinen osoite, pakollinen vahvistettu sähköposti, ID-token vihjeeksi uloskirjautumiseen (migraatio 025), `make sign-in-verify`. Mukana ticketin 02 policyn korjaus (end-session ei saa kaatua PKCE-policyyn) ja web-providerin invalidation flow vaihdettu `default-invalidation-flow`:ksi, jotta Authentik-sessio päättyy ja paluuosoite `/login` toimii. Poikkeamat: logout-osoitteessa vihje vain kun ID-token on tallessa; kaikki päätepisteet issuerin originissa; tuotannon julkaisun esto. Commit: `feat: authentik-sign-in 03`.

## Comments

- Lähde: Yearclock `6848e72` (`authentik/`, `docker-compose.yml`, `docs/runbooks/authentik-*.md`, `backend/app/oidc.py`); kirjaa käytetyt lähdetiedostot lopussa.
