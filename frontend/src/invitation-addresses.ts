/** Split a pasted list of addresses (Yearclock V2 bulk invitations). The server decides validity. */
export function parseAddresses(text: string): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const piece of text.split(/[\s,;]+/)) {
    const bracketed = piece.match(/<([^>]+)>/);
    const address = (bracketed ? bracketed[1] : piece).replace(/^[<"'(]+|[>"')]+$/g, "").trim();
    if (!address || !address.includes("@")) continue;
    const key = address.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(address);
  }
  return result;
}
