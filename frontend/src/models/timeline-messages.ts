import type { Locale } from "../i18n";

const en = {
  line: "Line",
  baseLine: "Base line",
  scenario: "Scenario",
  baseLineHelp: "The Base line records what has really happened.",
  scenarioHelp: "A Scenario is a what-if copy of its parent line.",
  lineOption: (name: string, kind: "base" | "scenario") => `${name} (${kind === "base" ? "Base line" : "Scenario"})`,
  newScenarioHere: "New scenario from here",
  newScenarioTitle: "New scenario",
  newScenarioFrom: (event: string | null) => (event ? `The scenario starts from the state after the event "${event}".` : "The scenario starts from the state of this line."),
  scenarioName: "Scenario name",
  create: "Create scenario",
  cancel: "Cancel",
  save: "Save",
  rename: "Rename",
  renameLine: (kind: "base" | "scenario"): string => (kind === "base" ? "Rename the Base line" : "Rename the scenario"),
  lineName: "Name",
  deleteScenario: "Delete scenario",
  deleteScenarioConfirm: (name: string) => `Delete the scenario ${name}? Its events, metrics and simulations are deleted with it.`,
  adopt: "Adopt into parent line",
  adoptConfirmTitle: (name: string, parent: string) => `Adopt the scenario ${name} into ${parent}?`,
  adoptConfirmBody: "The scenario's events are added to the parent line. A scenario that other scenarios start from stays; otherwise it is deleted. Metrics and simulations are not adopted.",
  adoptConfirm: "Adopt",
  adopted: (parent: string) => `The scenario was adopted into ${parent}.`,
  startChanged: "The state this scenario starts from changed after an event it depends on was edited. Check that the scenario still shows what you meant.",
  acknowledge: "I have checked it",
  duplicateName: "A line with this name already exists. Choose another name.",
  nameRequired: "Enter a name.",
  forbidden: "Your role does not allow this.",
  stale: "Someone changed this just now. It was reloaded; try again.",
  failed: "The request failed. Try again.",
  limitScenarios: "The model already holds the most lines allowed.",
  limitEvents: "The line already holds the most events allowed.",
  events: "Events",
  eventsOf: (line: string) => `Events of ${line}`,
  noEvents: "This line has no events yet.",
  now: "Now",
  planned: "Planned",
  happened: "Happened",
  changesCount: (count: number) => (count === 1 ? "1 change" : `${count} changes`),
  branchBadge: (name: string) => `Scenario: ${name}`,
  branchBadgeOpen: (name: string) => `Open the scenario ${name}`,
  shown: "Shown on the canvas",
  newEvent: "New event",
  editEvent: (title: string) => `Edit the event ${title}`,
  toggleEvents: "Show or hide the event list",
  pastNotice: (title: string, date: string, canWrite: boolean) => `The canvas shows the state after the event "${title}" (${date}). ${canWrite ? "Drawing changes this event, not the latest one." : "You cannot change it."}`,
  shownOn: (line: string, title: string | null, date: string | null) => (title ? `Shown: ${line}, after "${title}"${date ? ` (${date})` : ""}` : `Shown: ${line}, no events yet`),
  legendTitle: "Changed by this event",
  legendAdded: (count: number) => `+ ${count} added`,
  legendUpdated: (count: number) => `~ ${count} changed or re-routed`,
  legendRemoved: (count: number) => `\u2212 ${count} removed`,
  ghostNote: "Removed elements are drawn as dashed outlines. They cannot be selected or edited.",
  plannedNotice: "This event is planned: it has not happened yet and is not part of the present state.",
  showLatest: "Show the latest event",
  sharedTypes: "The node and connection types are shared by every line of the model. A change here applies to the Base line and all scenarios.",
  eventDialogTitle: "Event",
  newEventDialogTitle: "New event",
  eventTitle: "Title",
  eventDate: "Date",
  eventNote: "Note (optional)",
  eventDateHint: "A date after today makes the event planned.",
  eventDateSuggestion: "Today is suggested.",
  titleRequired: "Enter a title.",
  dateRequired: "Enter a date.",
  changes: "Changes in this event",
  noChanges: "This event has no changes. Draw on the canvas to add some.",
  changeDate: "Change date",
  deleteEvent: "Delete event",
  deleteEventConfirm: (title: string) => `Delete the event ${title}? Later events and scenarios must still make sense without it.`,
  createEvent: "Create event",
  loadingEvent: "Loading the event…",
  close: "Close",
  unknownElement: "an element",
  describeChange: (op: string, names: { element: string | null; source: string | null; target: string | null; type: string | null; fields: string[] }) => {
    const element = names.element ? `"${names.element}"` : "an element";
    const ends = names.source && names.target ? ` from "${names.source}" to "${names.target}"` : "";
    const type = names.type ? ` (${names.type})` : "";
    switch (op) {
      case "add_node": return `Add the node ${element}${type}`;
      case "remove_node": return `Remove the node ${element}`;
      case "update_node": return `Change the node ${element}${names.fields.length ? `: ${names.fields.join(", ")}` : ""}`;
      case "add_connection": return `Connect${ends || ` ${element}`}${type}`;
      case "remove_connection": return `Remove the connection ${element}`;
      case "reroute_connection": return `Re-route the connection ${element}${ends}`;
      case "change_connection_type": return `Change the type of the connection ${element}${type}`;
      default: return `${op} ${element}`;
    }
  },
  fieldNames: { name: "name", description: "description", node_type_id: "type" } as Record<string, string>,
};

const fi: typeof en = {
  line: "Linja",
  baseLine: "Peruslinja",
  scenario: "Skenaario",
  baseLineHelp: "Peruslinja kertoo, mitä on oikeasti tapahtunut.",
  scenarioHelp: "Skenaario on vanhemman linjan vaihtoehtoinen kopio.",
  lineOption: (name, kind) => `${name} (${kind === "base" ? "Peruslinja" : "Skenaario"})`,
  newScenarioHere: "Uusi skenaario tästä",
  newScenarioTitle: "Uusi skenaario",
  newScenarioFrom: (event) => (event ? `Skenaario alkaa tilasta tapahtuman "${event}" jälkeen.` : "Skenaario alkaa tämän linjan tilasta."),
  scenarioName: "Skenaarion nimi",
  create: "Luo skenaario",
  cancel: "Peruuta",
  save: "Tallenna",
  rename: "Nimeä uudelleen",
  renameLine: (kind) => (kind === "base" ? "Nimeä peruslinja uudelleen" : "Nimeä skenaario uudelleen"),
  lineName: "Nimi",
  deleteScenario: "Poista skenaario",
  deleteScenarioConfirm: (name) => `Poistetaanko skenaario ${name}? Sen tapahtumat, mittarit ja simuloinnit poistetaan sen mukana.`,
  adopt: "Liitä vanhempaan linjaan",
  adoptConfirmTitle: (name, parent) => `Liitetäänkö skenaario ${name} linjaan ${parent}?`,
  adoptConfirmBody: "Skenaarion tapahtumat lisätään vanhempaan linjaan. Skenaario, josta muut skenaariot alkavat, säilyy; muuten se poistetaan. Mittareita ja simulointeja ei liitetä.",
  adoptConfirm: "Liitä",
  adopted: (parent) => `Skenaario liitettiin linjaan ${parent}.`,
  startChanged: "Tila, josta tämä skenaario alkaa, muuttui, kun sen käyttämää tapahtumaa muokattiin. Tarkista, että skenaario näyttää yhä sen, mitä tarkoitit.",
  acknowledge: "Olen tarkistanut",
  duplicateName: "Samanniminen linja on jo olemassa. Valitse toinen nimi.",
  nameRequired: "Anna nimi.",
  forbidden: "Roolisi ei salli tätä.",
  stale: "Joku muutti tätä juuri. Tiedot ladattiin uudelleen; yritä uudelleen.",
  failed: "Pyyntö epäonnistui. Yritä uudelleen.",
  limitScenarios: "Mallissa on jo suurin sallittu määrä linjoja.",
  limitEvents: "Linjalla on jo suurin sallittu määrä tapahtumia.",
  events: "Tapahtumat",
  eventsOf: (line) => `Linjan ${line} tapahtumat`,
  noEvents: "Tällä linjalla ei ole vielä tapahtumia.",
  now: "Nyt",
  planned: "Suunniteltu",
  happened: "Tapahtunut",
  changesCount: (count) => (count === 1 ? "1 muutos" : `${count} muutosta`),
  branchBadge: (name) => `Skenaario: ${name}`,
  branchBadgeOpen: (name) => `Avaa skenaario ${name}`,
  shown: "Näkyy piirtoalueella",
  newEvent: "Uusi tapahtuma",
  editEvent: (title) => `Muokkaa tapahtumaa ${title}`,
  toggleEvents: "Näytä tai piilota tapahtumalista",
  pastNotice: (title, date, canWrite) => `Piirtoalue näyttää tilan tapahtuman "${title}" (${date}) jälkeen. ${canWrite ? "Piirtäminen muuttaa tätä tapahtumaa, ei viimeisintä." : "Et voi muuttaa sitä."}`,
  shownOn: (line, title, date) => (title ? `Näytetään: ${line}, tapahtuman "${title}" jälkeen${date ? ` (${date})` : ""}` : `Näytetään: ${line}, ei vielä tapahtumia`),
  legendTitle: "Tämän tapahtuman muutokset",
  legendAdded: (count) => `+ ${count} lisätty`,
  legendUpdated: (count) => `~ ${count} muutettu tai uudelleenyhdistetty`,
  legendRemoved: (count) => `\u2212 ${count} poistettu`,
  ghostNote: "Poistetut kohteet piirretään katkoviivalla. Niitä ei voi valita eikä muokata.",
  plannedNotice: "Tämä tapahtuma on suunniteltu: se ei ole vielä tapahtunut eikä kuulu nykytilaan.",
  showLatest: "Näytä viimeisin tapahtuma",
  sharedTypes: "Solmu- ja yhteystyypit ovat yhteiset kaikille mallin linjoille. Muutos tässä koskee peruslinjaa ja kaikkia skenaarioita.",
  eventDialogTitle: "Tapahtuma",
  newEventDialogTitle: "Uusi tapahtuma",
  eventTitle: "Otsikko",
  eventDate: "Päivämäärä",
  eventNote: "Muistiinpano (valinnainen)",
  eventDateHint: "Tulevaisuuden päivämäärä tekee tapahtumasta suunnitellun.",
  eventDateSuggestion: "Ehdotus on tämä päivä.",
  titleRequired: "Anna otsikko.",
  dateRequired: "Anna päivämäärä.",
  changes: "Tapahtuman muutokset",
  noChanges: "Tapahtumassa ei ole muutoksia. Lisää niitä piirtämällä.",
  changeDate: "Muuta päivämäärää",
  deleteEvent: "Poista tapahtuma",
  deleteEventConfirm: (title) => `Poistetaanko tapahtuma ${title}? Myöhempien tapahtumien ja skenaarioiden on silti toimittava ilman sitä.`,
  createEvent: "Luo tapahtuma",
  loadingEvent: "Ladataan tapahtumaa…",
  close: "Sulje",
  unknownElement: "elementti",
  describeChange: (op, names) => {
    const element = names.element ? `"${names.element}"` : "elementti";
    const ends = names.source && names.target ? ` "${names.source}" -> "${names.target}"` : "";
    const type = names.type ? ` (${names.type})` : "";
    switch (op) {
      case "add_node": return `Lisää solmu ${element}${type}`;
      case "remove_node": return `Poista solmu ${element}`;
      case "update_node": return `Muuta solmua ${element}${names.fields.length ? `: ${names.fields.join(", ")}` : ""}`;
      case "add_connection": return `Yhdistä${ends || ` ${element}`}${type}`;
      case "remove_connection": return `Poista yhteys ${element}`;
      case "reroute_connection": return `Ohjaa yhteys ${element} uudelleen${ends}`;
      case "change_connection_type": return `Vaihda yhteyden ${element} tyyppi${type}`;
      default: return `${op} ${element}`;
    }
  },
  fieldNames: { name: "nimi", description: "kuvaus", node_type_id: "tyyppi" },
};

export const timelineMessages = (locale: Locale) => (locale === "fi" ? fi : en);

type ChangeLike = { op: string; element_id: string | null; payload: Record<string, unknown> };

/** One change of an event as a sentence for reading, with element and type names resolved from `names` (id to name). */
export function describeChange(change: ChangeLike, names: ReadonlyMap<string, string>, locale: Locale): string {
  const text = timelineMessages(locale);
  const name = (value: unknown) => (typeof value === "string" ? names.get(value) ?? null : null);
  const payload = change.payload ?? {};
  return text.describeChange(change.op, {
    element: (typeof payload.name === "string" ? payload.name : null) ?? name(change.element_id),
    source: name(payload.source_node_id),
    target: name(payload.target_node_id),
    type: name(payload.node_type_id) ?? name(payload.connection_type_id),
    fields: Object.keys(payload).map((key) => text.fieldNames[key]).filter((value): value is string => Boolean(value)),
  });
}
