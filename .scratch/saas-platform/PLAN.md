# Shadow SaaS -siirtymän toteutussuunnitelma

Status: needs-info — alustava kokonaissuunnitelma; päätökset P1–P11 ja vaiheiden PRD:t speksataan erikseen (`FEATURE_WORKFLOW.md`)

Päivitetty: 2026-11-06 (vaihe 1 toteutettu; vaihe 2 speksattu `.scratch/authentik-sign-in/`)

Tämä suunnitelma kuvaa, miten Shadow muutetaan yhden yrityksen sisäisestä sovelluksesta monitenanttiseksi SaaS-palveluksi samalla alustamallilla kuin Yearclock (`../yearclock`). Mitään ei toteuteta ennen kuin suunnitelma ja kohdan 2 päätökset on hyväksytty. Suunnitelma on kokonaiskartta: jokainen vaihe speksataan omaksi `.scratch/`-featurekseen (PRD → domain model tarvittaessa → technical design → `issues/`), ks. kohta 4.0.

---

## 1. Tavoite ja reunaehdot

Käyttäjän asettamat ehdot:

1. **Tunnistautuminen**: sama Authentik-pohjainen tunnistautuminen kuin Yearclockissa. Microsoft Entra -kirjautuminen poistetaan kokonaan.
2. **Laskutus**: Stripe-tilaus ja istuinpohjainen (seat) laskutus kuten Yearclockissa.
3. **Platform-sivu**: erillinen `/platform`-konsoli SaaS-ylläpitäjän työkaluille.
4. **Roolit**: varsinaisessa sovelluksessa roolit owner, admin ja tavallinen käyttäjä (member).
5. **Varmuuskopiot**: restic Scalewayn S3-bucketiin kuten Yearclockissa.
6. **Legal-dokumentit**: sama käytäntö kuin Yearclockissa (versioidut tekstit, julkinen jakelu, hyväksyntäkirjaukset, Owner-ilmoitukset).
7. **Alustakoodi** kopioidaan Yearclockista mahdollisimman sellaisenaan, koska sama tiimi ylläpitää molempia palveluita.

Lähtötilanne lyhyesti (kartoituksen tulokset):

| Alue | Shadow nyt | Yearclock (malli) |
|---|---|---|
| Tunnistautuminen | Provider-neutraali OIDC-koodi, mutta `config.py` sallii vain `login.microsoftonline.com`; login ei koskaan luo käyttäjää | Authentik (blueprintit, MFA pakollinen, passkey), login luo `customer`-tilin |
| Käyttäjät ja roolit | Globaali `users.role` = `admin` / `consultant` | `user_accounts` + `organization_memberships` (`owner`/`admin`/`member`), erillinen `platform`-tililuokka |
| Tenanttius | "Organisation" on mallinnettava organisaatio, **ei** turvaraja; kaikki näkevät kaiken; `customers` ei ole rajattu | Organization = tenantti, eksplisiittinen route, PostgreSQL RLS (`yearclock_app`-rooli + GUC:t) |
| Laskutus | Ei mitään (`docs/domains/BILLING.md` on kandidaatti) | Stripe Checkout, seatit, grace/read-only, portaali, webhookit (raaka `httpx`, ei SDK:ta) |
| Platform | Ei ole | `/platform/*` konsoli, `platform_admin`/`support_agent`, CLI-enrollment |
| Legal | Ei ole | `backend/legal/<key>.<fi|en>.md`, `legal_acceptances`, ilmoitusjobit |
| Audit | `created_by`-sarakkeet, MCP OAuth audit stderriin | `audit_events` append-only |
| Taustatyöt ja sähköposti | Vain `prediction-worker`, ei sähköpostia | `worker` + `background_jobs`/`outbox_messages`, Scaleway TEM |
| Varmuuskopiot | Ofelia + `pg_dump` + GPG samalle hostille, 7 pv | restic → Scaleway S3, systemd-ajastimet, sovellus- ja Authentik-kanta |
| MCP | Oma OAuth 2.1 -auktorisointipalvelin cookie-session päällä (DCR, `shadow.read/write`) | Authentikin erillinen MCP-provider (ADR-0038) |
| Migraatiot | Oma SQL-runner, parit `NNN_*.sql`/`.down.sql`, viimeisin 020 | Alembic |
| Frontend | Käsin kirjoitettu CSS, ei i18n:ää (englanti) | Tailwind 4 + Radix, i18n fi/en |

---

## 2. Päätökset, jotka tarvitaan ennen toteutusta

Kullekin päätökselle on suositus. Vaihe 0 kirjaa hyväksytyt päätökset ADR:iksi.

**P1. Tenantin nimi.** Shadowin "Organisation" tarkoittaa jo mallinnettavaa asiakasorganisaatiota (MCP-työkalut `list_organisations`, URL `/shadow/:orgId`). Yearclockin tenantti on "Organization", joten saman nimen käyttö sekoittaisi käsitteet.
- *Suositus:* tenantti on koodissa **`tenant`** (`tenants`, `tenant_memberships`, `TenantRole`) ja käyttöliittymässä "Company / Yritys". Yearclockista kopioitu koodi nimetään mekaanisesti `organization` → `tenant`. Shadowin Organisation säilyy ennallaan.
- *Vaihtoehto:* tenantti on `organization` kuten Yearclockissa ja Shadowin Organisation nimetään uudelleen (esim. "Model"). Tämä on paljon laajempi muutos ja rikkoo MCP-työkalujen nimet.

**P2. Tenantin rajaus ja eristys.**
- *Suositus:* kopioidaan Yearclockin malli kokonaan. Tenantti on eksplisiittinen API-polussa (`/api/v1/tenants/{tenant_id}/…`), roolien tarkistus tehdään backendissä ja PostgreSQL RLS toimii toisena puolustuslinjana (`shadow_app` NOLOGIN NOBYPASSRLS + `app.current_tenant_id`-GUC). Yearclockin laskutus-, legal- ja audit-koodi olettaa juuri tämän `transaction_session`/`RequestContext`-mallin.

**P3. Member-roolin näkyvyys.**
- *Suositus:* member näkee ja muokkaa kaikkia tenantin Organisationeja kuten `consultant` nyt. Admin hallitsee lisäksi ihmisiä, MCP:tä ja tukipääsyä, ja Owner lisäksi laskutusta, omistajuutta ja tenantin poistoa (Yearclockin matriisi). Organisaatiokohtaiset käyttöoikeudet (vrt. Yearclockin editor/viewer) jätetään myöhemmäksi.

**P4. MCP-tunnistautuminen.**
- **Päätetty (2026-11-06): siirrytään Yearclockin malliin** (Yearclock ADR-0037/0038). MCP-rajapinta on OAuth-resurssipalvelin, jonka access tokenit myöntää Authentikin oma MCP-provider "Shadow MCP" (luottamuksellinen client, client id ja secret syötetään MCP-clientin connector-asetuksiin, tiukat redirect-URI:t, ei DCR:ää). Shadowin oma OAuth 2.1 -palvelin (ADR-015, TASK-069D–F/L) puretaan. Toteutus on vaiheessa 3b.
- *Aiempi suositus (hylätty):* säilytetään Shadowin oma OAuth 2.1 -palvelin. Se toimii cookie-session päällä, joten Authentik-vaihto on sille läpinäkyvä, ja se on tuotannossa testattu Claude Coden, claude.ai:n ja Claude Desktopin kanssa (DCR, change-set review). Siihen lisätään tenanttisidonta ja Yearclockin mukaiset tenanttikohtaiset kytkimet `mcp_enabled` ja `mcp_platform_blocked`.

**P5. Authentik-instanssi.** *Päätetty (2026-11-06, vaiheen 2 speksaus): oma instanssi, ADR-017.*
- *Suositus:* Shadowille oma Authentik-instanssi omalla identity-hostilla, esim. `id.shadow.lupaus.eu`. Konfiguraatio ja blueprintit kopioidaan Yearclockista.
- *Vaihtoehto:* jaettu Authentik molemmille palveluille (yksi tili, kaksi provideria). Tämä vaatisi oman ADR:n ja hostin.

**P6. Frontendin tekniikka.**
- *Suositus:* platform-konsoli, tenantin hallintasivut (People, Billing, Legal, Support, Activity), legal-sivut ja aktivointisivu kopioidaan Yearclockista. Niitä varten lisätään riippuvuudet Tailwind 4 (ilman preflightia, jotta Shadowin `reset.css` säilyy), Radix-primitiivit, `lucide-react`, `react-markdown` ja `remark-gfm` sekä Yearclockin `ui/`-kirjasto ja `theme.css`. AGENTS.md vaatii riippuvuuksille erillisen hyväksynnän. Shadowin mallinnusnäkymät säilyvät ennallaan.
- *Vaihtoehto:* kopioitavat sivut kirjoitetaan uudelleen Shadowin CSS-komponenteilla, jolloin uusia riippuvuuksia ei tule mutta alustan koodi poikkeaa Yearclockista.

**P7. Kieli.**
- *Suositus:* kopioidaan Yearclockin kevyt i18n-ratkaisu (`i18n.ts`, fi/en, `PATCH /auth/profile/locale`). Ensimmäisessä vaiheessa sitä käyttävät vain kopioidut alustasivut; legal-tekstit ovat fi ja en. Mallinnusnäkymät pysyvät englanninkielisinä, kunnes niiden kääntämisestä päätetään erikseen.

**P8. Yrityksen oma tenantti.** Nykyinen tuotantodata kuuluu omalle yritykselle.
- *Suositus:* lisätään platformille tila `complimentary` (laskutukseton, platform_adminin asettama ja audit-kirjattu), jota käytetään omassa tenantissa ja tarvittaessa pilottiasiakkailla.
- *Vaihtoehto:* oma yritys maksaa Stripen kautta kuten muut.

**P9. Hinnoittelu ja käyttöönotto.** *Kutsupohjainen beta päätetty (2026-11-06); hinta ja tuotteen nimi vahvistetaan vaiheessa 5.*
- Seat-hinta (Yearclockissa EUR 30 / seat / kk + ALV, ei trialia) ja Stripe-tuotteen nimi ("Shadow seat") on vahvistettava.
- *Suositus:* käyttöönotto kutsupohjaisena betana kuten Yearclockissa, eli Authentikissa `AUTHENTIK_ENROLLMENT_OPEN=false` ja kutsut käsin.

**P10. Migraatiotyökalu ja toimitusketju.**
- *Suositus:* säilytetään Shadowin SQL-migraatiorunner (ADR-002), ja Yearclockin Alembic-migraatioiden SQL käännetään käsin parillisiksi `NNN_*.sql`/`.down.sql`-tiedostoiksi.
- **Päätetty (2026-11-06):** imaget rakennetaan GitHub Actionsissa GHCR:ään Yearclockin tapaan (Yearclock ADR-0035). `main` on ainoa GitHubiin pushattava haara. Pushi `main`iin ajaa vain CI:n; backend- ja frontend-imaget rakennetaan **vain `v*`-tageista**, jotka ihminen luo ja pushaa (päätetty 2026-11-06). Tämä korvaa Shadowin Git-vapaan lähdetoimituksen ja palvelimella rakentamisen (ADR-013/059H), joten se vaatii oman ADR:n (TASK-086D).

**P11. Ajastukset.**
- *Suositus:* backupit ja levyvahti systemd-ajastimilla kuten Yearclockissa. Ofelia ja `backup-runner` poistetaan. Viikoittainen Docker-siivous siirtyy systemd-ajastimeksi.

---

## 3. Arkkitehtuurin kohdetila

```text
Caddy (shadow.lupaus.eu)       → frontend (SPA: /, /tenants/:tenantId/…, /platform/*, /legal/:key)
                               → backend  (/api/*, /.well-known/oauth-*)
Caddy (id.shadow.lupaus.eu)    → authentik-server
backend  ── PostgreSQL "shadow"     (SET LOCAL ROLE shadow_app + RLS-GUC:t)
authentik-server/worker ── PostgreSQL "authentik" (sama postgres-kontti)
worker             (background_jobs, outbox, sähköposti, legal-ilmoitukset, purge, tukipääsyn vanheneminen)
prediction-worker  (ennallaan, asettaa tenanttikontekstin)
migration          (one-shot) ; authentik-config-init (blueprintit)
host: systemd shadow-backup.timer (restic → Scaleway S3), shadow-disk-check.timer
MCP-client ── OAuth (Authentik-provider "Shadow MCP") ── token → backend /api/mcp (JWT-verifiointi JWKS:llä)
ulkoiset: Stripe (Checkout, Portal, webhook), Scaleway TEM (sähköposti, myös Authentikin SMTP)
```

Tietomallin ydin:

- `users` säilyy tilitaulukkona, koska `created_by`/`modified_by`-viittaukset osoittavat siihen. Siihen lisätään `account_class` (`customer`/`platform`) ja `locale`, ja `role` poistetaan siirron jälkeen.
- Uudet taulut: `tenants` (lifecycle- ja Stripe-sarakkeet Yearclockin `organizations`-taulun mukaan), `tenant_memberships` (`owner`/`admin`/`member`, `version`), `tenant_invitations`, `platform_roles`, `platform_enrollments`, `audit_events`, `background_jobs`, `outbox_messages`, `notifications`, `stripe_webhook_events`, `tenant_seat_changes`, `tenant_seat_previews`, `legal_acceptances`, `legal_announcements` ja `support_access_requests`.
- `tenant_id NOT NULL` lisätään tauluihin `organisations`, `customers`, `contacts`, `customer_addresses`, `prediction_versions`, `prediction_requests`, `ai_change_sets`. `mcp_oauth_*`-taulut poistetaan (vaihe 3b). `metamodels`-taulussa `tenant_id` sallii NULLin, joka tarkoittaa globaalia oletusmetamallia.
- Skenaarion kautta rajautuvat taulut saavat RLS-politiikan join-ehdolla tai denormalisoidun `tenant_id`:n. Valinta tehdään TASK-080A:n suunnittelussa, ja suositus on denormalisoitu sarake ja yksinkertaiset politiikat.
- Organisation-avain on uniikki tenantin sisällä, ei enää globaalisti.

---

## 4. Vaiheet ja tehtävät

### 4.0 Vaiheiden speksaus `.scratch/`-hakemistoon

Alla olevat `TASK-0NN`-tunnisteet ovat tämän suunnitelman sisäisiä työnimiä. Niitä ei luoda `tasks/`-tiedostoiksi (vanha käytäntö on arkistoitu hakemistoon `docs/archive/tasks/`). Jokainen vaihe speksataan omaksi featurekseen tai tekniseksi työkseen, ja vaiheen tehtävistä tulee sen `issues/NN-*.md`-ticketit. ADR:t (vaihe 0) kirjoitetaan hakemistoon `docs/adr/` numerosta 0016 alkaen sen featuren speksauksen yhteydessä, joka päätöksen tarvitsee.

| Vaihe | Ehdotettu hakemisto | Laji |
|---|---|---|
| 0 Päätökset ja ADR:t | ADR:t syntyvät vaiheiden speksauksessa; yhteiset P1–P3 tenanttien PRD:ssä | – |
| 1 Backend-perusta | `.scratch/tech-platform-foundation/` | tekninen |
| 2 Authentik ja Entran poisto (PRD, design ja ticketit 01–05 kirjoitettu) | `.scratch/authentik-sign-in/` | feature |
| 3 Tenanttius | `.scratch/tenants-and-roles/` | feature (domain model) |
| 3b MCP Authentikin OAuthiin | `.scratch/mcp-authentik-oauth/` | feature |
| 4 Legal-dokumentit | `.scratch/legal-documents/` | feature |
| 5 Stripe-laskutus | `.scratch/subscription-billing/` | feature (domain model) |
| 6 Jäsenet ja kutsut | `.scratch/people-and-invitations/` | feature |
| 7 Platform-konsoli ja tukipääsy | `.scratch/platform-console/` | feature |
| 8 Elinkaari ja GDPR | `.scratch/tenant-lifecycle/` | feature |
| 9 Tuotanto ja restic-backupit | `.scratch/tech-saas-production-runtime/` | tekninen |
| 10 Cutover | `.scratch/tech-saas-cutover/` | tekninen |


Numerointi jatkaa nykyisestä (viimeisin TASK-076, ADR-015, migraatio 020). Jokainen tehtävä on mitoitettu yhden agentin itsenäisesti toteutettavaksi yhteen PR:ään, ja tavoitekoko on alle 500 riviä reviewattavaa muutosta. Yearclockista suoraan kopioitu koodi on merkitty *(kopio)*. Sellaisen PR:n katselmointi rajautuu nimimuutoksiin ja sovituskohtiin, joten se voi olla suurempi.

Jokainen ticket noudattaa `docs/agents/definition-of-done.md`:n sääntöjä:
- testit tai perustelu niiden puuttumiselle
- AI review kirjataan ticketin `## AI review` -osioon
- uudet env-muuttujat tiedostoihin `.env.example` ja production-env-pohjaan
- kaaviot ja `docs/data/` päivitetään, kun muutos niitä koskee

### Vaihe 0 – Päätökset ja arkkitehtuuri (vain dokumentteja)

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-077A** SaaS-tenanttiuden ADR | ADR-016: tenant-käsite (P1), memberships ja roolit (P3), `customer`/`platform`-tililuokat, eksplisiittinen tenant-route, RLS (P2). Korvaa ADR-004:n "Initial Authorization" -osion. Uudet `docs/domains/TENANTS.md` ja `docs/concepts/TENANT.md`, `MEMBERSHIP.md` ja `PLATFORM_ACCOUNT.md`. Päivitetään `ORGANISATION.md` (ei enää "tenant-like"), `USER.md`, `DATA-MODEL.md`, `ARCHITECTURE.md` ja C4-kaaviot. | – |
| **TASK-077B** Authentik- ja MCP-ADR | *Kirjoitettu 2026-11-06 (`proposed`): ADR-017 (Authentik) ja MCP-päätös omana ADR:nään numerolla 0023, koska 018–022 on varattu muille. Alkuperäinen kuvaus:* ADR-017: oma Authentik (P5), blueprintit, pakollinen MFA, kutsupohjainen enrollment (P9), Entran poisto. Korvaa ADR-013:n Entra-osat, ja ADR-006 merkitään historialliseksi. Kirjaa P4:n MCP-ratkaisun omaksi ADR:kseen, joka korvaa ADR-015:n OAuth-palvelinosan (MCP-palvelin, työkalut ja change setit säilyvät). Päivittää `sequence-oidc-login.puml`- ja `component-authentication-topology.puml`-kaaviot. | – |
| **TASK-077C** Laskutus- ja elinkaari-ADR | ADR-018: Stripe ja seatit (Yearclock ADR-0009/0032), grace/read-only/canceled, `complimentary` (P8), sisällön purge vs. taloudellinen säilytys (ADR-0008). `docs/domains/BILLING.md` muuttuu kandidaatista omistetuksi domainiksi. | 077A |
| **TASK-077D** Alustapalveluiden ADR:t | ADR-019: worker ja outbox, Scaleway TEM, in-app-ilmoitukset, audit log. ADR-020: legal-dokumentit (Yearclock ADR-0041). ADR-021: restic → Scaleway S3, systemd-ajastimet, Ofelian poisto (P11), joka korvaa ADR-013:n backup-osat. ADR-022: frontend-riippuvuudet ja i18n (P6, P7) sekä niiden hyväksyntä. | 077A |

**Hyväksyntäportti:** ihminen hyväksyy ADR:t 016–022 ennen vaihetta 1.

### Vaihe 1 – Backend-perusta

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-078A** Pyyntökonteksti ja sovellusrooli | *(kopio)* `transaction_session`, `RequestContext`, `apply_request_context` ja `elevated` Yearclockin `database.py`:stä sovitettuna Shadowin `get_db_session`-malliin. Migraatio 021 luo `shadow_app`-roolin (NOLOGIN NOBYPASSRLS) ja grantit, mutta ei vielä politiikoita. Olemassa olevat reitit toimivat ennallaan. | 077A |
| **TASK-078B** Audit log | *(kopio)* `audit_events` (append-only-trigger), `audit.py` ja `audit_source()` (MCP-provenance). Migraatio 022. | 078A |
| **TASK-078C** Taustatyöt | *(kopio)* `work_queue.py`, `worker.py`, `jobs.py`, `background_jobs` ja `outbox_messages`. Migraatio 023. Uusi compose-palvelu `worker` sekä dev- että production-composeen. `prediction-worker` säilyy erillisenä. | 078A |
| **TASK-078D** Sähköposti ja ilmoitukset | *(kopio)* `email_delivery.py` (Scaleway TEM), `notification_email.py`, `notifications.py` ja `notifications`-taulu (migraatio 024) sekä ilmoitusten luku-API. Kehitysympäristöön paikallinen sähköpostin kaappaus (lokiin tai mailpit, päätetään taskissa). | 078C |

### Vaihe 2 – Authentik ja Entran poisto

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-079A** Paikallinen Authentik *(ticket 01)* | *(kopio)* Compose-palvelut `authentik-db-init`, `authentik-server`, `authentik-worker` ja `authentik-config-init`, `authentik/configure.sh` sekä blueprintit `shadow-identity-flows`, `shadow-application` ja `shadow-brand` (+ css). Paikallinen Caddy saa identity-hostin (esim. `https://id.app.localhost`). Lisäksi `docs/runbooks/authentik-local.md` ja vanhojen `authentik_*`-volyymien siivous. | 077B |
| **TASK-079A2** Authentikin MCP-provider *(ticket 02; siirretty 080H:sta)* | Blueprint `shadow-mcp-application.yaml` (luottamuksellinen client, tiukat redirect-URI:t claude.ai/claude.com, loopback-regex Claude Codelle, eksplisiittinen consent, `hashed_user_id`), tarkistusskripti ja oikean MCP-clientin kirjautumisen todentaminen. Ei Shadow-koodia. | 079A, 077B |
| **TASK-079B** OIDC Authentikiin *(ticket 03)* | `validate_auth_configuration` yleistetään: Entra-host- ja polkusäännöt poistetaan, ja tilalle tulevat Yearclockin `OIDC_INTERNAL_BASE_URL`-discovery, `per_provider`-issuer ja verified-email-attribuutti. Logout käyttää `id_token_hint`iä (migraatio: sarake sessioon). Shadowin istunto- ja CSRF-ydin säilyy, koska se on Yearclockia tiukempi (`__Host-`, SameSite=strict, `X-CSRF-Token`). | 079A |
| **TASK-079C** Tilit ja tililuokat *(ticket 04, supistettu: tilin luonti loginissa siirtyy 080B:hen, koska ennen tenantteja jokainen tili näkisi kaiken datan)* | `users` saa sarakkeet `account_class` ja `locale` (migraatio). Ensimmäinen vahvistettu login luo `customer`-tilin Yearclockin `complete_login`-mallin mukaan. Olemassa olevan käyttäjän guarded email-linkitys säilyy cutoveria varten. `audience=customer|platform` login-parametri ja tililuokkaan sidotut session-dependencyt. | 079B, 078A |
| **TASK-079D** Entra-jäänteiden poisto *(ticket 05)* | Poistetaan `scripts/setup-local-entra.sh`, `verify-local-direct-entra-config.sh`, `provision_local_admin.py`, Entra-kehotteet `bootstrap_admin.py`:stä, `session_state`-redaktio, Entra-tekstit frontendistä ja dokumenteista (`PRODUCTION-RUNBOOK.md` §2.7, `LOCAL-DEVELOPMENT.md`, QA-checklistit) sekä Entra-testit. Dev-käyttäjät tulevat Authentik-blueprintista. | 079C |

### Vaihe 3 – Tenanttius

> **Toteutus:** vaihe 3 on speksattu ominaisuutena `.scratch/tenants-and-roles/` (PRD, domain-model, technical-design, ticketit 01–11). Tehtävät 080A–080G jaetaan tickeiksi näin: 080A → 01–02, 080B → 03, 080C → 04, 080D → 05, 080E → 06, 080F → 08–09, 080G → 10–11. MCP:n väliaikainen tenantti (07) edeltää vaihetta 3b.

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-080A** Tenant-skeema ja backfill | Migraatio: `tenants`, `tenant_memberships` ja `tenant_id`-sarakkeet (kohta 3). Backfill luo yhden tenantin nykyiselle yritykselle (`complimentary`) ja siirtää kaiken datan siihen. `users.role` muunnetaan jäsenyydeksi: `admin` → `admin`, `consultant` → `member`, ja ensimmäinen bootstrap-admin → `owner`. Uniikkiusindeksit muuttuvat tenanttikohtaisiksi. Data-dokumentit ja DB-kaavio päivitetään. | 078A, 077A |
| **TASK-080B** Tenantin pääsynhallinta | *(kopio)* `access.py`:n Owner/Admin-tarkistukset, `_member_session`/`_manager_session`-malli, dependencyt `require_tenant_member/admin/owner` ja `GET /api/v1/tenants` (omat tenantit). `require_admin`/`require_business_admin` korvataan. | 080A, 079C |
| **TASK-080C** Reitit: organisations ja customers | `organisations`, `customers`, `contacts` ja `addresses` siirtyvät polkuun `/api/v1/tenants/{tenant_id}/…`, ja avaimet resolvoidaan tenantin sisällä. Testit todistavat, ettei toisen tenantin data näy (404). | 080B |
| **TASK-080D** Reitit: scenarios, org states, twin structure | Kuten C mallinnusreiteille ja metamalleille (globaali oletusmetamalli luettavissa kaikille). | 080B |
| **TASK-080E** Reitit: predictions ja change setit | Kuten C. `prediction-worker` asettaa tenanttikontekstin (`worker_scope`). | 080B |
| **TASK-080F** Frontend-tenanttikonteksti | Reitit muuttuvat muotoon `/tenants/:tenantId/shadow/:orgId/*`, ja lisätään tenantin valitsin, API-clientin polut ja roolipohjainen näkyvyys (`role === "admin"` → jäsenyysrooli). | 080C–E |
| **TASK-080G** RLS-politiikat | Kaikille tenanttitauluille `ENABLE`/`FORCE ROW LEVEL SECURITY` ja politiikat GUC:ien kautta (Yearclockin `0004`/`0025`-malli). Integraatiotestit todistavat eristyksen tietokantatasolla. | 080C–E |

### Vaihe 3b – MCP Authentikin OAuthiin (Yearclockin malli)

MCP-palvelin (`/api/mcp`, fastmcp), työkalut, promptit, skillit sekä change setien staging ja review (web- ja MCP-kanava) säilyvät. Vain tunnistautuminen vaihtuu: Authentik myöntää tokenit, ja Shadow ainoastaan verifioi ne. Oikeudet tulevat jäsenyysroolista ja tenantin kytkimistä, eivät OAuth-scopeista.

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-080H** Authentikin MCP-provider | *Blueprint ja client-tarkistus tehdään jo vaiheessa 2 (079A2); tässä jää vain env-muuttujien ja `MCP_OIDC_ISSUER`in käyttöönotto ja se, että varasuunnitelma ei ole tarpeen. Alkuperäinen kuvaus:* *(kopio)* Blueprint `shadow-mcp-application.yaml`: luottamuksellinen client, PKCE, authorization code + refresh token, eksplisiittinen consent, scopet `openid profile offline_access`, `hashed_user_id`, `per_provider`-issuer ja tiukat redirect-URI:t (claude.ai- ja claude.com-callbackit sekä loopback-kuvio paikallisille clienteille, kuten Claude Codelle). Env: `MCP_OIDC_ISSUER`, `MCP_OIDC_CLIENT_ID`, `MCP_OIDC_CLIENT_SECRET`, `MCP_RESOURCE_URL`. Ennen toteutusta varmistetaan, että Claude Code tukee esirekisteröityä client id:tä ja secretiä; jos ei, asiasta tehdään erillinen päätös (julkinen client tai OAuth-fasadi). | 079A, 077B |
| **TASK-080I** Token-verifiointi ja identiteetti | *(kopio)* Yearclockin `verifier.py` (paikallinen JWT-verifiointi MCP-providerin JWKS:llä, `iss` = `MCP_OIDC_ISSUER`, `aud` = `MCP_OIDC_CLIENT_ID`) fastmcp:n token-verifioijaksi `McpBearerAuth`:n tilalle sekä `identity.py` (MCP-issuerin `sub` → olemassa oleva `customer`-tili kanonisen `OIDC_ISSUER`in alla, tiliä ei koskaan luoda). Protected-resource-metadata nimeää Authentik-providerin auktorisointipalvelimeksi; Caddy reitittää `/.well-known/oauth-protected-resource*`. Testit: MCP-token ja web-login samalle käyttäjälle johtavat samaan tiliin, web-tokenia tai tuntematonta issueria ei hyväksytä. | 080H, 079C |
| **TASK-080J** Tenantti ja oikeudet MCP:ssä | *(kopio)* Yearclockin `gate.py`: tenanttikohtaiset `mcp_enabled` ja `mcp_platform_blocked` (migraatio). Työkalut saavat eksplisiittisen tenant-argumentin (Yearclockin explicit Organization -malli), ja jäsenyys tarkistetaan joka kutsulla. `requires_scope`/`ROLE_SCOPES` korvataan jäsenyysroolin tarkistuksella: kirjoitustyökalut ja `apply_change_set`/`reject_change_set` vaativat roolin, jolle P3 sallii mallien muokkauksen. MCP-provenanssi kirjataan `audit_source()`:lla. | 080I, 080G, 078B |
| **TASK-080K** Oman OAuth-palvelimen purku | Poistetaan `api/v1/mcp_oauth/` (discovery, `/api/oauth/register`, `authorize`, `token`, `revoke`, consent- ja connections-API), `MCP_OAUTH_*`-asetukset, redirect-allowlist ja rate limitit. Migraatio pudottaa taulut `mcp_oauth_clients`, `mcp_oauth_grants`, `mcp_oauth_authorization_requests` ja `mcp_oauth_tokens` (down luo ne tyhjinä). Frontendistä poistuvat `/ai/authorize`-consent-sivu, `ConnectionsList` ja adminin "Revoke AI connections". Testit ja `sequence-mcp-oauth-tokens.puml` korvataan uudella sekvenssillä. | 080J |
| **TASK-080L** Yhteysohjeet ja plugin | *(kopio)* Owner/Admin-API connection detailsille ja secretin näyttämiselle sekä MCP-kytkimelle (Yearclockin `mcp_routes.py`). Metrics-välilehden AI-paneelin Connect-ohjeet päivitetään (client id ja secret claude.ai:n custom connectoriin ja Claude Codeen); paneeli siirtyy myöhemmin hallinnan Agents-sivulle (083C). Plugin `.mcp.json` ja versio, skillit, README, `docs/architecture/domains/AI.md`, LikeC4-malli, runbook (`docs/runbooks/mcp-interface.md` Yearclockin mallilla) ja MCP-QA-checklist päivitetään. | 080K |

### Vaihe 4 – Legal-dokumentit

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-081A** Legal-kirjasto ja julkiset reitit | *(kopio)* `backend/legal/<key>.<fi|en>.md` (terms, dpa, privacy, storage, subprocessors, switching, security, provider) Shadowille sovitettuina draft-tiloina, `LegalLibrary` (käynnistyksen validointi) ja `GET /api/v1/legal/documents[/{key}]`. Env: `LEGAL_SHOW_DRAFTS`, `LEGAL_CONTACT_EMAIL`. Lisäksi `docs/legal/` (README, counsel-checklist). | 077D |
| **TASK-081B** Hyväksynnät ja ilmoitukset | *(kopio)* `legal_acceptances` ja `legal_announcements` (migraatio), `legal_acceptance.py`, tenantin legal-reitit ja päivittäinen `legal.announce`-job, joka lähettää Ownerille in-app- ja sähköposti-ilmoituksen. | 081A, 078D, 080B |
| **TASK-081C** Legal-frontend | *(kopio)* `/legal/:key`-sivut, footer-linkki ja Ownerin hyväksyntäsivu. Riippuvuudet `react-markdown` ja `remark-gfm` (P6). Tämä on ensimmäinen task, joka tuo Yearclockin `ui/`-kirjaston, `theme.css`:n, Tailwindin ja i18n:n. | 081B, 077D |

### Vaihe 5 – Stripe-laskutus

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-082A** Stripe-client ja webhook | *(kopio)* `billing.py` (`StripeBilling`-protokolla, `StripeBillingClient`, `StripeSignatureVerifier`), `stripe_webhook_events`, tenantin laskutussarakkeet (migraatio), webhook-reitti, idempotenssi ja CSRF-poikkeus webhookille. Env: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_MONTHLY_SEAT_PRICE_ID`. | 080A, 078B |
| **TASK-082B** Tenantin rekisteröinti ja aktivointi | *(kopio)* `tenant-signups` (`organization_activation.py`): pending-tenantti, legal-hyväksynnät, Checkout-URL, aktivointi `checkout.session.completed`-tapahtumasta ja 24 h:n vanheneminen. Frontendin aktivointisivu. | 082A, 081B |
| **TASK-082C** Seat-kapasiteetti | *(kopio)* `seat_capacity.py` ja reitit (preview, korotus, ajastettu lasku, `seat_version`), taulut `tenant_seat_changes`/`previews`. | 082A |
| **TASK-082D** Tilauksen pääsytila | *(kopio)* `subscription_access.py` (grace 7 pv → `read_only`, `canceled`, `complimentary`). `require_tenant_mutation_access` lisätään **jokaiseen** Shadowin kirjoittavaan reittiin, MCP:n kirjoitustyökaluihin ja change-setin applyyn. Audit ja ilmoitukset Ownereille/Admineille. | 082A, 080C–E |
| **TASK-082E** Ownerin laskutussivu | *(kopio)* `subscription_routes.py`, `billing_routes.py` ja `billing_contact.py` (next charge, invoices, cancel/undo, contact, resubscribe, portal) sekä frontendin `BillingPage` ja `SubscriptionNotice`. | 082C, 082D, 081C |
| **TASK-082F** Stripe-runbook | `docs/runbooks/stripe-production.md` sovitettuna: tuote, vero, portaalin asetukset (quantities pois), Smart Retries, webhook-tapahtumat ja testitila. | 082E |

### Vaihe 6 – Jäsenet, kutsut ja tenantin hallinta

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-083A** Kutsut | *(kopio)* `tenant_invitations` (+ ryhmäkutsut tarvittaessa), `invitations.py` (7 pv, seat-varaus, sähköposti outboxin kautta, sähköpostin täsmäys hyväksyttäessä) ja reitit `/api/v1/tenants/{id}/invitations` sekä `/api/v1/invitations/accept`. | 082C, 078D |
| **TASK-083B** Jäsenyyksien hallinta | *(kopio)* Jäsenlista, roolin muutos, poisto, leave (viimeinen Owner suojattu) ja omistajuuden siirto (`transfer-ownership`, `expected_version`). Audit-tapahtumat. Vanha globaali Users-API poistuu (sessioiden revoke säilyy Admin-toimintona). | 083A |
| **TASK-083C** Tenantin hallintanäkymä | *(kopio)* Hallintaosio `/tenants/:tenantId/admin/*`: People (+ bulk-kutsut), Activity (audit), Agents (MCP), Billing, Legal ja Settings, navigaatio Yearclockin `ADMIN_SECTIONS`-mallilla, kutsun hyväksyntäsivu `/invitations/:token`. Nykyinen `UsersTab` poistetaan. | 083B, 082E |

### Vaihe 7 – Platform-konsoli

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-084A** Platform-tilit | *(kopio)* `platform_roles` (`platform_admin`, `support_agent`), `platform_enrollments`, CLI `python -m app.platform_admin enroll|grant`, login `audience=platform` ja asiakastilien torjunta platform-sessiossa. Korvaa `bootstrap_admin.py`:n tyhjän users-taulun bootstrapin. | 079C, 078B |
| **TASK-084B** Platform-API ja monitorointi | *(kopio)* `/api/v1/platform`: session, logout, tenants (elinkaari, tilaus, seatit, jäsen- ja mallimäärät), MCP-block, `complimentary`-tilan asetus (P8), health, jobs ja replay sekä `GET /api/v1/monitoring/health` (`MONITORING_TOKEN`). | 084A, 082D |
| **TASK-084C** Platform-konsolin frontend | *(kopio)* `/platform/*` (`PlatformConsole`: health, tenants, jobs, support) ja platform-client. Caddy reitittää `/platform*` SPA:lle. | 084B, 081C |
| **TASK-084D** Tukipääsy | *(kopio)* `support_access_requests`, asiakkaan hyväksyntä/hylkäys/peruutus (Owner/Admin), enintään 24 h, RESTRICTIVE RLS -politiikat (`app_support_grant_allows`), workerin vanhennus sekä asiakkaan `SupportPage` ja platformin support-sivu. Shadowin sisältöreitit tukihenkilölle: ensin vain luku mallinnusdataan (Organisation → scenario → graph/timeseries/events). | 084C, 080G |

### Vaihe 8 – Tenantin elinkaari ja GDPR

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-085A** Tenantin poisto ja purge | *(kopio)* `/api/v1/tenants/{id}/deletion` (GET/POST/restore). Workerin `purge_tenant` ajetaan `TENANT_DELETION_RETENTION_DAYS` (30) jälkeen: sisältö poistetaan, mutta tenant-rivi, Stripe-tunnisteet, audit-toiminnot ja `legal_acceptances` säilyvät. | 082D, 078C |
| **TASK-085B** Ownerin vienti | *(kopio, sovitettu)* `GET /api/v1/tenants/{id}/export`: JSON-vienti tenantin malleista ja asiakkaista. | 080C–E |
| **TASK-085C** GDPR-dokumentit | `docs/gdpr/` (README ja säilytystaulukko, records-of-processing, breach-procedure, DPIA, NIS2/AI, staff-access-policy) ja `docs/runbooks/personal-data-request.md` Shadowille sovitettuina. | 085A |

### Vaihe 9 – Tuotantoympäristö ja varmuuskopiot

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-086A** Production compose ja edge | Authentik-palvelut ja `worker` lisätään `docker-compose.production.yml`:ään ADR-013:n hardening-tasolla, edge-Caddyyn identity-host ja CSP. Production env -pohja saa OIDC-, Authentik-, Stripe-, SCW-, legal- ja monitoring-muuttujat. Päivitetään `audit-host`, `check-host`, `verify-runtime-hardening` ja CI:n production-verifioinnit. | 079D, 082A, 078D |
| **TASK-086B** restic → Scaleway S3 | *(kopio)* `scripts/ops/` (`backup-databases.sh`, `backup-offsite.sh`, `lib-backup-env.sh`, `restic.sh`, `restore-offsite.sh`, `restore-drill.sh`, `notify-email.sh`, `check-disk.sh`) ja systemd-yksiköt `shadow-backup`/`shadow-disk-check`. Backupin kohteena on Shadow- ja Authentik-kanta + `production.env`. Retentio `--keep-hourly 24 --keep-daily 30 --keep-monthly 6` ja `restic check`. Poistetaan GPG-`backup.sh`, `backup-runner`, Ofelian backup-job ja `/opt/postgres-backups`-politiikka, ja Docker-siivous siirtyy systemd-ajastimeksi (P11). `deploy/Makefile`-targetit. | 086A, 077D |
| **TASK-086D** Imaget GHCR:ään | *(kopio)* Yearclockin `.github/workflows/images.yml` sovitettuna niin, että vain `v*`-tagin pushi rakentaa `ghcr.io/lupaus-eu/shadow-{backend,frontend}`-imaget (`linux/amd64`). Palvelin kirjautuu `read:packages`-tokenilla, ja `deploy/`-työkalut vaihdetaan vetämään tagattu image (rollback = edellinen tagi). Poistetaan `deploy-production.yml`, `shadow-receive`, `upload-gate`, upload-tili ja build-on-server sekä niiden CI-verifioinnit. ADR korvaa ADR-013:n lähdetoimitusosan. | 077D |
| **TASK-086C** Runbookit | `docs/runbooks/production.md` uudistetaan: Authentik (enrollment, kutsut, upgrade), Stripe, backup/restore-drill, platform-enrollment, monitorointi ja launch-checklist. QA-checklistit (`docs/operations/qa/`) päivitetään. | 086B, 086D, 082F, 084C |

### Vaihe 10 – Tuotannon cutover (vaatii ihmisen hyväksynnän)

| Task | Sisältö | Riippuu |
|---|---|---|
| **TASK-087A** Cutover-harjoitus | Tuotantobackup palautetaan eristettyyn ympäristöön, ja siinä ajetaan migraatiot 021→ ja verifioidaan backfill: yksi tenantti, roolit ja `complimentary`. Lisäksi testataan Authentik-kutsut, ensimmäisen loginin linkitys olemassa olevaan käyttäjään, MCP-uudelleenyhdistys ja restic-palautus. Evidenssi `docs/qa/`-hakemistoon. | kaikki edelliset |
| **TASK-087B** Tuotantojulkaisu | Hyväksytty julkaisu: Scaleway-bucket ja restic-repo, Stripe live -konfiguraatio, DNS identity-hostille, platform-adminin enrollment, käyttäjien kutsut ja Entra-sovellusrekisteröinnin poisto hyväksynnän jälkeen. Release tagataan. | 087A |

---

## 5. Riippuvuuskaavio ja rinnakkaisuus

```text
077A ─┬─ 077B ─ 079A ─ 079B ─ 079C ─ 079D ──────────────────────┐
      ├─ 077C                       │                           │
      ├─ 077D ─ 081A ─┐             └─ 084A ─ 084B ─ 084C ─ 084D │
      └─ 078A ─┬─ 078B ─────────────────┐                        │
               ├─ 078C ─ 078D ─ 081B ─ 081C                      │
               └─ 080A ─ 080B ─ 080C/D/E ─ 080F, 080G ─┐         │
                 079A ─ 080H ─ 080I ─────────── 080J ─ 080K ─ 080L │
                         082A ─ 082B/C/D ─ 082E ─ 082F           │
                         083A ─ 083B ─ 083C                      │
                         085A/B/C                                │
                                    086A ─ 086B ─ 086C ─ 087A ─ 087B
```

Rinnakkain voi edetä:

- vaihe 2 (Authentik) ja vaihe 1 (perusta)
- 080C, 080D ja 080E keskenään
- 081A legal-tekstien sovitus koska tahansa vaiheen 0 jälkeen
- 086B:n skriptien kopiointi heti ADR-021:n jälkeen

Kaksi agenttia ei saa kirjoittaa samoihin tiedostoihin samaan aikaan. Erityisesti `main.py`:n reitinrekisteröinti ja migraationumerot jaetaan järjestyksessä: migraationumero varataan taskia aloitettaessa.

---

## 6. Riskit ja hallinta

| Riski | Hallinta |
|---|---|
| Tenanttivuoto reitin unohtuessa | Eristys sekä backendissä (080B–E) että RLS:llä (080G). Jokaiseen reittitaskiin cross-tenant-testit, ja 080G:hen tietokantatason testit. |
| Tuotantodatan backfill epäonnistuu | Migraatiot ovat palautettavia (down-parit). Cutover-harjoitus tehdään tuotantobackupilla (087A), ja pre-release-backup otetaan ennen julkaisua. |
| Olemassa olevien käyttäjien kirjautuminen katkeaa Entran poistuessa | Guarded email-linkitys säilyy, ja Authentik-kutsut lähetetään ennen cutoveria. Entra-rekisteröinti poistetaan vasta hyväksynnän jälkeen. |
| Kopioitu koodi ajautuu erilleen Yearclockista | Tiedosto- ja funktionimet pidetään samoina, kopiointi on mekaanista (`organization` → `tenant`), ja jokaiseen kopiotaskiin kirjataan Yearclockin lähde-commit. Myöhemmin voidaan harkita yhteistä pakettia. |
| Uudet riippuvuudet (Tailwind, Radix ym.) | Hyväksytetään ADR-022:ssa ennen 081C:tä. |
| Stripe-webhookien järjestys ja idempotenssi | Kopioidaan Yearclockin testattu toteutus ja testit sellaisenaan. |
| Olemassa olevat MCP-yhteydet katkeavat | Kaikki käyttäjät yhdistävät clientinsa uudelleen client id:llä ja secretillä; ohjeet ja tiedote ennen cutoveria (087A testaa uudelleenyhdistyksen). |
| Claude Code ei tue esirekisteröityä OAuth-clientia | Tarkistetaan 080H:n alussa ennen toteutusta. Varasuunnitelma (julkinen client tai OAuth-fasadi) on erillinen päätös, kuten Yearclock ADR-0038:ssa. |
| Yhteinen client secret ei erottele asiakkaita | Hyväksytty kuten Yearclockissa: eristys tulee jäsenyydestä, tenant-argumentista ja tenantin kytkimestä. Secretin vaihto runbookissa. Yksittäisen yhteyden peruminen tapahtuu jäsenyyden poistolla tai Authentik-käyttäjän estolla, ja jo myönnetty token toimii vanhenemiseensa asti. |
| Authentikin päivitykset | Versio pinnataan ja `authentik-upgrade`-runbookia noudatetaan. Backupissa ovat mukana sekä Authentik-kanta että `production.env`. |

---

## 7. Työn ulkopuolella

- Yearclockin data transfer -CSV (ADR-0040) ja beta-kutsukoodit Checkoutissa (ADR-0034 on Yearclockissakin toteuttamatta).
- Organisaatiokohtaiset käyttöoikeudet tenantin sisällä (P3).
- Mallinnusnäkymien kääntäminen suomeksi (P7).
- Hallittu PostgreSQL ja off-host-palautusautomaatio restic-drillin lisäksi.

---

## 8. Seuraava askel

*Tilanne 2026-11-06 (päivitetty):* vaihe 2 on toteutettu (`.scratch/authentik-sign-in/`, tickets 01–05, commitit `8c53b40`–`c798a53`; ADR-017 ja ADR-0023 hyväksytty). Vaihe 1 on toteutettu (`.scratch/tech-platform-foundation/`, commitit `aee6b60`–`efce81c`), ADR-016 hyväksytty, ja vaihe 2 on speksattu (`.scratch/authentik-sign-in/`, ADR-017 ja ADR-0023 `proposed`). Seuraavaksi: hyväksytään ADR-017, ADR-0023 ja vaiheen 2 design, minkä jälkeen ticket 01 voidaan aloittaa.

1. Speksaus alkaa tenanttiudesta (`.scratch/tenants-and-roles/PRD.md`), koska P1–P3 ratkaisevat käsitteet, joihin kaikki muut vaiheet nojaavat. PRD grillataan (`/grilling`) ja käsitteet kirjataan `CONTEXT.md`:hen.
2. Muut vaiheet speksataan riippuvuusjärjestyksessä (kohta 5); jokaisen vaiheen hyväksytystä teknisestä suunnitelmasta syntyvät sen ticketit.
3. Toteutus alkaa vasta, kun vaiheen PRD ja tekninen suunnitelma ovat `accepted`.
