/**
 * The Structure canvas keymap: our keys, on top of the diagram-js `keyboard` service (which only delivers key events while focus is
 * inside the drawing, so the panels' text fields never reach it; `isEditableTarget` guards the rest). A binding names its keys and
 * runs an action; later tickets register their own with `Keymap.register` (see the map in docs/design/ui-foundation.md).
 */

export type KeyBinding = {
  /** A unique name, used to unregister and in tests. */
  id: string;
  /** Values of `KeyboardEvent.key`, compared in lower case ("+", "f", "ArrowLeft" is "arrowleft"). */
  keys: string[];
  /** Return false to let the next binding for the key try; anything else (including nothing) means handled. */
  run(event: KeyboardEvent): boolean | void;
};

/** True for a text field, a select, an editable element or anything inside one: keys there belong to the field. */
export function isEditableTarget(target: EventTarget | null): boolean {
  const element = target as (Element & { isContentEditable?: boolean }) | null;
  if (!element || typeof element.tagName !== "string") return false;
  if (element.isContentEditable) return true;
  if (/^(input|textarea|select)$/i.test(element.tagName)) return true;
  return typeof element.closest === "function" && element.closest("input, textarea, select, [contenteditable=''], [contenteditable='true']") !== null;
}

/**
 * Key bindings tried newest first, so a later ticket can take over a key. Chords with Ctrl, Cmd or Alt are never ours here (undo, redo,
 * select all and the browser's own belong to other owners); Shift is allowed because "+" needs it on many keyboards and it enlarges steps.
 */
export class Keymap {
  private readonly bindings: KeyBinding[] = [];

  /** Adds a binding and returns the function that removes it. A second binding with the same id is a mistake and throws. */
  register(binding: KeyBinding): () => void {
    if (this.bindings.some((existing) => existing.id === binding.id)) throw new Error(`key binding "${binding.id}" is already registered`);
    this.bindings.unshift({ ...binding, keys: binding.keys.map((key) => key.toLowerCase()) });
    return () => { const index = this.bindings.findIndex((existing) => existing.id === binding.id); if (index >= 0) this.bindings.splice(index, 1); };
  }

  /** The ids registered for a key (for tests and the documentation check). */
  idsFor(key: string): string[] {
    return this.bindings.filter((binding) => binding.keys.includes(key.toLowerCase())).map((binding) => binding.id);
  }

  /** Runs the first binding for the event's key that handles it. Returns true when one did (the caller then prevents the default action). */
  handle(event: KeyboardEvent): boolean {
    if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing || isEditableTarget(event.target)) return false;
    const key = event.key.toLowerCase();
    for (const binding of this.bindings) {
      if (binding.keys.includes(key) && binding.run(event) !== false) return true;
    }
    return false;
  }
}

/** What the navigation keys do to the drawing. `GraphKeys` implements it on the diagram. */
export type NavigationActions = {
  zoomStep(direction: 1 | -1): void;
  actualSize(): void;
  fit(): void;
  /** Pans by screen pixels. */
  pan(dx: number, dy: number): void;
  /** Moves the selected nodes one step (`large` is the bigger step); false when no node is selected or the canvas is read-only. */
  moveSelection(dx: -1 | 0 | 1, dy: -1 | 0 | 1, large: boolean): boolean;
};

/** Pixels the drawing pans per arrow press, and with Shift. */
export const PAN_STEP = 50;
export const PAN_STEP_LARGE = 200;

/** `+` `-` `0` `F` and the arrows. `Esc` is registered by the canvas, which knows about connect mode. */
export function navigationBindings(actions: NavigationActions): KeyBinding[] {
  const arrow = (id: string, key: string, dx: -1 | 0 | 1, dy: -1 | 0 | 1): KeyBinding => ({
    id,
    keys: [key],
    run: (event) => {
      if (actions.moveSelection(dx, dy, event.shiftKey)) return true;
      // The drawing follows the arrow: pressing right brings what is to the right into view.
      const step = event.shiftKey ? PAN_STEP_LARGE : PAN_STEP;
      actions.pan(-dx * step, -dy * step);
      return true;
    },
  });
  return [
    { id: "navigation.zoom-in", keys: ["+", "="], run: () => actions.zoomStep(1) },
    { id: "navigation.zoom-out", keys: ["-", "_"], run: () => actions.zoomStep(-1) },
    { id: "navigation.actual-size", keys: ["0"], run: () => actions.actualSize() },
    { id: "navigation.fit", keys: ["f"], run: () => actions.fit() },
    arrow("navigation.left", "ArrowLeft", -1, 0),
    arrow("navigation.right", "ArrowRight", 1, 0),
    arrow("navigation.up", "ArrowUp", 0, -1),
    arrow("navigation.down", "ArrowDown", 0, 1),
  ];
}
