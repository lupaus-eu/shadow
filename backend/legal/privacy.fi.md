---
title: Tietosuojaseloste
version: 1
effective_from: 2026-12-01
status: draft
acceptance: none
---
> **Luonnos juristin tarkastettavaksi.** Tuotetiimi on laatinut tämän repositorion dokumentaation pohjalta. Se ei ole oikeudellista neuvontaa, eikä juristi ole tarkastanut sitä. `TODO(lawyer)` merkitsee asiaa, joka on tuntematon tai tarvitsee juristin sanamuodon. Mikään tässä ei ole voimassa.

Tämä seloste kertoo Shadowin käyttäjille, mitä henkilötietoja Shadow itse rekisterinpitäjänä käsittelee ja miksi. Asiakkaan syöttämän suunnittelusisällön osalta Shadow toimii asiakkaan lukuun henkilötietojen käsittelijänä (ks. tietojenkäsittelysopimus), ja asiakas tiedottaa omille henkilöilleen.

## Kuka vastaa
Rekisterinpitäjä on palveluntarjoajan tiedot -sivulla nimetty tarjoaja. Yhteystieto tietosuoja-asioissa: `TODO(lawyer)` lakiasioiden yhteysosoite. `TODO(lawyer)` onko tietosuojavastaava pakollinen (tuotetiimin seulontamuistion mukaan ei, ellei juristi ole eri mieltä).

## Mitä käsittelemme, miksi ja kuinka kauan

| Tieto | Miksi | Kuinka kauan |
| --- | --- | --- |
| Tunnistautumispalvelun antama identiteetti (myöntäjä, tunniste, sähköposti, näyttönimi, kieli) | Tunnistaaksemme sinut ja näyttääksemme nimesi työtovereillesi | Niin kauan kuin sinulla on tili `TODO(lawyer)` |
| Istunto- ja kirjautumistila (tiivistetty tunniste, vanhenemisaika, identiteettitunniste uloskirjautumiseen asti) | Pitääksemme sinut turvallisesti kirjautuneena | Istunnon kesto (oletuksena 8 tuntia); kirjautumistila 10 minuuttia |
| Jäsenyys ja rooli organisaatiossa, ryhmät ja viimeksi avatut vuosikellot | Hallitaksemme pääsyä ja näyttääksemme viimeisimmät vuosikellosi ja mitä on muuttunut edellisen käyntisi jälkeen | Kunnes jäsenyys, ryhmä, vuosikello tai organisaatio poistetaan |
| Kutsut (sähköpostiosoite ja rooli) | Kutsuaksemme sinut | Seitsemän päivää, sitten ne vanhenevat |
| Organisaation laskutusnimi ja laskutussähköposti | Laskuttaaksemme asiakasta Stripen kautta | Niin kauan kuin organisaatio on olemassa, ja kirjanpitoaineistona sen tyhjennyksen jälkeen `TODO(lawyer)` kirjanpitolain mukainen aika |
| Toimintaloki (kuka teki mitä ja milloin; vähäinen muutosyhteenveto) | Vastuullisuus ja turvallisuus | `TODO(lawyer)` aika; yhteenvedot tyhjennetään organisaation tyhjennyksessä |
| Ilmoitukset, ilmoitusasetukset ja valinnainen yhteenveto tulevista tapahtumista | Kertoaksemme omien käyttöoikeuksiesi ja roolisi muutoksista ja, jos otat sen käyttöön, lähettääksemme sähköpostilla tulevat tapahtumat (tämä sähköposti luettelee tapahtumien otsikot) | Ilmoitukset 90 päivää |
| Jonossa oleva sähköposti (vastaanottaja, otsikko, teksti) | Luotettava toimitus | `TODO(lawyer)` aika (ei vielä määritelty) |
| Hyväksyntätiedot (kuka hyväksyi minkä asiakirjan version ja milloin) | Osoittaaksemme, mitä on sovittu | Säilytetään sopimusnäyttönä `TODO(lawyer)` aika |

Shadow ei tallenna salasanoja, avainkoodeja, MFA-salaisuuksia eikä maksukorttitietoja. Se ei käytä analytiikkaa tai mainontaa eikä myy henkilötietoja.

`TODO(lawyer)` kunkin käyttötarkoituksen oikeusperuste (sopimus, oikeutettu etu, lakisääteinen velvoite) lain vaatimassa muodossa.

## Kuka saa tietoja
Alikäsittelijät-sivulla luetellut alikäsittelijät (ylläpito, sähköposti, laskutus, varmuuskopiot) saavat tietoja vain palvelun tuottamiseen. Alustan henkilöstö näkee organisaation vain tukipääsyn kautta, jonka organisaation omistajat hyväksyvät. Jos yhdistät tekoälyagentin Shadowiin, agentin tarjoaja on oma valintasi ja käsittelee sen, mitä agentti lukee; Shadow ei tallenna agenttien keskusteluja.

## Siirrot EU:n ja ETA:n ulkopuolelle
`TODO(lawyer)` luettele siirrot ja niiden suojatoimet (ks. alikäsittelijät-sivu).

## Oikeutesi
Voit pyytää pääsyä tietoihisi, niiden oikaisua tai poistamista, käsittelyn rajoittamista tai vastustamista sekä siirrettävyyttä, ja voit tehdä valituksen tietosuojavaltuutetulle. Kirjoita lakiasioiden yhteysosoitteeseen. Jos tietosi ovat asiakkaan organisaation suunnittelusisältöä, välitämme pyyntösi kyseiselle asiakkaalle.
