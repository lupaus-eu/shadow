---
title: Selaintallennusseloste
version: 1
effective_from: 2026-12-01
status: draft
acceptance: none
---
> **Luonnos juristin tarkastettavaksi.** Tuotetiimi on laatinut tämän repositorion dokumentaation pohjalta. Se ei ole oikeudellista neuvontaa, eikä juristi ole tarkastanut sitä. `TODO(lawyer)` merkitsee asiaa, joka on tuntematon tai tarvitsee juristin sanamuodon. Mikään tässä ei ole voimassa.

Yearclock tallentaa vain sen, mitä palvelun toimintaan tarvitaan, ja sen, mitä itse valitset. Se ei käytä analytiikka-, mainonta- tai seurantatallennusta, joten se ei näytä evästesuostumusta. `TODO(lawyer)` vahvista, että tämä sopii sähköisen viestinnän palveluista annetun lain 205 §:ään ja tietosuojavaltuutetun nykyiseen ohjeistukseen.

Automaattiset testit pitävät tämän luettelon samana kuin koodi (`backend/legal/browser-storage.json`).

## Evästeet

| Nimi | Tarkoitus | Kesto |
| --- | --- | --- |
| `yearclock_session` | Pitää sinut kirjautuneena (satunnainen istuntotunniste). | Enintään 8 tuntia; poistetaan uloskirjautuessa. |
| `yearclock_oidc_flow` | Suojaa kirjautumisen edestakaista kulkua väärennykseltä. | 10 minuuttia; poistetaan, kun kirjautuminen valmistuu. |

## Selaimeesi tallennetut asetukset

| Avain | Tarkoitus | Kesto |
| --- | --- | --- |
| `yearclock.locale` | Muistaa kielesi. | Kunnes tyhjennät sivuston tiedot. |
| `yearclock.filters.<vuosikello>` | Muistaa yhdelle vuosikellolle valitsemasi suodattimet. | Kunnes tyhjennät ne tai sivuston tiedot. |
| `yearclock.display.<vuosikello>` | Muistaa yhdelle vuosikellolle valitsemasi näkymän. | Kunnes valitset oletuksen tai tyhjennät sivuston tiedot. |
| `yearclock.length.<vuosikello>` | Muistaa yhden vuosikellon suunnitteluikkunan pituuden. | Kunnes valitset oletuksen tai tyhjennät sivuston tiedot. |
| `yearclock.had-session` (istuntotallennus) | Antaa kirjautumissivun kertoa, että istuntosi päättyi. | Kunnes suljet välilehden. |
| `yearclock.signed-out` (istuntotallennus) | Antaa kirjautumissivun vahvistaa uloskirjautumisesi kerran. | Poistetaan yhden käytön jälkeen. |

## Kirjautumissivut

Kirjautuminen tapahtuu identiteettipalvelun omassa osoitteessa, joka asettaa siellä omat istunto- ja väärennyssuojaevästeensä (`TODO(lawyer)` vahvista nimet ja kestot käynnissä olevasta versiosta).
