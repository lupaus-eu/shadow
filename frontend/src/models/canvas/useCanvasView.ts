import { useState } from "react";

import { ViewMemory } from "./view";

/**
 * The memory of the canvas view for one line. It lives as long as the Structure tab is open on that line: saves and reloads of the line
 * keep it (the canvas also survives them untouched), switching to another line (`?line=`) or leaving the tab gives a new, empty one,
 * so the next load fits again. It is held in memory only, never in browser storage.
 */
export function useCanvasView(key: string): ViewMemory {
  const [memory, setMemory] = useState(() => new ViewMemory(key));
  if (memory.key === key) return memory;
  const next = new ViewMemory(key);
  setMemory(next);
  return next;
}
