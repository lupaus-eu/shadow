# Local Development

Tämä dokumentti kuvaa paikallisen DEV-ympäristön perusmallin.

Teknologiapino on vielä `TBD`, joten osa komennoista täsmennetään ADR-päätösten jälkeen.

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

Status: TBD

Kun stack on päätetty, lisää tähän:

- dependency install -komento
- dev server -komento
- Docker Compose -komento
- tietokannan migraatiokomennot
- testikomennot

Esimerkkirunko myöhempää käyttöä varten:

```bash
docker compose up -d
npm install
npm run dev
```

Älä ota näitä komentoja pakollisiksi ennen kuin teknologiapino on päätetty.

---

# Verification Before PR

Kun stack on päätetty, minimivaatimus ennen PR:ää:

```bash
npm run lint
npm test
npm run build
```

Jos projekti käyttää muuta työkalua, päivitä komennot tähän.

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
