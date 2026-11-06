---
title: Palvelun vaihto ja tietojen palautus
version: 1
effective_from: 2026-12-01
status: draft
acceptance: none
---
> **Luonnos juristin tarkastettavaksi.** Tuotetiimi on laatinut tämän repositorion dokumentaation pohjalta. Se ei ole oikeudellista neuvontaa, eikä juristi ole tarkastanut sitä. `TODO(lawyer)` merkitsee asiaa, joka on tuntematon tai tarvitsee juristin sanamuodon. Mikään tässä ei ole voimassa.

Voit viedä tietosi pois milloin tahansa ja siirtyä toiselle palveluntarjoajalle. Tämä sivu kertoo, miten. `TODO(lawyer)` yhdenmukaista tämä EU:n tietosäädöksen pilvipalveluille asettamien vaihtoehtojen kanssa (enimmäisilmoitusaika, siirtymäaika, maksut ja tiedonantovelvoitteet) ennen julkaisua.

## Mitä voit viedä

| Mitä | Kuka | Muoto |
| --- | --- | --- |
| **Organisaation vienti**: organisaation koko sisältö sekä jäsenten nimet, sähköpostit ja roolit | Omistajat | JSON-tiedosto (sitä ei voi tuoda takaisin) |
| **Kaikkien tietojesi vienti ja tuonti**: kaikkien ylläpitämiesi organisaatioiden vuosikellot, kaistat, luokat, tunnisteet, tapahtumat ja toistuvat sarjat | Omistajat ja ylläpitäjät | Yksi CSV-tiedosto (`shadow-data/1`), jonka sama sivu voi tuoda uudelleen; ihmisiä, käyttöoikeuksia, poistettuja tapahtumia, historiaa ja laskutustietoja ei ole mukana |
| **Tapahtumat taulukkoon** | Kuka tahansa vuosikellon lukija | Excel tai CSV, yhdestä vuosikellosta |
| Vuosikellon tulostus tai kuva | Kuka tahansa vuosikellon lukija | Tulostusasettelu tai kuvatiedosto |

Viennit kirjataan toimintalokiin määränä ja muotona, ei koskaan sisältönä.

## Kun tilauksesi päättyy

Peruttu tilaus päättyy maksetun jakson lopussa. Sen jälkeen organisaatio on vain luettavissa: mitään ei poisteta, organisaation vienti toimii edelleen ja omistaja voi tilata palvelun uudelleen. Jos omistaja poistaa organisaation, sen voi palauttaa 30 päivän ajan; sen jälkeen sisältö tyhjennetään eikä sitä voi palauttaa. Varmuuskopio voi säilyä varmuuskopioiden säilytysajan (24 tuntikohtaista, 30 päivittäistä ja 6 kuukausittaista tilannekuvaa).

## Ilmoitusaika, siirtymä ja maksut

`TODO(lawyer)` vaihtoilmoituksen aika, siirtymäaika, veloitetaanko vaihdosta ja miten, sekä miten vaihtopyyntö tehdään ja vastataan.
