# Ticket 01: Local Authentik stack (079A)

Status: implemented

## Goal

The local stack runs Authentik behind Caddy at `https://id.app.localhost`, with blueprints that create the web OIDC application, the strong-authentication and invitation flows, a minimal brand and the dev users.

## Implementation

- Compose: `authentik-db-init` (script from Yearclock `docker/postgres/`, creates role and database `authentik` in the existing PostgreSQL), `authentik-server`, `authentik-worker`, `authentik-config-init`; pinned `AUTHENTIK_VERSION=2026.8.5`; mail to Mailpit; fixed local IPs; trusted proxy limited to the Caddy peer; named volumes `authentik_media`/`authentik_templates` (the retired `authentik_*` volumes cleaned up by runbook).
- Verify that Authentik 2026.8.5 runs on PostgreSQL 18; if not, record it and use a dedicated PostgreSQL 17 container for Authentik only (design decision D5).
- `authentik/configure.sh` and blueprints `shadow-identity-flows.yaml`, `shadow-application.yaml`, `shadow-brand.yaml` (+ css), `authentik/dev/shadow-dev-users.yaml` (dev only; users `consultant@example.local` and `admin@example.local`, TOTP with a documented dev secret, password from `AUTHENTIK_DEV_USER_PASSWORD`).
- Caddy: host `id.app.localhost` (reverse proxy to `authentik-server:9000`, CSP) and the local certificate for it (`scripts/setup-local-app-tls.sh`).
- `make dev-up` starts the Authentik services; backend OIDC settings are ticket 03.
- Runbooks `docs/runbooks/authentik-local.md`, `authentik-invitations.md`, `authentik-upgrade.md`; `docs/admin/` operator guidance (invitation, recovery).
- `.env.example` and `docs/architecture/deployment.md` (names only; production values are step 086A).
- Not done: backend changes, MCP provider, Entra removal.

## Acceptance criteria

- [x] `make dev-up` brings the Authentik containers up healthy and `authentik-config-init` applies every blueprint without manual console steps.
- [x] `https://id.app.localhost` serves the Authentik sign-in over the local certificate; `https://id.app.localhost/application/o/shadow/.well-known/openid-configuration` returns the web provider's discovery document with the public issuer.
- [x] With `AUTHENTIK_ENROLLMENT_OPEN=false` enrollment needs an invitation and verifies the email (mail arrives in Mailpit); with `true` it is open.
- [x] Sign-in always requires TOTP or a passkey; a user without a factor must enroll one; recovery needs email plus a factor.
- [x] The dev users can sign in at Authentik with the documented dev credentials.
- [x] The result of the PostgreSQL 18 check is recorded in the technical design.

## Testing

- [x] Authentik — `docker compose up` of the new services; blueprint application logs show success (the Authentik API with the bootstrap token lists the application and flows)
- [x] Browser/E2E — headless flow-executor run of enrollment, TOTP, sign-in and the authorization code (`scripts/verify-authentik-local.py`), evidence in `docs/operations/qa/AUTHENTICATION-QA-CHECKLIST.md`; passkey and recovery not run (need a browser)
- [x] Compose/architecture — `docker compose config`, `make diagrams` if a diagram changes
- [x] Backend/Frontend — not applicable

## Ajetut tarkistukset

- [x] Puhtaalta pöydältä oikeilla konteilla (eristetty Compose-projekti `shadowverify`, `down -v` ja uusi nosto): `database`, `mailpit`, `authentik-server`, `authentik-worker`, `authentik-config-init` (exit 0, "Authentik configuration check passed"), Caddy `id.app.localhost`. Authentik 2026.8.5 toimii PostgreSQL 18.6:lla.
- [x] `python3 scripts/verify-authentik-local.py` ja `--enrollment` (suljettu enrollment): kaikki tarkistukset läpi (MFA, authorization code + PKCE, ID-tokenin vahvistettu sähköposti, kutsu, vahvistussähköposti, pakotettu TOTP, vahvistettu osoite, vaihdettu osoite ei enää vahvistettu).
- [x] Entra-tunnusten vuoto: stack ajettiin Entra-tyylisillä `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET`-arvoilla ympäristössä; Authentik-konttien ympäristössä niitä ei ole ja provider käyttää `LOCAL_OIDC_*`-arvoja.
- [x] `docker compose config`; `bash -n scripts/setup-local-app-tls.sh`; sertifikaatti uusittu (SAN `app.localhost`, `id.app.localhost`, SKI/AKI).
- Ei ajettu: koko `make dev-up` (backend, frontend ja vanhat Entra-asetukset; backend siirtyy tickettiin 03), passkey ja palautusflow (selain), ei backend-/frontend-testejä (ei koodimuutosta).

## AI review

- [x] Tuore subagentti (opus), taso medium–high, 1 kierros. 1 korkea, 3 keskitason, useita matalia:
  1. **high**, `make dev-up` antoi Authentikille Entra-tunnukset (`.env.entra.local` ylikirjoitti `OIDC_CLIENT_*`) — **fixed** (Authentikin web-client omilla `LOCAL_OIDC_*`-nimillään; todennettu ajamalla Entra-tyylisillä arvoilla; runbookin komennot `make authentik-apply`).
  2. medium, luotettu proxy koko verkolle — **fixed** (vain Caddy `.2` ja backend `.3`).
  3. medium, vahvistettu sähköposti kirjattiin vasta viimeisessä vaiheessa — **fixed** (kirjataan MFA-vaiheen sidonnassa, kun vahvistuslinkkiä on klikattu, ja loginissa).
  4. medium, `email_verified` ei sidottu osoitteeseen (osoitteen vaihto säilytti vahvistuksen; linkitys uhrin tiliin) — **fixed** (attribuutti `shadow_verified_email` sisältää vahvistetun osoitteen, scope vertaa nykyiseen osoitteeseen; tenant-asetukset: oman sähköpostin ja käyttäjänimen vaihto pois, impersonointi pois; negatiivinen testi skriptissä).
  5. low, Caddy lokitti kutsu- ja vahvistustokenit — **fixed** (`itoken`, `flow_token`, `query` redaktoidaan).
  6. low, CSP puuttui ja otsakkeet tuplina — **fixed** (suppea CSP; `header_down` korvaa Authentikin arvot).
  7. low, config-init-virheet jäivät huomaamatta — **fixed** (`run --rm` välittää poistumiskoodin; `authentik/verify-config.py` tarkistaa olennaiset ennen onnistumisen kirjaamista).
  8. low, version puuttui sormenjäljestä — **fixed** (`CONFIG_IMAGE_VERSION`).
  9. low, brandilta puuttui palautusflow; palautus aktivoi deaktivoidun käyttäjän — **fixed** (`flow_recovery` asetettu, `activate_user_on_success: false`; operaattorivaroitukset dokumentoitu).
  10. low, verifiointiskriptin siivous ja kestävyys — **fixed** (siivous `finally`:ssä, aikakatkaisut, negatiivinen testi); X509-strict-lievennys jäi (sertifikaatti saa nyt SKI/AKI:n, vanhat sertifikaatit tarvitsevat lievennyksen).
  11. low, db-init ilman suojaa — **fixed** (kieltäytyy, jos Authentik-käyttäjä tai -kanta on sama kuin sovelluksen).
  12. low, jaettu env-ankkuri antoi palvelimelle tarpeettomia salaisuuksia — **fixed** (ankkuri jaettu: palvelin ytimen asetukset, worker ja config-init lisäksi blueprint-syötteet).
  13. low, `ip_range` voi vaatia verkon uudelleenluonnin — **documented** (runbook).
  14. low, prosessiaukot — **fixed** (design D5, QA-checklist, ticket); komponenttikaavio siirtyy tickettiin 05 (kuvaa vasta backendin vaihdon jälkeen).
  Informatiivinen: impersonointi oli oletuksena päällä — sammutettu. Ei toista kierrosta; korjaukset varmistettu koko stackin uudelleenajolla. Yksi kierros kolmesta.

## Documentation effects

- [x] Update `docs/admin/` — operator guidance
- [x] Update `docs/operations/` or `docs/runbooks/` — `authentik-local.md`, `authentik-invitations.md`, `authentik-upgrade.md`, `local-development.md`, QA checklist
- [x] Update architecture or ADR — `docs/architecture/deployment.md`, `docs/architecture/stack.md`; komponenttikaavio + SVG tickettiin 05
- [x] Update `.env.example`

## Blocked by

- ADR-017 (hyväksytty 2026-11-06)

## Completion record

- Paikallinen Authentik-stack, blueprintit (flow't, web-sovellus, brändi, dev-käyttäjät), Caddy `id.app.localhost`, TLS, runbookit ja verifiointiskripti valmiit. Poikkeamat suunnitelmasta: `LOCAL_OIDC_*`-nimet Authentikin web-clientille (vältetään Entra-tunnusten vuoto, kunnes Entra poistuu), MFA-vaihe sidottu enrollmentiin, vahvistettu osoite attribuuttina, tenant-asetukset `ak shell`-skriptillä (blueprint ei voi muuttaa tenanttia), dev-TOTP-laitteet skriptillä (blueprint ei voi asettaa avainta). Commit: `feat: authentik-sign-in 01`.

## Comments

- Lähde: Yearclock `6848e72` (`authentik/`, `docker-compose.yml`, `docs/runbooks/authentik-*.md`, `backend/app/oidc.py`); kirjaa käytetyt lähdetiedostot lopussa.
