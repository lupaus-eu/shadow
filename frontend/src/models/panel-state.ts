/** Which side panels of the Structure canvas are collapsed. A per-person preference kept in the browser only; the page works without storage. */
export type PanelState = { left: boolean; right: boolean };
type Store = Pick<Storage, "getItem" | "setItem">;

export const defaultPanels: PanelState = { left: false, right: false };
const key = "shadow.canvas.panels";

function browserStore(): Store | null {
  try { return globalThis.localStorage ?? null; } catch { return null; }
}

/** Read the collapsed flags; anything missing, malformed or blocked gives the defaults. */
export function readPanels(store: Store | null = browserStore()): PanelState {
  try {
    const value: unknown = JSON.parse(store?.getItem(key) ?? "null");
    if (value && typeof value === "object") {
      const { left, right } = value as Record<string, unknown>;
      return { left: left === true, right: right === true };
    }
  } catch { /* blocked storage or bad JSON */ }
  return { ...defaultPanels };
}

/** Remember the collapsed flags; a blocked or full storage is ignored. */
export function writePanels(state: PanelState, store: Store | null = browserStore()): void {
  try { store?.setItem(key, JSON.stringify({ left: state.left, right: state.right })); } catch { /* ignore */ }
}
