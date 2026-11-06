import type { Locale } from "../i18n";

const KINDS = ["label", "yearclock", "lane", "category", "series", "event", "series_exception"] as const;

type Copy = {
  menu: string;
  title: string;
  intro: string;
  scope: string;
  scopeEmpty: string;
  roles: { owner: string; admin: string };
  exportTitle: string;
  exportBody: string;
  exportIncludes: string;
  exportExcludes: string;
  exportAction: string;
  exporting: string;
  exported: string;
  importTitle: string;
  importBody: string;
  importRules: string;
  choose: string;
  reading: string;
  previewTitle: string;
  nothingSaved: string;
  kinds: Record<(typeof KINDS)[number], string>;
  columns: { kind: string; created: string; updated: string; unchanged: string };
  overwrites: (count: number) => string;
  errorsTitle: (count: number, shown: number) => string;
  errorColumns: { row: string; kind: string; column: string; problem: string };
  save: string;
  saving: string;
  saved: string;
  cancel: string;
  rateLimited: (minutes: number) => string;
  failed: string;
  fileProblems: Record<string, string>;
  problems: Record<string, string>;
  limit: (name: string) => string;
};

const en: Copy = {
  menu: "Export and import data",
  title: "Export and import data",
  intro: "Download everything you administer as one CSV file, and upload the same file later to put the data back or to change many rows at once.",
  scope: "Included Organizations",
  scopeEmpty: "You are not an Owner or Admin of any Organization, so there is nothing to export or import.",
  roles: { owner: "Owner", admin: "Admin" },
  exportTitle: "Export",
  exportBody: "One file with every Organization listed above. There are no filters in this version.",
  exportIncludes: "Included: Yearclocks (also archived ones), Lanes, Categories, Labels, Events, and recurring Series with their changed or skipped occurrences.",
  exportExcludes: "Left out: people, Groups and access rights, deleted Events, Event history, the Activity log, and billing data. The Organization's own settings are only named in the file, never changed by an import.",
  exportAction: "Download CSV",
  exporting: "Preparing the file…",
  exported: "The file was saved.",
  importTitle: "Import",
  importBody: "Choose a file made by this export. You first see what would change, and nothing is saved until you confirm.",
  importRules: "A row whose id already exists is updated from the file, and a row that does not exist is created. Nothing is ever deleted. If any row has a problem, nothing is saved. An import never creates Organizations.",
  choose: "Choose a CSV file",
  reading: "Checking the file…",
  previewTitle: "What the import would do",
  nothingSaved: "This is a preview. Nothing has been saved.",
  kinds: { label: "Labels", yearclock: "Yearclocks", lane: "Lanes", category: "Categories", series: "Series", event: "Events", series_exception: "Changed or skipped occurrences" },
  columns: { kind: "Kind", created: "New", updated: "Changed", unchanged: "Same" },
  overwrites: (count) => `${count} ${count === 1 ? "Event has" : "Events have"} been changed by someone after this file was made; saving would overwrite ${count === 1 ? "that change" : "those changes"}. The old values stay in the Event history.`,
  errorsTitle: (count, shown) => `${count} ${count === 1 ? "problem" : "problems"} found${shown < count ? ` (the first ${shown} are shown)` : ""}. Fix the file and upload it again.`,
  errorColumns: { row: "Row", kind: "Kind", column: "Column", problem: "Problem" },
  save: "Save import",
  saving: "Saving…",
  saved: "The import was saved.",
  cancel: "Cancel",
  rateLimited: (minutes) => `You have made too many transfers this hour. Try again in ${minutes} ${minutes === 1 ? "minute" : "minutes"}.`,
  failed: "The operation failed. Try again.",
  fileProblems: { not_utf8: "The file is not UTF-8 text. Save it as CSV (UTF-8).", empty_file: "The file is empty.", unreadable_file: "The file could not be read as CSV.", missing_column: "The header row lacks a required column.", unsupported_format: "This file was not made by this version of the export.", missing_format_row: "The file lacks the format row that the export writes after the header.", too_many_rows: "The file has more rows than allowed.", file_too_large: "The file is too large.", id_conflict: "An id in the file already belongs to another Organization.", errors: "The file has problems, so nothing was saved." },
  problems: { missing_value: "A value is missing", invalid_id: "Not a valid id", invalid_boolean: "Use true or false", invalid_number: "Not a valid number", invalid_value: "Not a valid value", invalid_date: "Not a valid date", invalid_json: "Not valid data", unknown_type: "Unknown row kind", unknown_parent: "The parent row was not found", unknown_lane: "The Lane was not found in this Yearclock", linked_lane: "Events cannot be in a Linked Lane", unknown_category: "The Category was not found", unknown_label: "The Label was not found", unknown_source_lane: "The source Lane was not found", unknown_occurrence: "That occurrence does not exist", wrong_parent: "The row belongs to another parent than in the database", deleted_in_database: "This row was deleted in the application", recurring_occurrence: "This Event is an occurrence of a Series", series_rule_changed: "The repeat rule of an existing Series cannot be changed", not_administrator: "You are not an Owner or Admin of this Organization", organization_read_only: "The Organization is read-only", organization_not_active: "The Organization is not active", limit_reached: "A limit is reached" },
  limit: (name) => `limit: ${name}`,
};

const fi: Copy = {
  menu: "Tietojen vienti ja tuonti",
  title: "Tietojen vienti ja tuonti",
  intro: "Lataa kaikki hallinnoimasi tiedot yhtenä CSV-tiedostona. Samalla tiedostolla voit myöhemmin palauttaa tiedot tai muuttaa monta riviä kerralla.",
  scope: "Mukaan tulevat organisaatiot",
  scopeEmpty: "Et ole minkään organisaation omistaja tai ylläpitäjä, joten viemistä tai tuotavaa ei ole.",
  roles: { owner: "Omistaja", admin: "Ylläpitäjä" },
  exportTitle: "Vienti",
  exportBody: "Yksi tiedosto, jossa on kaikki yllä luetellut organisaatiot. Tässä versiossa ei ole rajausvalintoja.",
  exportIncludes: "Mukana: vuosikellot (myös arkistoidut), kehät, kategoriat, tunnisteet, tapahtumat sekä toistuvat sarjat muutettuine tai ohitettuine toistoineen.",
  exportExcludes: "Pois jätetään: ihmiset, ryhmät ja käyttöoikeudet, poistetut tapahtumat, tapahtumien historia, toimintaloki ja laskutustiedot. Organisaation omat asetukset vain mainitaan tiedostossa, eikä tuonti koskaan muuta niitä.",
  exportAction: "Lataa CSV",
  exporting: "Valmistellaan tiedostoa…",
  exported: "Tiedosto tallennettiin.",
  importTitle: "Tuonti",
  importBody: "Valitse tällä viennillä tehty tiedosto. Näet ensin, mitä muuttuisi, eikä mitään tallenneta ennen kuin vahvistat.",
  importRules: "Rivi, jonka tunniste (id) on jo olemassa, päivitetään tiedoston mukaiseksi, ja rivi jota ei ole, luodaan. Mitään ei koskaan poisteta. Jos yhdessäkin rivissä on ongelma, mitään ei tallenneta. Tuonti ei koskaan luo organisaatioita.",
  choose: "Valitse CSV-tiedosto",
  reading: "Tarkistetaan tiedostoa…",
  previewTitle: "Mitä tuonti tekisi",
  nothingSaved: "Tämä on esikatselu. Mitään ei ole tallennettu.",
  kinds: { label: "Tunnisteet", yearclock: "Vuosikellot", lane: "Kehät", category: "Kategoriat", series: "Sarjat", event: "Tapahtumat", series_exception: "Muutetut tai ohitetut toistot" },
  columns: { kind: "Laji", created: "Uusia", updated: "Muuttuu", unchanged: "Ennallaan" },
  overwrites: (count) => `${count} ${count === 1 ? "tapahtumaa" : "tapahtumaa"} on muutettu sen jälkeen, kun tämä tiedosto tehtiin. Tallennus ylikirjoittaisi ${count === 1 ? "muutoksen" : "muutokset"}. Vanhat arvot säilyvät tapahtuman historiassa.`,
  errorsTitle: (count, shown) => `Löytyi ${count} ${count === 1 ? "ongelma" : "ongelmaa"}${shown < count ? ` (näytetään ${shown} ensimmäistä)` : ""}. Korjaa tiedosto ja lataa se uudelleen.`,
  errorColumns: { row: "Rivi", kind: "Laji", column: "Sarake", problem: "Ongelma" },
  save: "Tallenna tuonti",
  saving: "Tallennetaan…",
  saved: "Tuonti tallennettiin.",
  cancel: "Peruuta",
  rateLimited: (minutes) => `Olet tehnyt tällä tunnilla liian monta siirtoa. Yritä uudelleen ${minutes} minuutin kuluttua.`,
  failed: "Toiminto epäonnistui. Yritä uudelleen.",
  fileProblems: { not_utf8: "Tiedosto ei ole UTF-8-tekstiä. Tallenna se CSV-muodossa (UTF-8).", empty_file: "Tiedosto on tyhjä.", unreadable_file: "Tiedostoa ei voitu lukea CSV:nä.", missing_column: "Otsikkorivistä puuttuu pakollinen sarake.", unsupported_format: "Tätä tiedostoa ei ole tehty tämän version viennillä.", missing_format_row: "Tiedostosta puuttuu muotorivi, jonka vienti kirjoittaa otsikon jälkeen.", too_many_rows: "Tiedostossa on enemmän rivejä kuin sallitaan.", file_too_large: "Tiedosto on liian suuri.", id_conflict: "Tiedoston tunniste kuuluu jo toiselle organisaatiolle.", errors: "Tiedostossa on ongelmia, joten mitään ei tallennettu." },
  problems: { missing_value: "Arvo puuttuu", invalid_id: "Tunniste ei kelpaa", invalid_boolean: "Käytä arvoa true tai false", invalid_number: "Ei kelvollinen luku", invalid_value: "Arvo ei kelpaa", invalid_date: "Päivämäärä ei kelpaa", invalid_json: "Tiedot eivät kelpaa", unknown_type: "Tuntematon rivilaji", unknown_parent: "Ylärivi puuttuu", unknown_lane: "Kehää ei löydy tästä vuosikellosta", linked_lane: "Tapahtuma ei voi olla linkitetyllä kehällä", unknown_category: "Kategoriaa ei löydy", unknown_label: "Tunnistetta ei löydy", unknown_source_lane: "Lähdekehää ei löydy", unknown_occurrence: "Tuota toistoa ei ole", wrong_parent: "Rivi kuuluu eri ylärivin alle kuin tietokannassa", deleted_in_database: "Tämä rivi on poistettu sovelluksessa", recurring_occurrence: "Tämä tapahtuma on sarjan toisto", series_rule_changed: "Olemassa olevan sarjan toistosääntöä ei voi muuttaa", not_administrator: "Et ole tämän organisaation omistaja tai ylläpitäjä", organization_read_only: "Organisaatio on vain luku -tilassa", organization_not_active: "Organisaatio ei ole aktiivinen", limit_reached: "Raja on täynnä" },
  limit: (name) => `raja: ${name}`,
};

export const KIND_ORDER = KINDS;

export function dataTransferMessages(locale: Locale): Copy {
  return locale === "fi" ? fi : en;
}
