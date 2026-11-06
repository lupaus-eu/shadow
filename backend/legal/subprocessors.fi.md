---
title: Alikäsittelijät
version: 1
effective_from: 2026-12-01
status: draft
acceptance: notice
---
> **Luonnos juristin tarkastettavaksi.** Tuotetiimi on laatinut tämän repositorion dokumentaation pohjalta. Se ei ole oikeudellista neuvontaa, eikä juristi ole tarkastanut sitä. `TODO(lawyer)` merkitsee asiaa, joka on tuntematon tai tarvitsee juristin sanamuodon. Mikään tässä ei ole voimassa.

Shadow käyttää alla lueteltuja tahoja palvelun tuottamiseen. Kun Shadow on suunnittelusisältösi käsittelijä, ne ovat tietojenkäsittelysopimuksen mukaisia alikäsittelijöitä.

| Taho | Tarkoitus | Tiedot | Sijainti ja siirron peruste |
| --- | --- | --- | --- |
| UpCloud | Sovelluksen, tietokantojen ja identiteettipalvelun ylläpito. | Kaikki palvelun tiedot. | `TODO(lawyer)` konesalin sijainti, sopimus ja siirron peruste (ei ilmene repositoriosta). |
| Stripe | Tilauslaskutus ja maksu. | Laskutusnimi ja -sähköposti, osoite, verotunnisteet, maksutapa, laskut. Shadow ei tallenna korttitietoja. | `TODO(lawyer)` Stripen yhtiö, sijainti ja siirron peruste. |
| Scaleway (Transactional Email) | Shadowin ja kirjautumisen sähköpostien lähetys. | Vastaanottajan osoite ja viestin sisältö (ei koskaan tapahtuman sisältöä, paitsi valinnainen yhteenveto tulevista tapahtumista, jossa on tapahtumien otsikot). | `TODO(lawyer)` alue (esimerkkiasetuksissa `fr-par`, vahvista todellinen). |
| Scaleway (Object Storage) | Tietokantojen salatut varmuuskopiot palvelimen ulkopuolella. | Tietokannat, salattuna ennen lähetystä avaimella, joka on vain operaattorilla. | `TODO(lawyer)` alue ja varmuuskopioille oma projekti. |

Eivät alikäsittelijöitä: identiteettipalvelua (Authentik) ylläpitää Shadow omalla palvelimellaan; konttirekisteri (GitHub Container Registry) saa ohjelmistokuvia eikä henkilötietoja; henkilön itse yhdistämä tekoälyagentti on hänen oma valintansa (ks. tietosuojaseloste).

## Luettelon muutokset

`TODO(lawyer)` vahvista menettely. Suunniteltu menettely: omistajille ilmoitetaan sähköpostilla ja sovelluksessa vähintään 30 päivää ennen alikäsittelijän lisäämistä tai vaihtamista; omistaja voi vastustaa muutosta tänä aikana kirjoittamalla lakiasioiden yhteystietoon, ja osapuolet pyrkivät ratkaisemaan asian. Ehtojen tulee sanoa, mitä ratkaisemattomasta vastustuksesta seuraa.
