import type { Locale } from "../i18n";

// Pure rules of the line picker and the event list: ordering, grouping, who may do what and the wording of refusals.
// Nothing here talks to the server, so every function is unit-tested on plain data.

export type LineKind = "base" | "scenario";
export type TimelineLine = { id: string; name: string; kind: LineKind; parent_line_id: string | null; branch_event_id?: string | null; created_by_user_account_id?: string | null };
export type Role = "owner" | "admin" | "member";

/** Base line first, then each line's Scenarios right under it (depth first, in the order the server lists them). */
export function lineTree<T extends TimelineLine>(lines: readonly T[]): { line: T; depth: number }[] {
  const children = new Map<string | null, T[]>();
  const ids = new Set(lines.map((line) => line.id));
  for (const line of lines) {
    // A line whose parent is not in the list (never expected) is shown at the top rather than lost.
    const key = line.kind === "base" || !line.parent_line_id || !ids.has(line.parent_line_id) ? null : line.parent_line_id;
    children.set(key, [...(children.get(key) ?? []), line]);
  }
  const roots = (children.get(null) ?? []).sort((a, b) => Number(b.kind === "base") - Number(a.kind === "base"));
  const out: { line: T; depth: number }[] = [];
  const visit = (line: T, depth: number) => {
    out.push({ line, depth });
    for (const child of children.get(line.id) ?? []) visit(child, depth + 1);
  };
  for (const root of roots) visit(root, 0);
  return out;
}

/** Base line: Owner or Admin. Scenario: its creator, an Owner or an Admin (the rule of rename and delete). */
export function canManageLine(line: TimelineLine, role: Role, userId: string | null): boolean {
  if (role === "owner" || role === "admin") return true;
  return line.kind === "scenario" && userId !== null && line.created_by_user_account_id === userId;
}

/** Writing a line (events, acknowledge): Owners and Admins write the Base line, any Member a Scenario. */
export function canWriteLine(line: TimelineLine, role: Role): boolean {
  return line.kind === "scenario" || role === "owner" || role === "admin";
}

/** Adopting writes the parent line, so the parent's write rule applies. */
export function canAdopt(line: TimelineLine, lines: readonly TimelineLine[], role: Role): boolean {
  if (line.kind !== "scenario") return false;
  const parent = lines.find((item) => item.id === line.parent_line_id);
  return parent !== undefined && canWriteLine(parent, role);
}

export type ListedEvent = { id: string; planned: boolean };
export type EventRow<T extends ListedEvent> = { kind: "event"; event: T; selected: boolean; last: boolean } | { kind: "now" };

/**
 * The event list as rows: the events in the server's order with a single "Now" divider between the last happened event and the first
 * planned one (at the end when nothing is planned). `selectedId` marks the shown event; when none is given it is the last one.
 */
export function eventRows<T extends ListedEvent>(events: readonly T[], selectedId: string | null): EventRow<T>[] {
  const firstPlanned = events.findIndex((event) => event.planned);
  const nowAt = firstPlanned === -1 ? events.length : firstPlanned;
  const shown = selectedId ?? events[events.length - 1]?.id ?? null;
  const rows: EventRow<T>[] = [];
  events.forEach((event, index) => {
    if (index === nowAt) rows.push({ kind: "now" });
    rows.push({ kind: "event", event, selected: event.id === shown, last: index === events.length - 1 });
  });
  if (nowAt === events.length) rows.push({ kind: "now" });
  return rows;
}

/** The event the page shows: the requested one when the line has it, else the line's last event. */
export function shownEvent<T extends { id: string }>(events: readonly T[], requested: string | null): { event: T | null; isLast: boolean } {
  const last = events[events.length - 1] ?? null;
  const event = events.find((item) => item.id === requested) ?? last;
  return { event, isLast: event === null || event.id === last?.id };
}

/** The address of a tab: the line and event are carried in the query so a tab change keeps what is shown. */
export function tabQuery(lineId: string | null, eventId: string | null): string {
  const params = new URLSearchParams();
  if (lineId) params.set("line", lineId);
  if (eventId) params.set("event", eventId);
  const text = params.toString();
  return text ? `?${text}` : "";
}

/** Date of today in `YYYY-MM-DD` for the "new event" suggestion (the Base line suggests today). */
export function todayIso(now = new Date()): string {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

// ---- Refusals -------------------------------------------------------------------------------------------------------------------------

/** The structured `hint` of a 422 `chain_broken` answer (never prose; see `backend/app/timeline/validate.py`). */
export type ChainHint = {
  code: string;
  event_title?: string | null; event_date?: string | null; op?: string | null;
  line_name?: string | null; line_kind?: string | null; scenario_name?: string | null; in_other_line?: boolean;
  element_kind?: string | null; element_name?: string | null; type_name?: string | null; source_name?: string | null; target_name?: string | null;
  branch_event_title?: string | null; branch_event_date?: string | null;
};

type Words = {
  event: (title: string | null, date: string | null) => string;
  inScenario: (name: string) => string;
  node: (name: string | null) => string;
  connection: (source: string | null, target: string | null) => string;
  type: (name: string | null) => string;
  sentence: (where: string, what: string, todo: string) => string;
  branch: (scenario: string, title: string | null, date: string | null) => string;
  generic: (where: string) => string;
  todo: Record<string, string>;
  what: Record<string, (element: string, node: string, kind: string | null) => string>;
};

const en: Words = {
  event: (title, date) => `the event ${title ? `"${title}"` : "(untitled)"}${date ? ` (${date})` : ""}`,
  inScenario: (name) => ` in the scenario "${name}"`,
  node: (name) => (name ? `the node "${name}"` : "a node"),
  connection: (source, target) => (source && target ? `the connection from "${source}" to "${target}"` : "a connection"),
  type: (name) => (name ? `the type "${name}"` : "a type"),
  sentence: (where, what, todo) => `${where} ${what} ${todo}`,
  branch: (scenario, title, date) => `The scenario "${scenario}" starts from ${title ? `the event "${title}"` : "an event"}${date ? ` (${date})` : ""}.`,
  generic: (where) => `This change would break ${where}, so it was not saved. Change or remove the dependent event first.`,
  todo: {
    add_element_before: "Add it in an earlier event first, or remove the change that uses it.",
    remove_duplicate_add: "Remove the duplicate addition.",
    choose_existing_type: "Choose a type that still exists.",
    choose_allowed_connection: "Choose a connection type that is allowed between these node types, or allow it on the Types tab.",
    add_endpoint_before: "Add the missing node in an earlier event first.",
    choose_different_ends: "Choose two different nodes.",
    remove_duplicate_connection: "Remove the duplicate connection.",
    restore_branch_event: "Keep that event, or delete the scenario first.",
    move_after_branch_event: "Move the event to the date of that event or later.",
  },
  what: {
    missing_element: (element) => `would use ${element}, which does not exist at that point.`,
    duplicate_element: (element) => `would add ${element}, which already exists at that point.`,
    missing_type: (element) => `would use ${element}, which does not exist.`,
    connection_not_allowed: (element) => `would make ${element}, which the allowed connections do not permit.`,
    missing_endpoint: (element) => `would connect nodes of which one does not exist at that point (${element}).`,
    self_connection: (element) => `would connect a node to itself (${element}).`,
    duplicate_connection: (element) => `would make ${element}, which already exists in this direction with this type.`,
  },
};

const fi: Words = {
  event: (title, date) => `tapahtuma ${title ? `"${title}"` : "(nimetön)"}${date ? ` (${date})` : ""}`,
  inScenario: (name) => ` skenaariossa "${name}"`,
  node: (name) => (name ? `solmu "${name}"` : "solmu"),
  connection: (source, target) => (source && target ? `yhteys "${source}" -> "${target}"` : "yhteys"),
  type: (name) => (name ? `tyyppi "${name}"` : "tyyppi"),
  sentence: (where, what, todo) => `${where} ${what} ${todo}`,
  branch: (scenario, title, date) => `Skenaario "${scenario}" alkaa ${title ? `tapahtumasta "${title}"` : "tapahtumasta"}${date ? ` (${date})` : ""}.`,
  generic: (where) => `Tämä muutos rikkoisi kohteen ${where}, joten sitä ei tallennettu. Muuta tai poista riippuva tapahtuma ensin.`,
  todo: {
    add_element_before: "Lisää se ensin aiempaan tapahtumaan tai poista muutos, joka sitä käyttää.",
    remove_duplicate_add: "Poista kaksoislisäys.",
    choose_existing_type: "Valitse tyyppi, joka on vielä olemassa.",
    choose_allowed_connection: "Valitse yhteystyyppi, joka on sallittu näiden solmutyyppien välillä, tai salli se Tyypit-välilehdellä.",
    add_endpoint_before: "Lisää puuttuva solmu ensin aiempaan tapahtumaan.",
    choose_different_ends: "Valitse kaksi eri solmua.",
    remove_duplicate_connection: "Poista kaksoisyhteys.",
    restore_branch_event: "Säilytä se tapahtuma tai poista skenaario ensin.",
    move_after_branch_event: "Siirrä tapahtuma sen tapahtuman päivään tai myöhemmäksi.",
  },
  what: {
    missing_element: (element) => `käyttäisi kohdetta ${element}, jota ei ole vielä olemassa tässä kohdassa.`,
    duplicate_element: (element) => `lisäisi kohteen ${element}, joka on jo olemassa tässä kohdassa.`,
    missing_type: (element) => `käyttäisi kohdetta ${element}, jota ei ole olemassa.`,
    connection_not_allowed: (element) => `tekisi kohteen ${element}, jota sallitut yhteydet eivät salli.`,
    missing_endpoint: (element) => `yhdistäisi solmuja, joista toista ei ole vielä olemassa tässä kohdassa (${element}).`,
    self_connection: (element) => `yhdistäisi solmun itseensä (${element}).`,
    duplicate_connection: (element) => `tekisi kohteen ${element}, joka on jo olemassa samaan suuntaan samalla tyypillä.`,
  },
};

const CODE_TO_CAUSE: Record<string, string> = {
  add_element_before: "missing_element",
  remove_duplicate_add: "duplicate_element",
  choose_existing_type: "missing_type",
  choose_allowed_connection: "connection_not_allowed",
  add_endpoint_before: "missing_endpoint",
  choose_different_ends: "self_connection",
  remove_duplicate_connection: "duplicate_connection",
  restore_branch_event: "missing_branch_event",
  move_after_branch_event: "before_branch_event",
};

/**
 * What a refused write says: where the chain breaks (event, date, Scenario), which element or type, why, and what to do first.
 * Built from the structured hint only; the server's own text is never shown.
 */
export function chainBrokenMessage(hint: ChainHint | null | undefined, locale: Locale): string {
  const words = locale === "fi" ? fi : en;
  const where = words.event(hint?.event_title ?? null, hint?.event_date ?? null) + (hint?.in_other_line && hint.scenario_name ? words.inScenario(hint.scenario_name) : "");
  const cause = hint ? CODE_TO_CAUSE[hint.code] : undefined;
  if (!hint || !cause) return words.generic(where);
  const todo = words.todo[hint.code];
  if (cause === "missing_branch_event" || cause === "before_branch_event") {
    const scenario = hint.scenario_name ?? hint.line_name ?? "";
    const start = words.branch(scenario, hint.branch_event_title ?? null, hint.branch_event_date ?? null);
    return cause === "missing_branch_event" ? `${start} ${locale === "fi" ? "Tämä muutos poistaisi sen." : "This change would remove it."} ${todo}` : `${start} ${locale === "fi" ? `Tapahtuma ${where} olisi sitä ennen.` : `${where[0].toUpperCase()}${where.slice(1)} would come before it.`} ${todo}`;
  }
  const node = words.node(hint.element_name ?? null);
  const element = cause === "missing_type" ? words.type(hint.type_name ?? null)
    : cause === "missing_endpoint" ? `${hint.source_name ?? "?"} -> ${hint.target_name ?? "?"}`
    : cause === "self_connection" ? node
    : hint.element_kind === "connection" ? words.connection(hint.source_name ?? null, hint.target_name ?? null)
    : hint.element_kind === "type" ? words.type(hint.type_name ?? null)
    : node;
  const sentence = words.what[cause](element, node, hint.element_kind ?? null);
  return words.sentence(`${where[0].toUpperCase()}${where.slice(1)}`, sentence, todo);
}

/** The causes the hint codes stand for, for the tests that every one has a message. */
export const CHAIN_HINT_CODES = Object.keys(CODE_TO_CAUSE);

/** 409 `branch_point`: the event is where a Scenario starts. */
export function branchPointMessage(scenario: string | null | undefined, locale: Locale): string {
  return locale === "fi"
    ? `Tämä tapahtuma on skenaarion ${scenario ? `"${scenario}" ` : ""}alkukohta, joten sitä ei voi poistaa. Poista skenaario ensin.`
    : `This event is where the scenario ${scenario ? `"${scenario}" ` : ""}starts, so it cannot be deleted. Delete the scenario first.`;
}

export type Refusal = { reason?: string; [key: string]: unknown };

const NEW_SCENARIO = {
  en: "To keep the differences, create a new scenario from the parent line's latest state and make the changes there again.",
  fi: "Jos haluat säilyttää erot, luo uusi skenaario vanhemman linjan viimeisimmästä tilasta ja tee muutokset siellä uudelleen.",
};

/** Why adopting a Scenario was refused (`reason` and the fields of the 409 or 422 answer), with what to do next. */
export function adoptMessage(refusal: Refusal, locale: Locale): string {
  const fi = locale === "fi";
  const parent = typeof refusal.parent_name === "string" ? refusal.parent_name : fi ? "vanhempi linja" : "the parent line";
  switch (refusal.reason) {
    case "parent_moved_on": {
      const count = typeof refusal.events_after === "number" ? refusal.events_after : 0;
      return fi
        ? `Linjalle "${parent}" on tullut ${count} tapahtuma${count === 1 ? "" : "a"} sen jälkeen, kun skenaario alkoi, joten sitä ei voi liittää. ${NEW_SCENARIO.fi}`
        : `The line "${parent}" has ${count} event${count === 1 ? "" : "s"} after the point where this scenario starts, so it cannot be adopted. ${NEW_SCENARIO.en}`;
    }
    case "dates_precede":
      return fi
        ? `Skenaarion tapahtuma on päivätty ennen vanhemman linjan viimeisintä tapahtumaa${typeof refusal.parent_last_event_title === "string" ? ` "${refusal.parent_last_event_title}"` : ""}. Siirrä tapahtumat tämän päivän tai myöhemmille päiville tai ${NEW_SCENARIO.fi.charAt(0).toLowerCase()}${NEW_SCENARIO.fi.slice(1)}`
        : `A scenario event is dated before the parent line's last event${typeof refusal.parent_last_event_title === "string" ? ` "${refusal.parent_last_event_title}"` : ""}. Move the events to that date or later, or ${NEW_SCENARIO.en.charAt(0).toLowerCase()}${NEW_SCENARIO.en.slice(1)}`;
    case "nothing_to_adopt":
      return fi ? "Skenaariossa ei ole omia tapahtumia, joten ei ole mitään liitettävää. Piirrä ensin muutokset skenaarioon." : "The scenario has no events of its own, so there is nothing to adopt. Draw the changes in the scenario first.";
    case "base_line":
      return fi ? "Peruslinjaa ei voi liittää mihinkään." : "The Base line cannot be adopted into anything.";
    case "limit_reached":
      return fi ? "Vanhemmassa linjassa on jo suurin sallittu määrä tapahtumia." : "The parent line already holds the most events allowed.";
    default:
      return fi ? "Skenaariota ei voitu liittää. Yritä uudelleen." : "The scenario could not be adopted. Try again.";
  }
}

/** Why deleting a line was refused. */
export function deleteLineMessage(refusal: Refusal, locale: Locale): string {
  const fi = locale === "fi";
  if (refusal.reason === "has_children") return fi ? "Muut skenaariot alkavat tästä linjasta. Poista ne ensin." : "Other scenarios start from this line. Delete them first.";
  if (refusal.reason === "base_line") return fi ? "Peruslinjaa ei voi poistaa." : "The Base line cannot be deleted.";
  return fi ? "Linjaa ei voitu poistaa. Yritä uudelleen." : "The line could not be deleted. Try again.";
}
