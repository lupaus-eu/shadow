# Local Development

Tämä dokumentti kuvaa paikallisen DEV-ympäristön perusmallin.

Teknologiapino on päätetty tiedostossa `docs/decisions/ADR-001-tech-stack.md`.

---

# Initial Setup

```bash
git clone git@github.com:reflector-oy/schatten.git
cd schatten
```

Jos repository on jo alustettu manuaalisesti:

```bash
git remote add origin git@github.com:reflector-oy/schatten.git
git pull origin main
```

---

# Environment Variables

Repossa säilytetään vain tyhjät esimerkkipohjat:

```text
.env.example
.env.authentik.example
```

Paikallinen tiedosto:

```bash
cp .env.example .env
```

Älä commitoi `.env`-tiedostoja.

Paikallisen Authentikin salaisuudet ja suolatut salasanatiivisteet luodaan
erilliseen, Gitiltä ohitettavaan tiedostoon. Skripti ei luo bootstrap-API-tokenia
eikä kirjoita selväkielisiä salasanoja levylle:

```bash
scripts/setup-local-authentik.sh
```

Komento näyttää satunnaiset `akadmin`-, consultant-, admin- ja unmatched-
testikäyttäjien salasanat kerran terminaalissa. Tallenna tarvitsemasi salasanat
paikalliseen salasananhallintaan. Skripti ei ylikirjoita olemassa olevaa
`.env.authentik.local`-tiedostoa.

Sama komento luo `.local/authentik-tls/`-hakemistoon paikallisen CA:n ja
`auth.localhost`-palvelinsertifikaatin. Jos `.env.authentik.local` on jo
olemassa mutta TLS-materiaali puuttuu, aja erikseen:

```bash
scripts/setup-local-authentik-tls.sh
```

Skripti ei muuta käyttöjärjestelmän trust storea. Debian/Ubuntu-hostilla CA:n
voi luottaa eksplisiittisesti näin:

```bash
sudo install -m 0644 .local/authentik-tls/ca.crt \
  /usr/local/share/ca-certificates/schatten-local-authentik.crt
sudo update-ca-certificates
```

Muilla käyttöjärjestelmillä tuo `.local/authentik-tls/ca.crt` paikallisten
luotettujen root-varmenteiden storeen. Selain voi vaatia lisäksi oman
certificate-store-importin. Poista trust testin jälkeen tarvittaessa poistamalla
vain `schatten-local-authentik.crt` hostin trust storesta ja ajamalla trust
store -päivitys uudelleen. Älä koskaan luota tai siirrä `ca.key`-tiedostoa.

Authentikia käyttävät Compose-komennot lataavat ensin normaalit paikalliset
asetukset `.env`-tiedostosta ja sen jälkeen salaisuudet
`.env.authentik.local`-tiedostosta. Jälkimmäinen tiedosto yliajaa vain samannimiset
arvot. Local Compose pitää Authentikin issuerin ja Schattenin public originin
kiinteinä, jotta selain ja backend käyttävät aina samoja tarkkoja osoitteita.

---

# Branch Setup

Luo jokaiselle työlle oma branch:

```bash
git checkout main
git pull origin main
git checkout -b feature/TASK-001-short-name
```

Branch-prefixit:

```text
feature/
fix/
docs/
chore/
refactor/
```

---

# Running The App

Status: frontend, backend, application database and local Authentik runtimes available

Paikallinen ympäristö ajetaan Docker-konteissa:

- frontend container: React / TypeScript / Vite
- backend container: FastAPI / Python
- database container: PostgreSQL
- Authentik server and worker containers, loopback-only TLS Caddy plus a
  dedicated PostgreSQL container

Tuoreesta checkoutista koko paikallinen ympäristö käynnistetään näin:

```bash
scripts/setup-local-authentik.sh
docker compose --env-file .env --env-file .env.authentik.local \
  up -d database authentik-database authentik-server authentik-worker authentik-tls
uv run --env-file .env --project backend python backend/migrate.py up
docker compose --env-file .env --env-file .env.authentik.local exec -T database \
  sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  < db/init/002_seed_development_data.sql
docker compose --env-file .env --env-file .env.authentik.local up -d
```

Authentik tarvitsee virallisen vähimmäissuosituksen mukaan vähintään kaksi CPU-
ydintä ja 2 GB RAM-muistia. Ensimmäinen käynnistys voi kestää muutaman minuutin,
koska Authentik alustaa oman tietokantansa ja soveltaa blueprintit ennen kuin
backend käynnistyy.

Frontend-kehityskontti:

```bash
docker compose up frontend
```

Frontend on saatavilla osoitteessa:

```text
http://app.localhost:5173
```

Käytä aina `app.localhost`-nimeä selaimessa. Paikalliset host-only Schatten-
evästeet kuuluvat vain tälle hostille eivätkä siirry Authentikiin tai bare
`localhost`-palveluihin. Vite-portti sidotaan vain loopback-osoitteeseen.

Frontendin lähdekoodi bind mountataan konttiin, joten muutokset näkyvät ilman image rebuildia.

Frontendin `/api`-proxy osoittaa Docker Composessa oletuksena backend-konttiin:

```text
http://backend:8000
```

Voit vaihtaa proxyn kohteen paikallisessa `.env`-tiedostossa:

```bash
FRONTEND_DEV_API_PROXY_TARGET=http://backend:8000
```

Jos ajat frontendin Dockerissa mutta backendin suoraan hostilla, käytä:

```bash
FRONTEND_DEV_API_PROXY_TARGET=http://host.docker.internal:8000
```

Viten local `/api` proxy exercises the same browser-visible one-origin contract
as production Caddy. Production does not ship Vite or Authentik: it serves the
same `pnpm build` output from Caddy and changes only the backend OIDC provider
configuration to tenant-specific Entra values. Do not add provider-specific
logic or browser tokens to the frontend when comparing environments.

ADR-005 defines only local development/testing and production. TASK-040 adds an
opt-in local overlay that federates this repository-managed Authentik to the
same organisation's Entra tenant through a local-only app registration. That
supplemental path is not a production-like environment and does not validate
FastAPI's direct production Entra client.

Backend-kehityskontti:

```bash
docker compose --env-file .env --env-file .env.authentik.local up backend
```

Backendin Docker build käyttää repositoryn juurta build contextina, jotta sama
Dockerfile voi rakentaa production-imagen yhdessä `db/migrations/`-tiedostojen
kanssa. Dev-target säilyttää alkuperäisen `/app`-layoutin, bind mounttaa edelleen
vain `backend/`-hakemiston eikä aja migraatioita automaattisesti.

Backend on saatavilla osoitteessa:

```text
http://localhost:8000
```

Health endpoint:

```bash
curl --header 'Host: app.localhost:5173' http://localhost:8000/health
```

## Local Authentik OIDC

Authentik on vain paikallinen identity provider. Selain ja backend käyttävät
samaa tarkkaa per-provider issueria:

```text
https://auth.localhost:9443/application/o/schatten/
```

Discovery ja Authentik UI ovat saatavilla hostilta:

```text
https://auth.localhost:9443/application/o/schatten/.well-known/openid-configuration
https://auth.localhost:9443
```

TLS Caddyn portti `9443` sidotaan eksplisiittisesti osoitteeseen `127.0.0.1`.
Authentik-serverin porttia `9000` tai tietokantaporttia ei julkaista.
Docker-network-alias `auth.localhost` kuuluu TLS Caddylle, joten browser ja
backend käyttävät samaa issueria. Backend asentaa julkisen local CA -sertifikaatin
system trust bundleen ennen OIDC-startupia ja ohjaa local HTTP-clientin tähän
bundleen; Caddylle mountataan vain leaf-sertifikaatti
ja sen avain, ei CA:n private keytä. Authentik ei käytä Schattenin tietokantaa
tai database-useria, eikä worker mounttaa Docker socketia.

Versionhallittu `authentik/blueprints/schatten.yaml` provisionoi toistettavasti:

- confidential `schatten-local` OAuth2/OIDC providerin ja Schatten-sovelluksen
- tarkan callbackin
  `http://app.localhost:5173/api/v1/auth/callback`
- tarkan post-logout URI:n `http://app.localhost:5173/login`
- vain `openid profile email` -claim mappingit
- verified-email consultant-, admin- ja unmatched-testitunnukset

Blueprint ei lähetä ryhmiä, rooleja, Entra `oid`/`tid`-claimeja tai muita
application-oikeuksia. Authentikin consultant- ja admin-tunnukset linkittyvät
ensimmäisellä onnistuneella kirjautumisella valmiiksi seedattuihin Schatten
Users -riveihin sähköpostin perusteella. Tämän jälkeen tarkka `(issuer,
subject)` on pysyvä identiteetti. Schattenin tietokannan `role` on aina
sovellusroolin ainoa lähde.

Unmatched-tunnuksen `unmatched@example.local` sähköpostia ei seedata Schattenin
tietokantaan. Sen kirjautumisen pitää päätyä geneeriseen
`/login?error=authentication_failed`-virheeseen eikä se saa luoda User- tai
identity-riviä.

Discovery- ja JWKS-smoke:

```bash
scripts/smoke-local-authentik.sh
```

Compose-, loopback-, issuer-, image-, secret- ja production-manifest-tarkistus:

```bash
scripts/verify-local-authentik-config.sh
```

Pysäytä vain identity stack säilyttäen sen datan:

```bash
docker compose --env-file .env --env-file .env.authentik.local \
  stop authentik-tls authentik-worker authentik-server authentik-database
```

Kaikki paikalliset kontit pysäytetään normaalisti komennolla:

```bash
docker compose --env-file .env --env-file .env.authentik.local down
```

### Optional Entra federation through local Authentik

Tämä opt-in rehearsal testaa ketjun Schatten -> local Authentik -> Entra. Se ei
korvaa `docs/DEPLOYMENT.md`:n human-approved limited production smokea, koska
Schatten näkee tässä flow'ssa issuerina edelleen Authentikin eikä suoraa
Schatten-to-Entra- tai Coolify-rajaa testata.

Varmista ensin, että `schatten-authentik` löytyy Entran **App registrations**
-näkymästä; Enterprise application on rekisteröinnin service principal, mutta
redirect URI ja client secret hallitaan app registrationissa. Käytä
single-tenant Web-registrationia ja lisää täsmälleen:

```text
https://auth.localhost:9443/source/oauth/callback/schatten-auth/
```

Polun loppukauttaviiva ja slug `schatten-auth` ovat pakolliset. Lisää delegated
Microsoft Graph -oikeudet `openid`, `profile`, `email` ja `User.Read`; älä lisää
group-, role-, `offline_access`- tai application-permissioneita.

Luo gitignored asetustiedosto interaktiivisesti. Skripti ei tulosta secret-arvoa:

```bash
scripts/setup-local-entra.sh
scripts/verify-local-entra-config.sh
```

Overlay provisionoi Authentik 2026.5.6:een single-tenant Entra ID OAuth
Sourcen, tenant-specific endpointit, `schatten-auth`-login-painikkeen ja source
mappingin. Mapping asettaa `email_verified=true` vain kun Entra `/me` palauttaa
ei-tyhjän emailin. Group sync ja group/role mappingit pysyvät pois käytöstä.
Kolme blueprintia ajetaan järjestyksessä kertaluonteisessa
`authentik-entra-config`-palvelussa, ja backend käynnistyy vasta kun konfigurointi
onnistuu. Entra-arvoja ei anneta pitkäikäiselle Authentik workerille.

Käynnistä full stack overlaylla, aja migraatiot ja lisää matching email
Schattenin local allowlistiin:

```bash
docker compose \
  --env-file .env \
  --env-file .env.authentik.local \
  --env-file .env.entra.local \
  -f docker-compose.yml \
  -f docker-compose.entra.yml \
  up -d database authentik-database authentik-server authentik-worker authentik-tls
uv run --env-file .env --project backend python backend/migrate.py up
scripts/provision-local-entra-user.sh
docker compose \
  --env-file .env \
  --env-file .env.authentik.local \
  --env-file .env.entra.local \
  -f docker-compose.yml \
  -f docker-compose.entra.yml \
  up -d
```

Provisionointi on idempotentti eikä muuta olemassa olevan aktiivisen käyttäjän
roolia. Jos testisähköposti on jo aktiivisella käyttäjällä, varmista Users-UI:sta
että rooli on tarkoitettu. Authentik-source käyttää source-specific identifieria;
Schatten linkittää ensimmäisellä loginilla Authentikin `(issuer, subject)`-parin
pre-provisionoituun emailiin ja lukee roolin vain omasta tietokannastaan.

Avaa `http://app.localhost:5173`, aloita login ja valitse **Microsoft Entra
development**. Testaa myös Entra-käyttäjä, jonka emailia ei ole Schattenissa;
sen pitää päätyä geneeriseen authentication failureen luomatta User-, identity-
tai session-riviä. Authentik logout poistaa local provider-session, mutta Entra
voi käyttää olemassa olevaa upstream SSO -sessioita seuraavalla loginilla.

Client secretin rotaatiossa korvaa vain `.env.entra.local`, käynnistä
`authentik-entra-config` uudelleen overlay-komennolla (`docker compose ... run
--rm authentik-entra-config`) ja varmista source Authentik Admin UI:ssa. Älä
liitä arvoja issueen, PR:ään, komentoriville tai lokiin.

### Authentik image upgrade

Local stack on pinnattu Authentik-versioon `2026.5.6` ja multi-platform digest-
arvoon
`sha256:ed120caf710ccf82ef0026f0bc74e51615bc95ebff228a7a2d6fc60c441c3868`.
Authentikin oma PostgreSQL on pinnattu erikseen versioon `16.10-alpine` ja
digestiin `sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297`.

Päivitys tehdään tietoisena taskina:

1. Lue kohdeversion viralliset release- ja upgrade-ohjeet. Major-versiot
   päivitetään järjestyksessä.
2. Tarkista uusi tarkka patch ja multi-platform digest komennolla
   `docker buildx imagetools inspect ghcr.io/goauthentik/server:<patch>`.
3. Päivitä image-viite `docker-compose.yml`:ssä ja pinnausdokumentaatio tässä.
4. Aja `docker compose --env-file .env --env-file .env.authentik.local pull`, disposable fresh-
   volume bootstrap, discovery/JWKS-smoke ja manual login/logout molemmilla
   rooleilla ennen normaalin kehitysvolumen päivittämistä.

Älä käytä `latest`-tagia tai kopioi upstream Composea sellaisenaan. Viralliset
ohjeet: [Docker Compose installation](https://docs.goauthentik.io/install-config/install/docker-compose/),
[2026.5 release notes](https://docs.goauthentik.io/releases/2026.5/) ja
[upgrade guide](https://docs.goauthentik.io/install-config/upgrade/).

Frontend preview -kontti buildatulle Vite-tuotokselle:

```bash
docker compose --profile preview up frontend-preview
```

Preview on saatavilla osoitteessa:

```text
http://localhost:4173
```

The preview target is a developer convenience and does not reproduce the
production Host/proxy/header boundary. Build and verify the actual Caddy target
with the commands in `docs/DEPLOYMENT.md` when changing release behavior.

Tietokantakontti:

```bash
docker compose up database
```

Paikallinen PostgreSQL on saatavilla osoitteessa:

```text
localhost:5432
```

Tietokantakontti käyttää Docker-imagea:

```text
postgres:18.0
```

Paikallinen runtime käyttää versiota `18.0`, jotta kontti voidaan oikeasti käynnistää virallisesta PostgreSQL-imagesta. Production deploymentissa pinnaus pitää vaihtaa versioon `18.0.4`, kun managed PostgreSQL -ympäristö käyttää sitä ja sopiva image/target on saatavilla.

Paikallisen tietokannan oletusarvot ovat:

```text
database: schatten
user: schatten
password: schatten_dev_password
```

Voit vaihtaa arvoja paikallisessa `.env`-tiedostossa:

```bash
DATABASE_NAME=schatten
DATABASE_USER=schatten
DATABASE_PASSWORD=schatten_dev_password
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_URL=postgresql://schatten:schatten_dev_password@localhost:5432/schatten
```

`DATABASE_URL` on hostilla ajettavia backend- ja migraatiokomentoja varten.
Docker Compose muodostaa backend-kontin URL:n samoista
`DATABASE_NAME`-, `DATABASE_USER`- ja `DATABASE_PASSWORD`-arvoista käyttäen
hostina `database`-palvelua.

Tietokannan data säilyy konttien uudelleenkäynnistysten yli named volume -volumessa `database_data`.

Tietokantakontin pysäytys:

```bash
docker compose stop database
```

Tietokannan resetointi pysäyttää tietokantakontin ja poistaa vain paikallisen tietokantavolumen `schatten_database_data`. Älä aja tätä, jos haluat säilyttää paikallisen tietokantadatan.

```bash
docker compose stop database
docker volume rm schatten_database_data
```

Kontit pysäytetään:

```bash
docker compose down
```

Frontend-kehitys ilman Dockeria:

```bash
cd frontend
pnpm install
pnpm dev
```

Backend-kehitys:

```bash
cd backend
uv sync
uv run fastapi dev app/main.py
```

Tietokannan nykyisen skeeman voi alustaa tai päivittää ajamalla kaikki puuttuvat
migraatiot repositoryn juuresta:

```bash
uv run --env-file .env --project backend python backend/migrate.py up
```

Runner käyttää `DATABASE_URL`-ympäristömuuttujaa ja näyttää jokaisen sovelletun
migraation. Uusi `up` on turvallinen no-op, kun kaikki migraatiot on jo ajettu.

Viimeisimmän sovelletun migraation voi peruuttaa tarkalla tiedostonimellä:

```bash
uv run --env-file .env --project backend \
  python backend/migrate.py 009_add_auth_identity_session_schema.down.sql
```

Down-migraatiot voivat poistaa dataa. Käytä niitä vain disposable-paikallisessa
tietokannassa tai varmista palautuskelpoinen backup. Runner ei salli vanhemman
migraation rollbackia ennen uudempien migraatioiden eksplisiittistä perumista.

Migration 009 adds required User emails and deliberately has no legacy-data
backfill. If a local migration-008 database contains User rows, discard/reset
that disposable database before running `up`.

Jos paikallinen skeema on luotu vanhoilla manuaalisilla `psql`-komennoilla,
varmista ensin että se vastaa migraatiota 009 ja ota historia käyttöön ajamatta
SQL:ää uudelleen:

```bash
uv run --env-file .env --project backend python backend/migrate.py baseline 009
```

Baseline ei tarkista skeeman sisältöä eikä päättele sen versiota. Komento on
operaattorin vakuutus valitusta tasosta, ja se sallitaan vain olemassa olevalle
skeemalle, jolla ei vielä ole migraatiohistoriaa.

Production-tietokannan käyttöönotto, backup- ja baseline-portti sekä
automaattinen release migration on kuvattu erikseen tiedostossa
`docs/DEPLOYMENT.md`. Älä käytä production Compose -tiedostoja paikallisen dev
backendin korvikkeena.

Paikallisen kehitysdatan seed on dev-only ja se varmistaa aktiiviset
`consultant@example.local` consultant- ja `admin@example.local` admin-rivit sekä
repo-local JSON-lähteeseen perustuvan Schattenin default-metamallin. Seed ei luo
identiteetti-, login transaction- tai session-riveja:

```bash
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/init/002_seed_development_data.sql
```

Seed lukee lähteen ajon aikana tiedostosta:

```text
db/init/metamodel_state_##default##.json
```

Seed on tarkoitettu vain paikalliseen kehitykseen. Sitä ei ajeta tuotantoon.

## Rendering Diagrams

PlantUML diagrams can be rendered through the Docker Compose docs profile:

```bash
docker compose --profile docs build diagram-renderer
docker compose --profile docs run --rm diagram-renderer
```

The default command renders:

```text
docs/diagrams/db-physical-schema.puml
```

to:

```text
docs/diagrams/generated/db-physical-schema.svg
```

---

# Verification Before PR

Backendin oletustarkistukset:

```bash
cd backend
uv run ruff check .
uv run pytest
uv run pyright
```

Frontendin oletustarkistukset:

```bash
cd frontend
pnpm lint
pnpm test
pnpm build
```

Kun frontendin typecheck-scripti on lisätty, aja myös se ennen PR:ää.

## Manual QA: Clean Organisation States

Use this checklist when reviewing the organisation-state cleanup flow:

- Start the database, backend and frontend locally.
- Select or create a non-protected scenario with at least one active
  organisation state.
- In the Scenarios tab, choose the scenario, click `Clean states`, confirm the
  action and verify the success message shows the cleaned count.
- Verify the selected scenario's organisation state list refreshes to empty.
- Repeat cleanup for the same non-protected scenario and verify the no-op
  result reports `Cleaned 0 state(s).`
- Select the protected `Reality` scenario and verify the cleanup action is not
  available in the UI.
- Optionally verify the backend guard directly:

```bash
curl -i -X POST \
  http://localhost:8000/api/v1/organisations/{organisation_key}/scenarios/reality/org-states/clean
```

Expected result for the protected scenario backend guard is HTTP `409`.
No authentication or authorization behavior is implemented as part of this
cleanup flow.

---

# Update Branch Before PR

```bash
git fetch origin
git rebase origin/main
```

Jos rebase aiheuttaa konflikteja:

1. ratkaise konfliktit
2. aja tarkistukset uudelleen
3. jatka rebasea
4. pushaa branch

---

# Push

```bash
git push -u origin feature/TASK-001-short-name
```

---

# Local Data Rules

- Älä käytä tuotantodataa lokaaliympäristössä ilman hyväksyntää.
- Älä commitoi paikallisia dumppeja.
- Älä commitoi salaisuuksia.
- Testidata luodaan fixtureillä, seedeillä tai erillisillä kehitysskripteillä.
