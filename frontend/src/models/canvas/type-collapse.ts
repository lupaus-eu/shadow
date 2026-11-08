/**
 * Which type groups of the Structure canvas' left panel the person collapsed or opened, per model. A per-person preference kept in the
 * browser only (`shadow.canvas.typeCollapse`); only types the person has toggled are stored, the rest follow the default (a type without
 * nodes starts collapsed). Every read and write is guarded: blocked or full storage gives the defaults and the panel still works.
 */
type Store = Pick<Storage, "getItem" | "setItem">;
export type TypeCollapse = Record<string, boolean>;

const key = "shadow.canvas.typeCollapse";

function browserStore(): Store | null {
  try { return globalThis.localStorage ?? null; } catch { return null; }
}

function readAll(store: Store | null): Record<string, TypeCollapse> {
  try {
    const value: unknown = JSON.parse(store?.getItem(key) ?? "null");
    if (value && typeof value === "object" && !Array.isArray(value)) {
      const result: Record<string, TypeCollapse> = {};
      for (const [modelId, types] of Object.entries(value)) result[modelId] = clean(types);
      return result;
    }
  } catch { /* blocked storage or bad JSON */ }
  return {};
}

function clean(value: unknown): TypeCollapse {
  const result: TypeCollapse = {};
  if (value && typeof value === "object" && !Array.isArray(value)) {
    for (const [typeId, collapsed] of Object.entries(value)) if (typeof collapsed === "boolean") result[typeId] = collapsed;
  }
  return result;
}

/** The stored choices for a model; anything missing, malformed or blocked gives none. */
export function readTypeCollapse(modelId: string, store: Store | null = browserStore()): TypeCollapse {
  return readAll(store)[modelId] ?? {};
}

/** Remembers the choices of a model next to those of other models; a blocked or full storage is ignored. */
export function writeTypeCollapse(modelId: string, state: TypeCollapse, store: Store | null = browserStore()): void {
  try { store?.setItem(key, JSON.stringify({ ...readAll(store), [modelId]: clean(state) })); } catch { /* ignore */ }
}
