/** The displays of the Planning Window (Yearclock V2 P5, ADR-0029). */
export const ALL_DISPLAYS = ["circle", "timeline", "list", "agenda"] as const;
export type Display = (typeof ALL_DISPLAYS)[number];

/** The displays that exist; each display's ticket adds its own entry, so the switch never offers an empty one. */
const BUILT: ReadonlySet<Display> = new Set<Display>(["circle", "timeline", "list", "agenda"]);
export const AVAILABLE_DISPLAYS: readonly Display[] = ALL_DISPLAYS.filter((display) => BUILT.has(display));

export const DEFAULT_DISPLAY: Display = "circle";

type Storage = { getItem(key: string): string | null; setItem(key: string, value: string): void; removeItem(key: string): void };

const key = (yearclockId: string) => `yearclock.display.${yearclockId}`;

/** The display chosen for this Yearclock in this browser; the circle when none is stored, it is unknown, or storage is blocked. */
export function loadDisplay(yearclockId: string, available: readonly Display[] = AVAILABLE_DISPLAYS, storage: Storage | undefined = globalThis.localStorage): Display {
  try {
    const stored = storage?.getItem(key(yearclockId));
    return (available as readonly string[]).includes(stored ?? "") ? (stored as Display) : DEFAULT_DISPLAY;
  } catch {
    return DEFAULT_DISPLAY;
  }
}

export function saveDisplay(yearclockId: string, display: Display, storage: Storage | undefined = globalThis.localStorage): void {
  try {
    if (display === DEFAULT_DISPLAY) storage?.removeItem(key(yearclockId));
    else storage?.setItem(key(yearclockId), display);
  } catch {
    // Blocked storage: the choice is simply not remembered.
  }
}
