/** The formatted-description subset (Yearclock V2 P11, ADR-0033), matching `backend/app/rich_text.py`.
 *
 * Bold `**x**`, italic `*x*`, `- ` bullet and `1. ` numbered lists, `[text](https://…)` links, bare web
 * addresses, paragraphs, and line breaks. Everything else is literal text and no HTML is ever produced.
 */

export type Inline = string | { b: Inline[] } | { i: Inline[] } | { a: string; href: string };
export type Block = { p: Inline[][] } | { ul: Inline[][] } | { ol: Inline[][] };

const PUNCTUATION = new Set("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~");
const URL_AT = /^https?:\/\/[^\s<>"]+/;
const LINK_AT = /^\[([^\[\]]+)\]\((https?:\/\/[^\s)]+)\)/;
const TRAILING = /[).,;:!?\]]+$/;
const BULLET = /^- (.*)$/;
const NUMBERED = /^(\d{1,3})\. (.*)$/;

function push(nodes: Inline[], text: string) {
  if (!text) return;
  const last = nodes[nodes.length - 1];
  if (typeof last === "string") nodes[nodes.length - 1] = last + text;
  else nodes.push(text);
}

/** Index of the unescaped marker that closes one opened before `start`, or -1. */
function closing(text: string, start: number, marker: "**" | "*"): number {
  let index = start;
  while (index < text.length) {
    const char = text[index];
    if (char === "\\") { index += 2; continue; }
    if (marker === "**" && text.startsWith("**", index)) return index;
    if (marker === "*" && char === "*") {
      if (text.startsWith("**", index)) { index += 2; continue; }
      return index;
    }
    index += 1;
  }
  return -1;
}

export function parseInline(text: string): Inline[] {
  const nodes: Inline[] = [];
  let index = 0;
  while (index < text.length) {
    const char = text[index];
    if (char === "\\" && index + 1 < text.length && PUNCTUATION.has(text[index + 1])) {
      push(nodes, text[index + 1]);
      index += 2;
      continue;
    }
    if (char === "*") {
      const marker = text.startsWith("**", index) ? "**" : "*";
      const end = closing(text, index + marker.length, marker);
      const body = end !== -1 ? text.slice(index + marker.length, end) : "";
      if (end !== -1 && body && !/^\s/.test(body) && !/\s$/.test(body)) {
        nodes.push(marker === "**" ? { b: parseInline(body) } : { i: parseInline(body) });
        index = end + marker.length;
        continue;
      }
      push(nodes, marker);
      index += marker.length;
      continue;
    }
    if (char === "[") {
      const match = LINK_AT.exec(text.slice(index));
      if (match) {
        nodes.push({ a: match[1], href: match[2] });
        index += match[0].length;
        continue;
      }
    }
    if (char === "h") {
      const match = URL_AT.exec(text.slice(index));
      if (match) {
        let address = match[0];
        const trailing = TRAILING.exec(address);
        if (trailing) address = address.slice(0, trailing.index);
        if (address) {
          nodes.push({ a: address, href: address });
          index += address.length;
          continue;
        }
      }
    }
    push(nodes, char);
    index += 1;
  }
  return nodes;
}

export function parseRichText(text: string): Block[] {
  const blocks: Array<Block | { gap: true }> = [];
  for (const line of text.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n")) {
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    const last = blocks[blocks.length - 1];
    if (bullet || numbered) {
      const kind = bullet ? "ul" : "ol";
      const item = parseInline(bullet ? bullet[1] : numbered![2]);
      if (last && kind in last) (last as { ul: Inline[][] } & { ol: Inline[][] })[kind].push(item);
      else blocks.push(kind === "ul" ? { ul: [item] } : { ol: [item] });
    } else if (line.trim() === "") {
      if (last && !("gap" in last)) blocks.push({ gap: true });
    } else if (last && "p" in last) last.p.push(parseInline(line));
    else blocks.push({ p: [parseInline(line)] });
  }
  return blocks.filter((block): block is Block => !("gap" in block));
}

/** The text without markers, as the server writes it into exports and search. */
export function plainText(text: string | null | undefined, format: "plain" | "markdown" = "markdown"): string {
  if (!text) return "";
  if (format !== "markdown") return text;
  const flat = (nodes: Inline[]): string => nodes.map((node) => (typeof node === "string" ? node : "b" in node ? flat(node.b) : "i" in node ? flat(node.i) : node.a === node.href ? node.href : `${node.a} (${node.href})`)).join("");
  return parseRichText(text).map((block) => ("p" in block ? block.p.map(flat).join("\n") : "ul" in block ? block.ul.map((item) => `- ${flat(item)}`).join("\n") : block.ol.map((item, index) => `${index + 1}. ${flat(item)}`).join("\n"))).join("\n\n");
}
