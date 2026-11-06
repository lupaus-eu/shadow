import { GRAPH_NAME_MAX_LENGTH } from "../../api/orgTwinStructure";

// Count characters as the backend does (code points), so an emoji counts once.
function characterCount(value: string): number {
  return Array.from(value).length;
}

export function graphNameTooLong(name: string): boolean {
  return characterCount(name.trim()) > GRAPH_NAME_MAX_LENGTH;
}

// Names stored before the length limit are shortened for display.
export function displayGraphName(name: string): string {
  const characters = Array.from(name);
  if (characters.length <= GRAPH_NAME_MAX_LENGTH) return name;
  return `${characters.slice(0, GRAPH_NAME_MAX_LENGTH).join("")}…`;
}
