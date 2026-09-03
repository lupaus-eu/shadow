# AI Review Records

Tämä dokumentti määrittelee Step 13:n AI-review-tulosten versionhallittavan,
koneellisesti luettavan tallennusmuodon.

Review-recordit ovat auditointi- ja oppimisaineistoa. Ne eivät korvaa Git-
historiaa, PR-keskustelua, taskia, ADR:ää tai human review'ta. Koosteesta
tehdyt päätelmät ovat aina neuvoa-antavia; kehittäjä hyväksyy mahdolliset
jatkotaskit, ADR:t ja korjaukset.

## Sijainti Ja Elinkaari

Jokainen AI-review-kierros tallennetaan versionhallintaan:

```text
docs/ai-reviews/TASK-051/review-001.json
docs/ai-reviews/TASK-051/review-002.json
```

Hakemiston nimi on taskin tunnus. Kierrosnumerot alkavat yhdestä, ovat
kolminumeroisia ja kasvavat ilman aukkoja. Arkisto ei sisällä takautuvasti
luotuja recordeja aiemmista taskeista.

Step 13 etenee näin:

1. Reviewaa committed diff tai PR ja tallenna tarkat `base_sha`- ja `head_sha`
   -viitteet.
2. Luo seuraava JSON-record ja rajaa review'sta aina
   `docs/ai-reviews/**`. Näin metadatarecordin commitointi ei aiheuta
   rekursiivista metadatareview'ta.
3. Aja `python3 scripts/ai_review_records.py validate` ennen recordin pushia.
4. Jos review löytää korjattavaa, korjaa muutos, aja relevantit tarkistukset ja
   tee uusi review-kierros. Uusi record kirjaa aiempien findingien dispositionit;
   alkuperäistä recordia ei kirjoiteta uudelleen.
5. Ennen human review'ta aja kooste. Avoimet findingit ja `accepted_risk`
   -dispositionit näkyvät ihmisen arvioitavana.

`head_sha` on toteutusrevision, jota AI tosiasiassa reviewasi. Sen jälkeen
commitettu review-record ei muuta tätä todistetta eikä vaadi erillistä
AI-review-kierrosta pelkkänä metadata-muutoksena.

## Schema Version 1

Jokainen record on yksi JSON-objekti. Validator hylkää puuttuvat tai tuntemattomat
kentät, joten seuraavat kentät ovat tämän version koko sopimus.

| Kenttä | Muoto | Tarkoitus |
| --- | --- | --- |
| `schema_version` | `1` | Record-sopimuksen versio. |
| `record_id` | `TASK-XXX/review-NNN` | Yksilöllinen record-tunnus, joka vastaa tiedostopolkua. |
| `task.id`, `task.path` | task-tunnus ja repository-relative polku | Reviewn pysyvä scope-lähde. |
| `round` | positiivinen kokonaisluku | Taskin review-kierros. |
| `reviewed_at` | UTC-aika, jonka pääte on `Z` | Reviewn ajankohta. |
| `reviewer.label` | lyhyt, ei-sensitiivinen merkkijono | Reviewn tehnyt agentti tai palvelu. |
| `pull_request` | `null` tai `{number, url}` | Valinnainen PR-viite; URL on HTTPS eikä sisällä queryä tai fragmenttia. |
| `source` | katso alla | Muuttumaton reviewattu Git-vertailu. |
| `review` | katso alla | AI-reviewn päätelmä, findingit ja aiempien findingien dispositionit. |

`source` sisältää 40-merkkiset pienaakkoset Git-SHA:t `base_sha` ja `head_sha`,
niistä muodostetun merkkijonon `comparison` muodossa
`<base_sha>...<head_sha>` sekä `excluded_paths`-listan. Listassa on aina oltava:

```json
"docs/ai-reviews/**"
```

`review.outcome` on yksi arvoista `clean`, `findings` tai `inconclusive`.
`clean` ei sisällä findingeja; `findings` sisältää vähintään yhden; `inconclusive`
saa sisältää nolla tai useampia findingeja. Jokaisella lopputuloksella on lyhyt
`summary`.

Jokaisella `findings`-listan alkiolla on recordin sisällä yksilöllinen tunnus
`F-001`, `F-002` ja niin edelleen sekä:

- `category`: `bug`, `regression`, `security`, `missing_test`, `documentation`
  tai `scope`
- `severity`: `critical`, `high`, `medium`, `low` tai `info`
- `summary`, `rationale` ja `recommendation`
- vähintään yksi `locations`-alkio, jossa on repository-relative `path` ja
  valinnainen positiivinen `line`

Myöhempi record sulkee aiemman findingin `prior_finding_dispositions`-listassa.
Jokainen alkio viittaa täsmälliseen aiempaan `record_id`- ja `finding_id`-pariin,
käyttää arvoa `fixed`, `accepted_risk` tai `not_reproduced`, perustelee valinnan
ja sisältää nykyisen recordin tunnuksen sekä `head_sha`:n kentässä
`validated_by`. Sama finding voidaan dispositionoida vain kerran.

## Turvallisuus Ja Redaktointi

Älä tallenna recordiin tai testifixtureen:

- promptia, raakaa mallivastausta tai kokonaista transcriptia
- patchia, koodikatkelmaa tai request/response-bodya
- salasanaa, API-avainta, tokenia, cookiea tai muuta credentialia
- henkilötietoa ilman erillistä perustetta
- URL:ia, jossa on query-parametreja tai muuta sensitiivistä sisältöä

Kirjoita sen sijaan lyhyt redaktoitu tiivistelmä ja repository-relative
tiedostoviite. Validator tarkistaa rakenteen, mutta se ei korvaa kirjoittajan
vastuuta tunnistaa ja redaktoida sensitiivinen sisältö ennen commitia.

## Validointi Ja Analyysi

```bash
python3 scripts/ai_review_records.py validate
python3 scripts/ai_review_records.py summarize --format json
python3 scripts/ai_review_records.py summarize --format markdown
```

`validate` tarkistaa koko arkiston ja palauttaa virheessä recordin polun sekä
syyn. `summarize` validoi ensin, kirjoittaa vain standard outputiin eikä muuta
tiedostoja. Kooste sisältää review- ja outcome-määrät, avoimet findingit,
findingien category/severity/disposition-määrät sekä recurrence candidate -
ryhmät, joissa sama category ja tiedostopolku toistuvat.

Agentin analyysipromptin lähtökohta voi olla:

```text
Lue docs/AI-REVIEW-RECORDS.md ja aja
python3 scripts/ai_review_records.py summarize --format json.
Tee vain aineistoon perustuva neuvoa-antava yhteenveto: avoimet findingit,
toistuvat category/path-kuviot ja mahdolliset ehdotukset taskiksi tai ADR:n
arviointiin. Älä muuta tiedostoja tai tee päätöksiä kehittäjän puolesta.
```

Arkisto ei ole CI- tai merge-gate. CI ei vaadi recordin olemassaoloa eikä
automaatio hyväksy, hylkää tai korjaa findingeja.
