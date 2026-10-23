# Database Migrations

Tämä hakemisto sisältää versionhallittavat tietokantamigraatiot.

Status: paired migration convention and Python/Psycopg runner available

Tietokantateknologia on PostgreSQL ja ORM on SQLAlchemy. Migraatiot ajetaan
repositoryn `backend/migrate.py`-työkalulla ADR-002:n mukaisesti.

---

# Naming Convention

Käytä lineaarista kolminumeroista prefixiä ja lowercase snake_case -nimeä:

```text
001_create_customers.sql
002_create_contacts.sql
003_create_customer_addresses.sql
004_create_documents.sql
005_add_document_status.sql
006_create_ai_extractions.sql
```

Muoto:

```text
NNN_<verb>_<object>.sql
NNN_<verb>_<object>.down.sql
```

Jokaisella up-migraatiolla pitää aina olla täsmälleen samalla stemillä nimetty
down-migraatio. Esimerkiksi `009_add_invoice_status.sql` vaatii tiedoston
`009_add_invoice_status.down.sql`.

Sallitut yleiset verbit:

- `create`
- `add`
- `alter`
- `rename`
- `drop`
- `backfill`

Esimerkkejä:

```text
001_create_customers.sql
002_create_contacts.sql
003_add_customer_soft_delete.sql
004_create_documents.sql
005_add_document_status.sql
006_create_ai_extractions.sql
```

---

# Rules

- Yksi looginen muutos per migraatio.
- Numerointi kasvaa yhdellä.
- Numerointi alkaa `001`:stä ja muodostaa aukottoman lineaarisen ketjun.
- Lisää jokainen up- ja down-migraatio samassa muutoksessa.
- Älä muuta jo mainiin mergeättyä migraatiota ilman erillistä päätöstä.
- Korjaa aiempi julkaistu migraatio uudella migraatiolla.
- Migraatio ei saa sisältää salaisuuksia.
- Migraation pitää olla reviewattava.
- Tuotantotietokantaa ei muuteta käsin.
- Down-migraatio voi tuhota dataa. Ota tarvittava varmuuskopio ennen rollbackia.
- Down-migraatio ajetaan vain, jos sen up-migraatio on viimeisin sovellettu migraatio.
- Deployment ajaa vain `up`-komennon. Deployment- tai application rollback ei
  käynnistä down-migraatiota automaattisesti.

---

# Current Migrations

The current ordered migration chain is:

```text
001_create_core_schema.sql
002_add_org_state_name_and_org_name_unique_index.sql
003_alter_scenario_target_dates_not_null.sql
004_alter_graphs_to_scenarios.sql
005_add_graph_logical_delete_dates.sql
006_create_customers.sql
007_create_contacts.sql
008_create_customer_addresses.sql
009_add_auth_identity_session_schema.sql
010_create_prediction_schema.sql
011_alter_prediction_target_observation_source.sql
012_add_timeserie_short_name.sql
013_create_derived_metrics.sql
014_add_prediction_intervals.sql
015_create_prediction_requests.sql
016_add_prophet_result_kind.sql
017_create_mcp_oauth_schema.sql
```

Jokaisella yllä olevalla tiedostolla on vastaava `.down.sql`-tiedosto.

---

# Commands

Aja kaikki puuttuvat migraatiot repositoryn juuresta:

```bash
uv run --project backend python backend/migrate.py up
```

Peruuta viimeisin sovellettu migraatio antamalla tarkka down-tiedostonimi:

```bash
uv run --project backend python backend/migrate.py 009_add_auth_identity_session_schema.down.sql
```

Runner ei hyväksy polkuja, versionumeroiden lyhenteitä, soveltamattomia
migraatioita tai muuta kuin viimeisintä sovellettua down-migraatiota.

Jos skeema on luotu ennen migraatiohistorian käyttöönottoa, tarkista sen taso ja
rekisteröi se eksplisiittisesti suorittamatta SQL-tiedostoja:

```bash
uv run --project backend python backend/migrate.py baseline 009
```

Baseline on operaattorin vakuutus siitä, että olemassa oleva skeema vastaa
annettua tasoa. Runner ei päättele tasoa automaattisesti.

Migration 009 intentionally adds required `users.email` without a backfill or
temporary nullable state. It assumes migration-008 databases contain no
retained User rows. Reset disposable local databases before applying it; do not
apply it to retained data without a separately reviewed migration plan.

---

# Migration History And Safety

Runner ylläpitää `schema_migrations`-taulua. Se tallentaa version, up-tiedoston
nimen, SHA-256-tarkistussumman ja suoritusajan. Historia hyväksytään vain, kun se
on repositoryketjun yhtenäinen prefix ja tallennetut nimet sekä tarkistussummat
vastaavat nykyisiä tiedostoja.

Jokainen migraatio ja historiapäivitys suoritetaan samassa transaktiossa.
Session-tason PostgreSQL advisory lock estää rinnakkaisten runnerien
lomittumisen. Yhden pending-migraation epäonnistuminen ei peruuta sitä ennen jo
onnistuneesti committoituja migraatioita.

Migration 004:n alkuperäinen up-migraatio poisti graph-metadataa ja
graph-to-org-state-assosiaation. Sen down-migraatio palauttaa legacy-rakenteen
vain, kun jokainen graph-dataa sisältävä scenario liittyy täsmälleen yhteen
organisation stateen. Muuten rollback epäonnistuu atomisesti.

Migration 015 preserves all existing prediction versions and does not create
request history for them. Its down migration deletes only prediction request
history and must be run with every prediction worker stopped; it does not delete
completed prediction versions or their owned rows.

Migration 016 recreates the `prediction_model_results.result_kind` CHECK with
the `prophet` result kind (ADR-014) and changes no rows. Its down migration
deletes every `prophet` result and its prediction points, then restores the
five-kind CHECK; other results and their versions are kept. Run it only with
the prediction worker stopped and no queued or running requests that select
Prophet, because a release before ADR-014 cannot calculate them.

Migration 017 creates the AI Domain's MCP OAuth tables (`mcp_oauth_clients`,
`mcp_oauth_authorization_requests`, `mcp_oauth_grants`, `mcp_oauth_tokens`,
ADR-015) and changes no existing table. They store only SHA-256 hashes of
request ids, codes and tokens. Its down migration drops the four tables and
deletes every MCP client registration, grant and token; MCP clients must
register and authorize again afterwards.

## Deployment Compatibility

Production-release ajaa `python migrate.py up` erillisenä one-shot
jobina ennen uuden backendin käynnistymistä. Sama immutable backend-image sisältää
sekä runnerin että tämän hakemiston migraatiot. PostgreSQL advisory lock suojaa
myös rinnakkaisilta deploymenteilta.

Käytä skeemamuutoksissa expand/contract-mallia:

1. lisää uusi rakenne ja tarvittava backfill yhteensopivasti
2. julkaise sovellus, joka toimii transitionaalisen skeeman kanssa
3. poista vanha rakenne vasta myöhemmässä migraatiossa, kun vanha sovellus ja
   sen rollback-ikkuna ovat poistuneet

Älä yhdistä destruktiivista cleanupia julkaisuun, jossa vanha tai rollbackissa
palautuva sovellus tarvitsee poistettavaa rakennetta.

---

# Relationship To Init Scripts

`db/init/` voi sisältää kehitysympäristön alustusskriptejä.

Migraatiot ovat silti source of truth skeemamuutoksille.

Älä kopioi muutoksia vain init-skripteihin. Lisää aina migraatio, jos skeema muuttuu.

---

# Required Documentation Updates

Kun lisäät migraation, tarkista pitääkö päivittää:

- `docs/data/DATABASE.md`
- `docs/data/DATA-MODEL.md`
- `docs/domains/<DOMAIN>.md`
- `docs/concepts/<CONCEPT>.md`
- `docs/diagrams/db-physical-schema.puml`
- `docs/diagrams/generated/db-physical-schema.svg`
- relevantti ADR
