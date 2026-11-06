/** Text edits for the description toolbar (Yearclock V2 P11): pure, so they can be tested without a browser. */

export type FormatKind = "bold" | "italic" | "list" | "link";
export type Edit = { value: string; start: number; end: number };

const wrap = (value: string, start: number, end: number, marker: string): Edit => {
  const selected = value.slice(start, end);
  // Selecting the markers again takes them away.
  if (selected.startsWith(marker) && selected.endsWith(marker) && selected.length >= marker.length * 2) {
    const inner = selected.slice(marker.length, selected.length - marker.length);
    return { value: value.slice(0, start) + inner + value.slice(end), start, end: start + inner.length };
  }
  return { value: value.slice(0, start) + marker + selected + marker + value.slice(end), start: start + marker.length, end: end + marker.length };
};

/** The new text and selection after pressing a toolbar button with `start`–`end` selected. */
export function applyFormat(value: string, start: number, end: number, kind: FormatKind): Edit {
  if (kind === "bold") return wrap(value, start, end, "**");
  if (kind === "italic") return wrap(value, start, end, "*");
  if (kind === "link") {
    const selected = value.slice(start, end) || "text";
    const inserted = `[${selected}](https://)`;
    const addressStart = start + selected.length + 3;
    return { value: value.slice(0, start) + inserted + value.slice(end), start: addressStart, end: addressStart + "https://".length };
  }
  // A list: every line touched by the selection gets a "- " prefix, or loses it when all of them have one.
  const lineStart = value.lastIndexOf("\n", start - 1) + 1;
  const nextBreak = value.indexOf("\n", end);
  const lineEnd = nextBreak === -1 ? value.length : nextBreak;
  const lines = value.slice(lineStart, lineEnd).split("\n");
  const all = lines.every((line) => line.startsWith("- "));
  const changed = lines.map((line) => (all ? line.slice(2) : line.startsWith("- ") ? line : `- ${line}`)).join("\n");
  return { value: value.slice(0, lineStart) + changed + value.slice(lineEnd), start: lineStart, end: lineStart + changed.length };
}
