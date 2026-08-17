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

Repossa säilytetään vain:

```text
.env.example
```

Paikallinen tiedosto:

```bash
cp .env.example .env
```

Älä commitoi `.env`-tiedostoja.

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

Status: frontend, backend and database Docker runtimes available

Paikallinen ympäristö ajetaan Docker-konteissa:

- frontend container: React / TypeScript / Vite
- backend container: FastAPI / Python
- database container: PostgreSQL

Frontend-kehityskontti:

```bash
docker compose up frontend
```

Frontend on saatavilla osoitteessa:

```text
http://localhost:5173
```

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

Backend-kehityskontti:

```bash
docker compose up backend
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
curl --header 'Host: localhost:5173' http://localhost:8000/health
```

Frontend preview -kontti buildatulle Vite-tuotokselle:

```bash
docker compose --profile preview up frontend-preview
```

Preview on saatavilla osoitteessa:

```text
http://localhost:4173
```

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
uv run --project backend python backend/migrate.py up
```

Runner käyttää `DATABASE_URL`-ympäristömuuttujaa ja näyttää jokaisen sovelletun
migraation. Uusi `up` on turvallinen no-op, kun kaikki migraatiot on jo ajettu.

Viimeisimmän sovelletun migraation voi peruuttaa tarkalla tiedostonimellä:

```bash
uv run --project backend python backend/migrate.py 009_add_auth_identity_session_schema.down.sql
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
uv run --project backend python backend/migrate.py baseline 009
```

Baseline ei tarkista skeeman sisältöä eikä päättele sen versiota. Komento on
operaattorin vakuutus valitusta tasosta, ja se sallitaan vain olemassa olevalle
skeemalle, jolla ei vielä ole migraatiohistoriaa.

Staging- ja production-tietokantojen käyttöönotto, backup- ja baseline-portti
sekä automaattinen release migration on kuvattu erikseen tiedostossa
`docs/DEPLOYMENT.md`. Älä käytä production Compose -tiedostoja paikallisen dev
backendin korvikkeena.

Paikallisen kehitysdatan seed on dev-only ja se luo tyhjään tietokantaan
`admin@example.local`-sähköpostia käyttävän dummy-adminin sekä repo-local
JSON-lähteeseen perustuvan Schattenin default-metamallin. Seed ei luo
identiteetti-, login transaction- tai session-riveja:

```bash
PGPASSWORD=schatten_dev_password psql -h localhost -p 5432 -U schatten -d schatten -f db/init/002_seed_development_data.sql
```

Seed lukee lähteen ajon aikana tiedostosta:

```text
db/init/metamodel_state_##default##.json
```

Seed on tarkoitettu vain paikalliseen kehitykseen. Sitä ei ajeta staging- tai tuotantoympäristöihin.

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
