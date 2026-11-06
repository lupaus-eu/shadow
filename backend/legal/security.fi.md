---
title: Tietoturvatoimet
version: 1
effective_from: 2026-12-01
status: draft
acceptance: none
---
> **Luonnos juristin tarkastettavaksi.** Tuotetiimi on laatinut tämän repositorion dokumentaation pohjalta. Se ei ole oikeudellista neuvontaa, eikä juristi ole tarkastanut sitä. `TODO(lawyer)` merkitsee asiaa, joka on tuntematon tai tarvitsee juristin sanamuodon. Mikään tässä ei ole voimassa.

Tämä on yhteenveto teknisistä ja organisatorisista toimista, jotka suojaavat Yearclockia. Se on myös tietojenkäsittelysopimuksen tietoturvaliite. `TODO(lawyer)` päätä, miten avoimet asiat kuvataan (merkitty alla "ei vielä tehty").

## Kirjautuminen ja istunnot
- Kirjautuminen käyttää ulkoista identiteettipalvelua OpenID Connect -valtuutuskoodikululla, PKCE:llä sekä `state`- ja `nonce`-arvoilla. Salasanakirjautuminen vaatii toisen tekijän; avainkoodit (passkey) ovat tuettuja. Yearclock ei tallenna salasanoja, avainkoodeja eikä MFA-salaisuuksia.
- Istunto on satunnainen tunniste, joka tallennetaan vain tiivisteenä. Eväste on `HttpOnly`, `SameSite=Lax` ja tuotannossa `Secure`, kestää oletuksena enintään 8 tuntia ja mitätöidään palvelimella uloskirjautuessa.
- Tilaa muuttavat pyynnöt epäluotetusta alkuperästä hylätään.

## Asiakkaiden erottelu
- Kunkin organisaation tiedot erotetaan tietokannassa pakotetulla rivitason suojauksella rajoitetun tietokantaroolin alla; reitit tarkistavat lisäksi jäsenyyden ja roolin. Automaattiset testit kattavat tämän organisaatioiden välillä.
- Jäsenet eivät voi korottaa omaa rooliaan tai pääsyään; ylläpitäjät eivät voi luoda omistajia tai tulla omistajiksi.

## Yearclockin henkilöstön pääsy
- Alustan henkilöstö pääsee organisaatioon vain tukipääsyn kautta: omistajat hyväksyvät pyynnön rajauksella ja kestolla, pääsy valvotaan tietokannassa ja päättyy itsestään, ja jokainen käyttö kirjataan. `TODO(lawyer)` henkilöstön salassapitositoumukset.

## Sovellus ja infrastruktuuri
- Salaisuudet ovat vain palvelimen ympäristömuuttujissa, eivät koskaan repositoriossa. Tuotanto ei käynnisty ilman niitä.
- Stripen webhook-kutsut allekirjoitustarkistetaan ja ne ovat idempotentteja. Palvelu kutsuu vain määritettyjä Stripe-, identiteetti- ja sähköpostipäätepisteitä.
- Reunapalvelin asettaa HSTS:n, upottamisen kieltävän sisältöturvakäytännön, `nosniff`-otsakkeen sekä referrer- ja permissions-käytännöt, ja merkitsee API- ja konsolivastaukset `no-store`.
- Asiakkaan suunnittelusisältö tyhjennetään poistamisen jälkeen tietosuojaselosteessa ja vaihtosivulla kuvatulla tavalla.

## Varmuuskopiot ja palautus
- Molemmat tietokannat vedostetaan aikataulun mukaan, salataan palvelimella ennen lähetystä ja säilytetään palvelimen ulkopuolella erillisessä tallennusprojektissa; avain on vain operaattorilla. Säilytys on 24 tuntikohtaista, 30 päivittäistä ja 6 kuukausittaista tilannekuvaa. Palautuksia harjoitellaan aikataulun mukaan (`TODO(lawyer)` määritä sitoutuva palautuspiste ja -aika; beta-dokumentaatio mainitsee yhden tunnin palautuspisteen ja puolen päivän palautusajan ilman käytettävyystakuuta).

## Ei vielä tehty
- Ulkopuolinen tunkeutumistesti ja riippuvuuksien tarkastus on suunniteltu ennen julkaisua, eikä niitä ole vielä tehty.
- API-pyyntöjen nopeusrajoitus reunalla on päättämättä.
