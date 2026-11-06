# Yearclock × eTWIN: täydentävyys- ja integraatiospeksi

**Tila:** Luonnos 0.2 – ensimmäinen ajattelu; kohdan 8.2 päätökset on tehnyt omistaja, muu on ehdotusta
**Päiväys:** 2026-10-20
**Tarkoitus:** Yhteinen pohja, jonka päälle molempien sovellusten kehitystä voidaan suunnitella rinnakkain.

> **Lähteet ja varauma.** Yearclock-puoli perustuu `CONTEXT.md`:hen ja ADR:iin (0003, 0027).
> eTWIN-puoli perustuu repon `etwin/docs` -dokumentaatioon (PROJECT_DOCUMENTATION, USER_MANUAL,
> DATABASE_DOCUMENTATION, DB_APP_V2_SCHEMA, EVENT_IMPACT_RULE_SCOPE_V2, EXTERNAL_API_DOCUMENTATION,
> usecases-indeksi) sekä vanhaan `EnterpriseTwin/ontology/ontology.ttl`-prototyyppiin.
> **ArchiMate/EDGY-kytkentä on tässä dokumentissa minun tulkintani:** eTWINin dokumentaatiossa
> ei mainita ArchiMatea tai EDGYä, joten kohdan 3 vastaavuustaulukko on ehdotus, ei kuvaus nykytilasta.
> Merkinnät **[VAHVISTA]** kysyvät omistajan näkemystä.
>
> **Muutokset versiossa 0.2** (omistajan palautteen jälkeen): Event-käsite tarkennettu (ajallinen sijainti
> vs. status, kohdat 2.3 ja 5.1); eTWINin käsitemalli supistettu alkuperäisiin lukittuihin käsitteisiin
> ja ontologia jätetty pois (kohta 3); todellisuuden ja simulaation ero tehty näkyväksi (3.2);
> yhteyskohdat 5.1–5.4, 5.6 ja taulukko 7 päivitetty vastaamaan.

---

## 1. Tiivistelmä

| | Yearclock | eTWIN |
|---|---|---|
| Kysymys | *Mitä organisaatio aikoo tehdä ja milloin?* | *Miten organisaatio toimii ja mitä tapahtuu, jos jotain muuttuu?* |
| Aikasuunta | Tuleva, ennakoitava, toistuva | Nykytila (baseline), historia ja simuloitu tulevaisuus |
| Ydinobjekti | Event (päivätty suunnitelmamerkintä) | Graafin solmu + metriikka + aikasarja |
| Mittaus | Ei mittaa (ei suoritustilaa) | Metriikat, aikasarjat, ennusteet |
| Arvo | Yhteinen, näkyvä aikataulu | Ymmärrys vaikutussuhteista ja simulointi |
| Käyttäjä | Suunnittelija, tiimi | Analyytikko, johto, arkkitehti |

**Keskeinen väite:** Yearclock on eTWINin puuttuva *tahtotilan aikajana* ja eTWIN on Yearclockin
puuttuva *vaikutusten ja mittareiden malli*. Yearclock kertoo, mitä on tarkoitus tehdä; eTWIN kertoo,
mitä se tekee mitattaville asioille ja mitä sen oltava, jotta tavoite täyttyy. Yhdessä ne sulkevat
silmukan **suunnitelma → toteuma → mittari → poikkeama → uusi suunnitelma**.

Ei-tavoite: yhdistää sovelluksia yhdeksi. Ne pysyvät erillisinä tuotteina, joilla on oma
asiakkuus, laskutus ja tietomalli. Integraatio on **löyhä, tapahtumapohjainen ja molemmin puolin valinnainen**.

---

## 2. Sovellusten nykytila (lyhyesti)

### 2.1 Yearclock
- Organization omistaa Yearclockit; Yearclockissa on Lane-renkaita; Lanessa Eventit; Eventit voivat olla toistuvia (Series → Occurrence).
- Luokittelu: Category, Label. Näkymät: Circle, Timeline, List, Agenda.
- Rajapinnat ulos: Export (xlsx/csv/ics), Organization Export (JSON), Import (xlsx). Ei julkista API-integraatiota.
- **Tietoinen rajaus:** Event ei ole tehtävä; sillä ei ole vastuuhenkilöä, eräpäivää eikä suoritustilaa.
- **Varattu laajennus:** External Signal ja Recommendation on kuvattu mutta rajattu V1:n ulkopuolelle (ADR-0003, ADR-0027). Tämä on luonteva integraatiopaikka.
- Pilvi-SaaS, Organization-tason monivuokraus, seat-pohjainen laskutus, Authentik-kirjautuminen (invitaatiot).

### 2.2 eTWIN
- Tenant = `company`. Graafi (Apache AGE) kuvaa organisaation entiteetit ja suhteet, versioituna ontologialla (ontology_version, entity_type, relationship_type, constraints). Baseline = nykytila; skenaariot haarautuvat siitä.
- Metriikat: `metric` (input/derived), `metric_calculation`, `metric_dependency`, `metric_assignment`; aikasarjat `timeseries` (actual) ja `scenario_input`.
- Tapahtumat: `event`, `event_category_impact` (kategoria → vaikutus metriikkaan), `event_inbox`, `event_analysis` (AI-analyysi).
- Ennuste: `forecast_run`, `scenario_graph_phase`; actual-priority-politiikka.
- AI: analyysi, toimenpide-ehdotukset (Action Recommendations → Actions, Jira CSV), guardrailit.
- Ulkoinen ingest: `POST /external/v1/events/upsert` ja `/timeseries/upsert` (API key + HMAC + nonce).
- Authentik OIDC, tenant-roolit owner/member omassa DB:ssä, erillinen admin-web.
- Tunnettu avoin kohta: event impact -säännöt ovat vielä globaaleja (EVENT_IMPACT_RULE_SCOPE_V2).

### 2.3 Havainto: Event on keskeinen käsite kummassakin, mutta niiden status on eri

Molemmissa Event kuvaa jotain tiettynä ajanhetkenä tapahtuvaa toimintaa. Kummassakin Event voi olla
menneisyydessä tai tulevaisuudessa, joten *aika ei erota* käsitteitä. Ne erottaa se, **mitä
tapahtumasta väitetään**:

| | Yearclock Event | eTWIN Event (todellisuus) | eTWIN Scenario Event (simulaatio) |
|---|---|---|---|
| Väite | *Aiottu* toiminta (suunnitelma) | *Fakta*: tapahtui tai tapahtuu (organisaatiomuutos, ulkoinen isku) | *Oletus*: mitä jos tämä tapahtuisi |
| Tulevaisuudessa | Tavallisinta | Sallittu: tulee voimaan, kun reaaliaika saavuttaa päivän | Tavallisinta |
| Menneisyydessä | Muuttuu historiatiedoksi | Toteutunut fakta | Vain simulaation oma aikajana |
| Tila | Ei suoritustilaa (ADR-0027) | Ei tallennettua tilaa; "voimassa" johdetaan päivästä | Kuuluu aina yhteen skenaarioon |
| Vaikutus | Ei mallinneta | Muuttaa mallia (sisäinen) tai kuvaa ulkoisen tapahtuman | Muuttaa vain skenaariota |

Periaate: **ajallinen sijainti (mennyt/tuleva) johdetaan päivästä eikä sitä tallenneta; väite
(suunniteltu / fakta / oletus) on käsitteen luonne, ei tallennettu tilakone.** Siksi emme rakenna
Eventille yhteistä tilakonetta. Kohdan 5.1 säännöt kertovat, miten käsitteet linkitetään.

---

## 3. eTWINin käsitemalli (ehdotus)

Yearclockilla on `CONTEXT.md`; eTWINillä ei ole vastaavaa. Tämä on ehdotus sellaiseksi.
Se kuvaa **alkuperäiset, lukitut käsitteet**: ne, joilla eTWIN tehtiin ennen kuin ontologian
rakentaminen lisättiin laajennukseksi.

### 3.1 Rajaus

**Mukana:** Company, Team, Service, Goal, KPI, KPI Timeseries, Event, Scenario, Scenario Event,
Simulation Run, Projected KPI Series, Action.

**Tarkoituksella pois ensimmäisestä käsitemallista:**
- **Ontologia** (Ontology, Entity/Relationship Type, Property Definition, Constraint, Preflight). Se on
  laajennusmekanismi: asiakas voi määritellä omia tyyppejä. Se lisää vaikeutta eikä kuulu perusmalliin.
  Perusmallin tyypit (Team, Service, Goal, KPI...) ovat lukittuja. Ontologia kirjataan laajennukseksi (3.5).
- Tekninen ja kaupallinen runko: Tenant Member, kutsut, laskutus, token usage, API-avaimet.
- Laskennan ja tekoälyn apukäsitteet: Impact Rule, Event Analysis, Analysis, Guardrail, Parameters,
  Scenario Graph Phase, Metric Assignment. Ne ovat tapoja toteuttaa laskenta, eivät perusmallin käsitteitä.
  Event Impact Rule -kysymys (globaali vs. tenant-kohtainen) pysyy kuitenkin avoimena eTWIN-puolella.

### 3.2 Kaksi maailmaa: todellisuus ja simulaatio

Tämä on mallin tärkein rakenne.

| | **Todellisuus** (baseline) | **Simulaatio** |
|---|---|---|
| Sisältö | Company, Team, Service, Goal, KPI, KPI Timeseries, Event | Scenario, Scenario Event, Simulation Run, Projected KPI Series, Action |
| Merkitys | Mitä organisaatiosta tiedetään ja mitä on tapahtunut | Mitä voisi tapahtua, jos... |
| Muuttuu | Kun todellisuus muuttuu | Kun käyttäjä leikkii vaihtoehdoilla |
| Raja | — | **Skenaarion tapahtumat eivät koskaan valu skenaarion ulkopuolelle.** Jokainen ajo on erillinen. Skenaario alkaa kopiona todellisuudesta. |

Siirto simulaatiosta todellisuuteen on aina **käyttäjän manuaalinen kopiointi**: käyttäjä valitsee
skenaarion Eventin ja kopioi sen todellisuuden Eventiksi. Mikään ei siirry automaattisesti ja
skenaario ei kirjoita todellisuuteen.

### 3.3 Sanasto

**Company**
Asiakasyritys, jonka malli ja data eTWINissä on. Kaikki data on yrityskohtaista.
_Avoid_: Tenant (tekninen termi), Organisation

**Team**
Organisaation ihmisryhmä, joka tekee työtä ja tavoittelee tavoitteita.

**Service**
Yrityksen tuottama palvelu, jolle voi asettaa mittareita.

**Goal**
Tavoite, jota Team tavoittelee ja jonka toteutumista KPI mittaa.

**KPI**
Mittari, joka kertoo, miten Service tai Team onnistuu, ja jolla Goalin toteutumista seurataan. Sillä on yksikkö; se voi olla syötetty tai johdettu toisista KPI:stä.
_Avoid_: Metric (tekninen termi taulussa)

**KPI Timeseries**
KPI:n varsinaiset, toteutuneet lukemat ajassa. Totuus; voittaa simuloidun arvon.

**Event**
Todellisuudessa tapahtuva tai tapahtunut asia, joka joko muuttaa mallia sisäisesti (esim. organisaatiomuutos) tai kuvaa ulkoisen tapahtuman (esim. pörssiromahdus). Päivä voi olla menneessä tai tulevassa; tulevaisuuden Event tulee voimaan, kun reaaliaika saavuttaa päivän.
_Avoid_: suunnitelma (se on Yearclockin Event), skenaarion tapahtuma

**Scenario**
Todellisuudesta kopiona alkava simulaatiomaailma, jossa kokeillaan vaihtoehtoja. Ei kirjoita todellisuuteen.

**Scenario Event**
Oletettu tapahtuma yhdessä skenaariossa. Elää vain siinä skenaariossa.
_Avoid_: Event (todellisuuden fakta)

**Simulation Run**
Yksi erillinen simulointiajo skenaariolle.

**Projected KPI Series**
Simulointiajon tuottama arvio KPI:n tulevasta kehityksestä. Eri asia kuin KPI Timeseries (toteuma).

**Action**
Simulaation perusteella tehty toimenpide-ehdotus. Ihminen päättää, ottaako sen käyttöön.

### 3.4 Suhteet (tiiviisti)
- Company 1—n Team, Service, Goal, KPI.
- Team 1—n Service (tuottaa); Team n—n Goal (tavoittelee).
- Goal n—n KPI (mitataan); KPI mittaa Servicea tai Teamia.
- KPI 1—n KPI Timeseries -lukemaa.
- Event vaikuttaa Teamiin, Serviceen tai KPI:hin (sisäinen: muuttaa rakennetta; ulkoinen: vaikuttaa mittareihin).
- Scenario alkaa kopiona todellisuudesta; Scenario 1—n Scenario Event; Scenario 1—n Simulation Run.
- Simulation Run tuottaa Projected KPI Series ja Action-ehdotuksia.
- Scenario Event → Event: vain käyttäjän manuaalinen kopiointi.

### 3.5 Laajennus myöhemmin: ontologia ja EDGY/ArchiMate **[VAHVISTA]**
Kun lukittu perusmalli toimii, ontologia voi tuoda mahdollisuuden määritellä omia tyyppejä.
Silloin perusmallin käsitteet (Team, Service, Goal...) ovat ontologian oletuspohja. Karkea vastaavuus
viitekehyksiin (ehdotus, ei eTWINin määrittelyä):

| eTWIN | EDGY | ArchiMate |
|---|---|---|
| Company | Organisation | Business Actor |
| Team | Organisation (yksikkö) | Business Actor / Role |
| Service | Product / Service | Business Service |
| Goal | Purpose | Goal / Outcome |
| KPI | *ei vastinetta* | Measure (laajennus) |
| Event | Event | Business Event |

Mittari ja aika ovat aukko molemmissa viitekehyksissä; siksi eTWIN ja Yearclock täydentävät niitä.

---

## 4. Miten sovellukset täydentävät toisiaan

### 4.1 Kaksi suuntaa

**A. Yearclock → eTWIN (suunnitelmasta malliin)**
Yearclockin Eventit kertovat *aiotun toiminnan*. eTWINille se on syöte skenaarioihin:
"Jos kampanja tehdään viikolla 14 ja ERP-päivitys viikolla 37, mitä tapahtuu myynnille ja kapasiteetille?"
- Suunnitellut Eventit → eTWIN-skenaarion *Scenario Eventeiksi* (oletuksena skenaarioon, ei suoraan todellisuuteen).
- Lane → ehdotus: kohdistus eTWINin Teamiin tai Serviceen.
- Category → eTWINin Eventin luokka (Label ei oletuksena).
- Series → jokainen Occurrence omana Scenario Eventinään (esim. tilinpäätös, kampanjat).

**B. eTWIN → Yearclock (mallista suunnitelmaan)**
eTWIN tuottaa *tietoa*, jonka pitäisi näkyä ajassa:
- Action-ehdotukset → Yearclockiin Recommendationeina (Pending), jotka ihminen hyväksyy Eventeiksi.
- Ennusteen merkittävät poikkeamat tai uhat → Yearclockin **External Signal** (kuvattu ADR-0003:ssa) tai **Recommendation** (CONTEXT.md).
- KPI:n arviointipäivät (esim. "Q3-tavoite arvioidaan 30.9.") → Event Yearclockin Laneen.
- Ulkoiset Eventit (esim. pörssiromahdus, sääntely) eTWINistä → Signal.

### 4.2 Suljettu silmukka

```
   Yearclock (suunnitelma)          eTWIN (todellisuus + simulaatio)
   ───────────────────────          ─────────────────────────
   Event: "Kampanja vk 14"  ─────►  Scenario Event
                                     │
                                     ▼
                                    Simulation Run ──► Projected KPI
                                     │
   Recommendation / Signal  ◄─────  Action-ehdotus / poikkeama
   (ihminen hyväksyy)                │
        │                            ▼
        ▼                           Action (Jira)
   Uusi / siirretty Event  ─────►  Toteuma (Event + KPI Timeseries)
                                     │
                                     └──► vertailu suunnitelmaan
```

Suunnitelma-vs-toteuma-vertailu on **uusi arvo, jota kumpikaan ei tuota yksin**: Yearclock tietää
milloin jotain piti tapahtua; eTWIN tietää, mitä oikeasti mitattiin ja milloin.

### 4.3 Mitä kumpikin saa toisesta

| Yearclockin hyöty | eTWINin hyöty |
|---|---|
| Tavoite- ja KPI-konteksti Eventille ("miksi tämä on tässä") | Valmis, ihmisen kuratoima tulevien toimien lähde skenaarioihin |
| Toteutunut vaikutus suunnitelmaan (poikkeamahälytys) | Kausirytmi ja ajoitusinformaatio ennusteisiin |
| Recommendation/External Signal -ominaisuudet saavat sisällön ilman omaa analytiikkaa | Toimenpiteille elävä aikajana (Action → Event) |
| Mahdollisuus jättää Yearclockin V1:n rajaus (ei suoritustilaa) koskemattomaksi | Käyttäjäystävällinen, kuvallinen suunnittelukäyttöliittymä |

---

## 5. Yhteiset käsitteelliset ja toiminnalliset yhtymäkohdat

Kymmenen yhtymäkohtaa, järjestetty arvon ja riskin mukaan.

### 5.1 Event – sama sana, eri väite *(pakollinen ratkaista)*
Kuten kohdassa 2.3: aika ei erota Eventejä, väite erottaa. **Päätetty (omistaja):** Yearclockiin ei lisätä Tentative- tai Hypothetical-tilaa; vaihtoehdoilla leikkiminen kuuluu eTWINin simulaatioon.

Säännöt:
1. **Yearclock Event on suunnitelma** (integraatiokielessä *Plan Entry*). Ei suoritustilaa. Mennyt päivä tekee siitä historiatietoa; mitään ei muuteta.
2. **eTWIN Event on fakta.** Se voi olla tulevaisuudessa ja tulee voimaan, kun reaaliaika saavuttaa päivän. Tilaa ei tallenneta; "voimassa" johdetaan päivästä.
3. **Scenario Event on oletus** ja elää vain skenaariossa. Se ei koskaan valu skenaarion ulkopuolelle.
4. **Plan Entry → Scenario Event** (oletus): suunnitelma on aikomus eikä fakta, joten se menee skenaarioon. Todellisuuteen se voi päätyä vain käyttäjän manuaalisen kopioinnin kautta, samoin kuin mikä tahansa Scenario Event.
5. **Occurrence Link:** kun eTWINiin tulee todellisuuden Event, jonka voi yhdistää Plan Entryyn, linkki kertoo "tämä suunnitelma toteutui tässä Eventissä". Planned ja Occurred ovat eri tietueita, joten suunniteltu ja toteutunut päivä sekä osittainen toteutuminen säilyvät analysoitavina.
6. Älä yhdistä tauluja. Linkki on viitesuhde, ei yhdistäminen.

### 5.2 Lane ↔ Team / Service
- Lane on visuaalinen rengas (prosessi, vastuu, tiimi tai painopiste). Merkitys vastaa eTWINissä Teamia tai Serviceä.
- **Ehdotus:** valinnainen `external_ref` Lanella osoittamaan eTWINin Teamiin tai Serviceen. Lane ei tule eTWINin tyypiksi.
- **Riski:** Yearclockin Lane ei määrittele oikeuksia; eTWINin Team ei saa tehdä niin Lanen kautta.

### 5.3 Category ↔ Eventin luokka
- Yearclockin Category (väri + nimi) on pelkkä luokittelu. eTWINin Eventillä on luokka (sisäinen/ulkoinen ja sisältöluokka), jonka kautta vaikutus voidaan laskea.
- **Ehdotus:** kohdistuslista "Yearclock Category → eTWIN Eventin luokka" integraation asetuksissa. Ei pakkoa; kohdistamaton Plan Entry tulee skenaarioon ilman luokkaa.
- Edellytys: eTWINin vaikutussääntöjen siirto tenant-tasolle (EVENT_IMPACT_RULE_SCOPE_V2), muuten kohdistus vaikuttaisi kaikkiin tenantteihin.

### 5.4 Series ↔ Scenario Eventit
- Series on toistuva rakenne. eTWINin lukitussa perusmallissa ei ole toistuvuuskäsitettä.
- **Ehdotus:** jokainen Occurrence viedään omana Scenario Eventinään (oletus). Series sääntönä vasta, jos eTWIN oppii käyttämään toistuvuussääntöä.

### 5.5 External Signal / Recommendation ↔ Analysis / Action Recommendation
- Täsmälleen sama idea kahdessa kielessä: *kone ehdottaa, ihminen päättää.*
- Yearclockin Recommendation (Pending/Accepted/Dismissed) = eTWINin Action Recommendation.
- **Ehdotus:** eTWIN on Recommendationin yksi *lähde* (provider), Yearclock sen *vastaanottaja ja päätöspaikka*. Hyväksyntä synnyttää Plan Entryn.
- Tämä aktivoi Yearclockin varatun laajennuksen ilman että Yearclockin ydin muuttuu.

### 5.6 KPI ja Goal – eivät tule Yearclockiin
- Yearclockissa ei ole tavoitetta eikä KPI:tä; se on *tietoinen rajaus* (ADR-0027), ei puute.
- **Ehdotus:** Yearclockiin ei tuoda KPI:tä eikä Goalia. Plan Entry voi viitata eTWINin KPI:hin ulkoisena linkkinä (Link, ks. 5.9) ja näyttää KPI:n tuoreen lukeman vain luku -tietona.
- **[VAHVISTA]** Pysyykö tavoitteiden ja KPI:iden hallinta kokonaan eTWINissä? (Ehdotus: kyllä.)

### 5.7 Organisaatio ja identiteetti
- Yearclock: Organization, Organization User, Group, rooli (Owner/Admin/Member), Yearclock Editor/Viewer.
- eTWIN: Tenant/company, membership (owner/member), Authentik-ryhmät.
- Molemmat käyttävät **Authentikia**. Jos asiakas hankkii molemmat, SSO ja yhteinen henkilöllisyys ovat luonteva yhdistävä tekijä.
- **Ehdotus:** erillinen *Organization ↔ Tenant -liitos* (1:1 oletuksena), kirjattuna molempiin päihin. Käyttäjien täsmäytys sähköpostin/OIDC-subjectin kautta; **oikeuksia ei periytetä** automaattisesti suuntaan eikä toiseen. Roolikartta on erikseen määriteltävä, koska Yearclockin Member ja eTWINin member eivät ole sama oikeus.

### 5.8 Laskutus ja lisenssit
- Yearclock: kuukausiennakkoinen seat-pohjainen Subscription per Organization (Stripe).
- eTWIN: tenant billing, token-usage-synkki Stripeen, planit.
- **Ehdotus (lyhyt aikaväli):** erilliset tilaukset, ei yhteistä laskua. **(Pitkä aikaväli, [VAHVISTA]):** niputettu paketti on liiketoimintapäätös, ei tekninen; älä rakenna sen varaan ennen kuin päätös on tehty.

### 5.9 Linkit, viitteet ja ulkoiset tunnisteet
- Yearclockilla on jo `Link`-käsite (titled http(s), max 10). Tämä riittää ensivaiheen "ikkunaksi" eTWINiin ilman skeemamuutosta: Plan Entryyn linkki skenaarioon, metrikkaan tai Analysiin.
- Syvemmälle integraatiolle tarvitaan vakaa **ulkoinen viite**: `external_system`, `external_id`, `external_url` – tallennetaan viitteenä, ei kopiona.

### 5.10 Audit, historia ja datansuoja
- Yearclock: Audit Log (ei sisältöä), Event Revision (asiakkaan sisältöä, ei Audit), GDPR-dokumentaatio, Support Access.
- eTWIN: tenant audit, support-context, token usage.
- **Ehdotus:** jokainen integraatiotapahtuma (vienti/tuonti/hyväksyntä) kirjataan *molempiin* audit-lokeihin ilman sisältöä – samoin periaattein kuin Yearclockin Export.
- **Riski:** Yearclock-sisältö on organisaation luottamuksellista sisältöä (Admin on luottamusraja). Tieto saa siirtyä eTWINiin vain eksplisiittisen, Owner/Admin-tason integraatiokytkennän jälkeen, ja vain valituista Yearclockeista/Laneista.

---

## 6. Integraatioarkkitehtuuri (ehdotus)

### 6.1 Periaatteet
1. **Itsenäisyys:** kumpikin toimii ilman toista; integraatio on valinnainen lisä.
2. **Viite ennen kopiota:** pidä totuuden lähde yhdessä paikassa; toinen järjestelmä säilyttää viitteen ja korkeintaan välimuistin.
3. **Ihminen päättää:** mikään koneellinen ehdotus ei muuta toisen järjestelmän suunnitelmaa ilman ihmisen hyväksyntää (Pending → Accepted).
4. **Pienin oikeus:** integraatio näkee vain sen, minkä Owner/Admin on erikseen valinnut.
5. **Tenant-eristys:** ei ristiin-tenant-hakuja; yksi Organization ↔ yksi Tenant.
6. **Idempotenssi:** kaikki synkronoinnit toistettavia (avain: external_system + external_id).

### 6.2 Vaihtoehdot

| Malli | Kuvaus | Hyvä | Huono |
|---|---|---|---|
| **A. Tiedostopohjainen** | Yearclock Export (xlsx/csv) → eTWIN CSV import (event) | Toimii heti, ei koodia | Käsityö, ei suuntaa takaisin |
| **B. Push eTWINin external API:in** | Yearclock lähettää Plan Entryt `POST /external/v1/events/upsert` (HMAC) | Olemassa oleva, tenant-eristetty rajapinta | Vain yksisuuntainen; "event" ≠ plan, tarvitsee skenaariokohdistuksen |
| **C. Kaksisuuntainen API + tapahtumat** | Kummallakin pieni, versioitu integraatio-API ja webhookit | Täysi silmukka | Eniten työtä; tarvitsee yhteisen sopimuksen |
| **D. Yhteinen integraatiokerros** | Ohut välittäjäpalvelu, joka kääntää käsitteet | Käsitteet pysyvät puhtaina | Uusi komponentti ylläpidettäväksi |

**Suositus:** A → B → C porrastettuna. D vasta, jos useampia järjestelmiä liitetään.

### 6.3 Porrastettu tiekartta (ehdotus)

| Vaihe | Sisältö | Muutokset Yearclockiin | Muutokset eTWINiin |
|---|---|---|---|
| **0** | Käsitemalli, tämä speksi, sanaston tasaus | Ei | `etwin/CONTEXT.md` (3.3:n pohjalta) |
| **1** | Tiedostotuonti: Yearclock Export → eTWIN CSV; Link-kenttä osoittamaan eTWINiin | Ei | CSV-import tukee `source`, `external_id` -kenttiä |
| **2** | Yearclock → eTWIN: valitut Laneet/Categoryt scenario eventeiksi (push, ihmisen käynnistämänä) | Integraatioasetukset Owner/Admin:lle, vienti-job, audit | Skenaario-event-ingest, kategoriakohdistus, tenant-tason impact-säännöt |
| **3** | eTWIN → Yearclock: Action Recommendation → Recommendation/External Signal (Pending) | **Avaa ADR-0027:n rajauksen** (oma ADR), Recommendation-toteutus | Vientirajapinta hyväksytyistä suosituksista |
| **4** | Suunnitelma-vs-toteuma: eTWIN actual events ja KPI-arvot näkyvät Plan Entryn rinnalla (vain luku) | Sivuvalikon "Toteuma"-paneeli | Luku-API metriikka-arvoille |
| **5** | Yhteinen SSO, Organization ↔ Tenant -liitos | Liitostaulu, kirjautumisvirta | Sama |

Jokainen vaihe on itsenäisesti arvokas ja voidaan pysäyttää.

---

## 7. Tietomallin vastaavuus (karkea)

| Yearclock | Suunta | eTWIN | Huomio |
|---|---|---|---|
| Organization | ↔ | Company | 1:1-liitos, ei yhdistämistä |
| Yearclock | → | (ei vastinetta) | Käytetään vientirajauksena |
| Lane | → | Team tai Service | valinnainen `external_ref` |
| Plan Entry (Event) | → | **Scenario Event** | oletus; `external_id` = Event/Occurrence-tunniste |
| Series | → | Scenario Eventit | jokainen Occurrence omana |
| Category | ↔ | Eventin luokka | kohdistuslista |
| Label | ✕ | — | ei viedä oletuksena |
| Link | → | Scenario / KPI / Simulation Run | ensivaiheen kevyt integraatio |
| Recommendation | ← | Action | vaihe 3, Pending |
| External Signal | ← | ulkoinen Event tai Simulation Run -poikkeama | vaihe 3 |
| Event (suunnitelma) | ← | Event (fakta, Occurrence Link) | vaihe 4, vain luku |
| (ei vastinetta) | ← | KPI / KPI Timeseries | vain luku -näkymä, vaihe 4 |
| Event Revision | ✕ | — | ei viedä |
| Audit Log | ↔ | tenant audit | molemmat kirjaavat integraation käytön |

---

## 8. Riskit ja avoimet kysymykset

### 8.1 Riskit
| # | Riski | Lievennys |
|---|---|---|
| R1 | **Event-käsitteen sekoittuminen** – aikomus ja havainto samana | Sanasto (5.1), erilliset tyypit, linkki ei yhdistä |
| R2 | **Yearclockin tietoinen rajaus murtuu** (suoritustila, tehtävyys) | Ei tuoda KPI:tä, Goalia tai Taskia Yearclockiin; näytetään vain luku -viitteenä |
| R3 | **Luottamuksellisuus** – Yearclock-sisältö eTWINiin ilman lupaa | Eksplisiittinen Admin-kytkentä, valintakohtainen vienti, audit |
| R4 | **eTWINin globaalit impact-säännöt** vääristävät monivuokraista integraatiota | Tenant-tason säännöt ennen vaihetta 2 |
| R5 | **AI-ehdotukset ohittavat ihmisen** | Recommendation pysyy Pending-tilassa; ei automaattista luontia |
| R6 | **Kaksi laskutusmallia** sekoittavat asiakasta | Erilliset tilaukset alussa |
| R7 | **Integraatio kovettaa kummankin kehityksen** (rajapintojen rikkoutuminen) | Versioitu integraatio-API, sopimustestit |
| R8 | **ArchiMate/EDGY-kohdistus tehdään liian aikaisin** ja jäykistää ontologiaa | Käytä minimijoukkoa, pidä laajennettavana |

### 8.2 Päätetty
1. **Ei Tentative/Hypothetical-tilaa Yearclockiin.** Vaihtoehdot ja "entä jos" kuuluvat eTWINin simulaatioon.
2. **eTWINin Event voi olla tulevaisuudessa fakta** ja tulee voimaan, kun reaaliaika saavuttaa päivän.
3. **Skenaariot ovat erillinen simulaatiomaailma.** Skenaarion tapahtumat eivät valu sen ulkopuolelle; siirto todellisuuteen on aina käyttäjän manuaalinen kopiointi.
4. **Ensimmäinen eTWIN-käsitemalli kuvaa lukitut alkuperäiset käsitteet; ontologia jätetään laajennukseksi.**

### 8.3 Kysymykset omistajalle **[VAHVISTA]**
1. **Kohderyhmä:** Onko tavoitetilassa *sama asiakas* molemmissa (yritys joka käyttää vuosikelloa ja mallintaa toimintaansa)? Vai myydäänkö niitä eri ostajille?
2. **Ydinsilmukka:** Onko tärkein arvo (a) suunnitelma → skenaario, (b) suositus → suunnitelma, vai (c) suunnitelma vs. toteuma?
3. **Tavoite/KPI:** Pysyykö tavoitteiden ja KPI:iden hallinta kokonaan eTWINissä (ehdotus: kyllä)?
4. **Suunta ja omistaja:** Onko Yearclock eTWINin suunnittelunäkymä, vai tasaveroiset erilliset tuotteet?
5. **Plan Entry baselineen?** Suunnitelma menee oletuksena skenaarioon. Saako käyttäjä viedä Plan Entryn suoraan todellisuuden tulevaksi faktaksi (eTWINin Event), vai vain skenaarion kautta kopioiden?
6. **Occurrence Linkin synty:** Syntyykö linkki Plan Entryn ja toteutuneen Eventin välille käsin, ehdotuksena (sama Lane/Team, päivä, luokka) vai automaattisesti?
7. **EDGY/ArchiMate:** Onko viitekehys ontologialaajennuksen *ohjaava metamalli* vai vain inspiraatio?
8. **Hosting ja data:** eTWIN on dokumentoitu Hetzner-tuotantoon ja Yearclockin tuotantoympäristö on eri (tarkista sijainnit) – saako data siirtyä palveluiden välillä (GDPR, sijainti)? Pidetäänkö integraatio asiakkaan nimenomaisen suostumuksen takana?
9. **Nimeäminen:** Hyväksytäänkö integraatiokielessä "Plan Entry" Yearclockin Eventille?
10. **Aikataulu:** Mikä on realistinen ensimmäinen demo – vaihe 1 (tiedostotuonti) vai vaihe 2 (push)?

---

## 9. Seuraavat askeleet

Ei toteutusta ennen vastauksia kohdan 8.3 kysymyksiin 1–5. Ehdotettu järjestys:

1. Omistaja käy läpi tämän speksin ja vastaa 8.3:n kysymyksiin 1–5.
2. Kirjoitetaan `etwin/CONTEXT.md` kohdan 3.3 pohjalta eTWINin omaan repoon ja viimeistellään sanasto (kuuluu eTWIN-repon, ei Yearclockin). Ontologia on tarkoituksella pois ensimmäisestä versiosta.
3. Päätetään vaiheen 1 (tiedostopohjainen demo) laajuus ja tehdään pieni käsin ajettava esimerkki: yksi Yearclock-vienti → eTWIN CSV-import → yksi ennuste.
4. Jos vaihe 2 etenee, kirjataan ADR molempiin repoihin (Yearclock: avataanko ADR-0027:n rajaus; eTWIN: tenant-tason impact-säännöt, integraatio-ingest) sekä päivitetään C4-malli ja DBML Yearclockin käytännön mukaan.

---

## Liite A: Lähdeviitteet

**Yearclock:** `CONTEXT.md`; `docs/adr/0003-separate-external-signals-from-events.md`; `docs/adr/0027-keep-yearclock-v1-event-only.md`; `docs/architecture/` (api, database, billing, support-access).
**eTWIN:** `etwin/docs/project/PROJECT_DOCUMENTATION.md`; `etwin/docs/user/USER_MANUAL.md`; `etwin/docs/db/DATABASE_DOCUMENTATION.md`; `etwin/docs/project/DB_APP_V2_SCHEMA.md`; `etwin/docs/project/EVENT_IMPACT_RULE_SCOPE_V2.md`; `etwin/docs/backend/EXTERNAL_API_DOCUMENTATION.md`; `etwin/docs/usecases/README.md`; `EnterpriseTwin/ontology/ontology.ttl`.

## Liite B: Mitä en tarkistanut
- En lukenut eTWINin lähdekoodia, vain dokumentaation; skeema voi poiketa dokumentoidusta.
- ArchiMate- ja EDGY-vastaavuudet ovat yleistietoon perustuvia arvioita, eivät eTWINin omaa määrittelyä.
- Hinnoittelua, markkina-asemaa tai asiakastarpeita ei ole arvioitu.
