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
  newScenarioFrom: (change: string | null) => (change ? `The scenario starts from the state after the change "${change}".` : "The scenario starts from the state of this line."),
  scenarioName: "Scenario name",
  create: "Create scenario",
  cancel: "Cancel",
  save: "Save",
  rename: "Rename",
  renameLine: (kind: "base" | "scenario"): string => (kind === "base" ? "Rename the Base line" : "Rename the scenario"),
  lineName: "Name",
  deleteScenario: "Delete scenario",
  deleteScenarioConfirm: (name: string) => `Delete the scenario ${name}? Its changes, metrics and simulations are deleted with it.`,
  adopt: "Adopt into parent line",
  adoptConfirmTitle: (name: string, parent: string) => `Adopt the scenario ${name} into ${parent}?`,
  adoptConfirmBody: "The scenario's changes are added to the parent line. A scenario that other scenarios start from stays; otherwise it is deleted. Metrics and simulations are not adopted.",
  adoptConfirm: "Adopt",
  adopted: (parent: string) => `The scenario was adopted into ${parent}.`,
  startChanged: "The state this scenario starts from changed after an change it depends on was edited. Check that the scenario still shows what you meant.",
  acknowledge: "I have checked it",
  duplicateName: "A line with this name already exists. Choose another name.",
  nameRequired: "Enter a name.",
  forbidden: "Your role does not allow this.",
  stale: "Someone changed this just now. It was reloaded; try again.",
  failed: "The request failed. Try again.",
  limitScenarios: "The model already holds the most lines allowed.",
  limitChanges: "The line already holds the most changes allowed.",
  changes: "Changes",
  changesOf: (line: string) => `Changes of ${line}`,
  noChanges: "This line has no changes yet.",
  now: "Now",
  planned: "Planned",
  happened: "Happened",
  editsCount: (count: number) => (count === 1 ? "1 edit" : `${count} edits`),
  branchBadge: (name: string) => `Scenario: ${name}`,
  branchBadgeOpen: (name: string) => `Open the scenario ${name}`,
  shown: "Shown on the canvas",
  newChange: "New change",
  editChange: (title: string) => `Edit the change ${title}`,
  toggleChanges: "Show or hide the change list",
  pastNotice: (title: string, date: string, canWrite: boolean) => `The canvas shows the state after the change "${title}" (${date}). ${canWrite ? "Drawing edits this change, not the latest one." : "You cannot change it."}`,
  shownOn: (line: string, title: string | null, date: string | null) => (title ? `Shown: ${line}, after "${title}"${date ? ` (${date})` : ""}` : `Shown: ${line}, no changes yet`),
  legendTitle: "Edited by this change",
  legendAdded: (count: number) => `+ ${count} added`,
  legendUpdated: (count: number) => `~ ${count} changed or re-routed`,
  legendRemoved: (count: number) => `\u2212 ${count} removed`,
  ghostNote: "Removed elements are drawn as dashed outlines. They cannot be selected or edited.",
  plannedNotice: "This change is planned: it has not happened yet and is not part of the present state.",
  showLatest: "Show the latest change",
  startRow: "Start",
  startsFrom: "Starts from:",
  startAfter: "after the change",
  startUnknownChange: "(a change that cannot be read)",
  startCaption: "Start state, not editable. Change it in the parent line.",
  startOpenLine: (name: string) => `Open the parent line ${name}`,
  startOpenChange: (title: string) => `Open the change ${title} in the parent line`,
  sharedTypes: "The node and connection types are shared by every line of the model. A change here applies to the Base line and all scenarios.",
  changeDialogTitle: "Change",
  newChangeDialogTitle: "New change",
  changeTitle: "Title",
  dateLabel: "Date",
  changeNote: "Note (optional)",
  changeDateHint: "A date after today makes the change planned.",
  changeDateSuggestion: "Today is suggested.",
  titleRequired: "Enter a title.",
  dateRequired: "Enter a date.",
  edits: "Edits in this change",
  noEdits: "This change has no edits. Draw on the canvas to add some.",
  changeDate: "Change date",
  deleteChange: "Delete change",
  deleteChangeConfirm: (title: string) => `Delete the change ${title}? Later changes and scenarios must still make sense without it.`,
  createChange: "Create change",
  loadingChange: "Loading the change…",
  close: "Close",
  unknownElement: "an element",
  describeEdit: (op: string, names: { element: string | null; source: string | null; target: string | null; type: string | null; fields: string[] }) => {
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
  newScenarioFrom: (change) => (change ? `Skenaario alkaa tilasta muutoksen "${change}" jälkeen.` : "Skenaario alkaa tämän linjan tilasta."),
  scenarioName: "Skenaarion nimi",
  create: "Luo skenaario",
  cancel: "Peruuta",
  save: "Tallenna",
  rename: "Nimeä uudelleen",
  renameLine: (kind) => (kind === "base" ? "Nimeä peruslinja uudelleen" : "Nimeä skenaario uudelleen"),
  lineName: "Nimi",
  deleteScenario: "Poista skenaario",
  deleteScenarioConfirm: (name) => `Poistetaanko skenaario ${name}? Sen muutokset, mittarit ja simuloinnit poistetaan sen mukana.`,
  adopt: "Liitä vanhempaan linjaan",
  adoptConfirmTitle: (name, parent) => `Liitetäänkö skenaario ${name} linjaan ${parent}?`,
  adoptConfirmBody: "Skenaarion muutokset lisätään vanhempaan linjaan. Skenaario, josta muut skenaariot alkavat, säilyy; muuten se poistetaan. Mittareita ja simulointeja ei liitetä.",
  adoptConfirm: "Liitä",
  adopted: (parent) => `Skenaario liitettiin linjaan ${parent}.`,
  startChanged: "Tila, josta tämä skenaario alkaa, muuttui, kun sen käyttämää muutosta muokattiin. Tarkista, että skenaario näyttää yhä sen, mitä tarkoitit.",
  acknowledge: "Olen tarkistanut",
  duplicateName: "Samanniminen linja on jo olemassa. Valitse toinen nimi.",
  nameRequired: "Anna nimi.",
  forbidden: "Roolisi ei salli tätä.",
  stale: "Joku muutti tätä juuri. Tiedot ladattiin uudelleen; yritä uudelleen.",
  failed: "Pyyntö epäonnistui. Yritä uudelleen.",
  limitScenarios: "Mallissa on jo suurin sallittu määrä linjoja.",
  limitChanges: "Linjalla on jo suurin sallittu määrä muutoksia.",
  changes: "Muutokset",
  changesOf: (line) => `Linjan ${line} muutokset`,
  noChanges: "Tällä linjalla ei ole vielä muutoksia.",
  now: "Nyt",
  planned: "Suunniteltu",
  happened: "Tapahtunut",
  editsCount: (count) => (count === 1 ? "1 muokkaus" : `${count} muokkausta`),
  branchBadge: (name) => `Skenaario: ${name}`,
  branchBadgeOpen: (name) => `Avaa skenaario ${name}`,
  shown: "Näkyy piirtoalueella",
  newChange: "Uusi muutos",
  editChange: (title) => `Muokkaa muutosta ${title}`,
  toggleChanges: "Näytä tai piilota muutoslista",
  pastNotice: (title, date, canWrite) => `Piirtoalue näyttää tilan muutoksen "${title}" (${date}) jälkeen. ${canWrite ? "Piirtäminen muokkaa tätä muutosta, ei viimeisintä." : "Et voi muuttaa sitä."}`,
  shownOn: (line, title, date) => (title ? `Näytetään: ${line}, muutoksen "${title}" jälkeen${date ? ` (${date})` : ""}` : `Näytetään: ${line}, ei vielä muutoksia`),
  legendTitle: "Tämän muutoksen muokkaamat",
  legendAdded: (count) => `+ ${count} lisätty`,
  legendUpdated: (count) => `~ ${count} muutettu tai uudelleenyhdistetty`,
  legendRemoved: (count) => `\u2212 ${count} poistettu`,
  ghostNote: "Poistetut kohteet piirretään katkoviivalla. Niitä ei voi valita eikä muokata.",
  plannedNotice: "Tämä muutos on suunniteltu: se ei ole vielä tapahtunut eikä kuulu nykytilaan.",
  showLatest: "Näytä viimeisin muutos",
  startRow: "Lähtötilanne",
  startsFrom: "Alkaa:",
  startAfter: "muutoksen jälkeen:",
  startUnknownChange: "(muutosta ei voi lukea)",
  startCaption: "Lähtötilanne, ei muokattavissa. Muuta sitä vanhemmassa linjassa.",
  startOpenLine: (name) => `Avaa vanhempi linja ${name}`,
  startOpenChange: (title) => `Avaa muutos ${title} vanhemmassa linjassa`,
  sharedTypes: "Solmu- ja yhteystyypit ovat yhteiset kaikille mallin linjoille. Muutos tässä koskee peruslinjaa ja kaikkia skenaarioita.",
  changeDialogTitle: "Muutos",
  newChangeDialogTitle: "Uusi muutos",
  changeTitle: "Otsikko",
  dateLabel: "Päivämäärä",
  changeNote: "Muistiinpano (valinnainen)",
  changeDateHint: "Tulevaisuuden päivämäärä tekee muutoksesta suunnitellun.",
  changeDateSuggestion: "Ehdotus on tämä päivä.",
  titleRequired: "Anna otsikko.",
  dateRequired: "Anna päivämäärä.",
  edits: "Muutoksen muokkaukset",
  noEdits: "Muutoksessa ei ole muokkauksia. Lisää niitä piirtämällä.",
  changeDate: "Muutoksen päivämäärä",
  deleteChange: "Poista muutos",
  deleteChangeConfirm: (title) => `Poistetaanko muutos ${title}? Myöhempien muutosten ja skenaarioiden on silti toimittava ilman sitä.`,
  createChange: "Luo muutos",
  loadingChange: "Ladataan muutosta…",
  close: "Sulje",
  unknownElement: "elementti",
  describeEdit: (op, names) => {
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

type EditLike = { op: string; element_id: string | null; payload: Record<string, unknown> };

/** One edit of an change as a sentence for reading, with element and type names resolved from `names` (id to name). */
export function describeEdit(edit: EditLike, names: ReadonlyMap<string, string>, locale: Locale): string {
  const text = timelineMessages(locale);
  const name = (value: unknown) => (typeof value === "string" ? names.get(value) ?? null : null);
  const payload = edit.payload ?? {};
  return text.describeEdit(edit.op, {
    element: (typeof payload.name === "string" ? payload.name : null) ?? name(edit.element_id),
    source: name(payload.source_node_id),
    target: name(payload.target_node_id),
    type: name(payload.node_type_id) ?? name(payload.connection_type_id),
    fields: Object.keys(payload).map((key) => text.fieldNames[key]).filter((value): value is string => Boolean(value)),
  });
}
