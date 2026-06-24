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

Status: frontend Docker runtime available, backend and database scaffolding pending

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

Frontendin `/api`-proxy osoittaa oletuksena hostilla ajettavaan backendin osoitteeseen:

```text
http://host.docker.internal:8000
```

Voit vaihtaa proxyn kohteen paikallisessa `.env`-tiedostossa:

```bash
FRONTEND_DEV_API_PROXY_TARGET=http://host.docker.internal:8000
```

Frontend preview -kontti buildatulle Vite-tuotokselle:

```bash
docker compose --profile preview up frontend-preview
```

Preview on saatavilla osoitteessa:

```text
http://localhost:4173
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
uv run fastapi dev
```

Backend scaffold lisätään erillisessä taskissa.

Tietokannan migraatiokomennot lisätään, kun migraatiotyökalu on valittu.

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
