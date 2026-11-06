/** The titled links of an Event (Yearclock V2 P11): editing helpers and their limits, matching the server's rules. */

export type EventLink = { title: string; url: string };

export const LINKS_MAX = 10;
export const LINK_TITLE_MAX = 100;
export const LINK_URL_MAX = 2048;
export const LOCATION_MAX = 200;

export function isWebAddress(value: string): boolean {
  try {
    const url = new URL(value);
    return (url.protocol === "http:" || url.protocol === "https:") && url.host !== "";
  } catch {
    return false;
  }
}

/** Trim every title and address and drop rows that are completely empty (the editor keeps blank rows while typing). */
export function cleanLinks(links: EventLink[]): EventLink[] {
  return links.map((link) => ({ title: link.title.trim(), url: link.url.trim() })).filter((link) => link.title !== "" || link.url !== "");
}

export type LinkProblem = { row: number; kind: "title" | "address" | "duplicate" | "tooMany" };

/** One problem per row that cannot be saved; a row number is 1-based. `tooMany` is reported once with row 0. */
export function linkProblems(links: EventLink[]): LinkProblem[] {
  const cleaned = cleanLinks(links);
  const problems: LinkProblem[] = [];
  const seen = new Set<string>();
  cleaned.forEach((link, index) => {
    const row = index + 1;
    if (link.title === "" || link.title.length > LINK_TITLE_MAX) problems.push({ row, kind: "title" });
    else if (!isWebAddress(link.url) || link.url.length > LINK_URL_MAX) problems.push({ row, kind: "address" });
    else if (seen.has(link.url)) problems.push({ row, kind: "duplicate" });
    seen.add(link.url);
  });
  if (cleaned.length > LINKS_MAX) problems.push({ row: 0, kind: "tooMany" });
  return problems;
}

/** Where a link moves when it goes up or down; the same list when it cannot. */
export function moveLink(links: EventLink[], index: number, direction: -1 | 1): EventLink[] {
  const target = index + direction;
  if (target < 0 || target >= links.length) return links;
  const next = [...links];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export const sameLinks = (left: EventLink[] | undefined, right: EventLink[] | undefined) => JSON.stringify(left ?? []) === JSON.stringify(right ?? []);
