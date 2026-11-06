/** Case- and accent-insensitive text matching shared by Yearclock name search and filters. */
export function normalizeText(value: string): string {
  return value.normalize("NFKD").replace(/\p{M}/gu, "").toLocaleLowerCase("en").trim();
}

export function matchesText(query: string, ...candidates: Array<string | null | undefined>): boolean {
  const needle = normalizeText(query);
  if (!needle) return true;
  return candidates.some((candidate) => candidate != null && normalizeText(candidate).includes(needle));
}
