import { describe, expect, it, vi } from "vitest";

import { isEditableTarget, Keymap, navigationBindings, PAN_STEP, PAN_STEP_LARGE, type NavigationActions } from "../../src/models/canvas/keymap.ts";

const press = (key: string, init: KeyboardEventInit = {}, target?: Element) => {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init });
  if (target) Object.defineProperty(event, "target", { value: target });
  return event;
};

function setup(moveSelection = false) {
  const actions: NavigationActions = { zoomStep: vi.fn(), actualSize: vi.fn(), fit: vi.fn(), pan: vi.fn(), moveSelection: vi.fn(() => moveSelection) };
  const keymap = new Keymap();
  for (const binding of navigationBindings(actions)) keymap.register(binding);
  return { actions, keymap };
}

describe("navigation keys", () => {
  it("+ and - zoom a step, 0 is 100 %, F fits", () => {
    const { actions, keymap } = setup();
    expect(keymap.handle(press("+", { shiftKey: true }))).toBe(true);
    expect(keymap.handle(press("="))).toBe(true);
    expect(keymap.handle(press("-"))).toBe(true);
    expect(keymap.handle(press("0"))).toBe(true);
    expect(keymap.handle(press("f"))).toBe(true);
    expect(keymap.handle(press("F", { shiftKey: true }))).toBe(true);
    expect(actions.zoomStep).toHaveBeenNthCalledWith(1, 1);
    expect(actions.zoomStep).toHaveBeenNthCalledWith(2, 1);
    expect(actions.zoomStep).toHaveBeenNthCalledWith(3, -1);
    expect(actions.actualSize).toHaveBeenCalledOnce();
    expect(actions.fit).toHaveBeenCalledTimes(2);
  });

  it("arrows pan the drawing when nothing can be moved, Shift pans further", () => {
    const { actions, keymap } = setup(false);
    keymap.handle(press("ArrowRight"));
    keymap.handle(press("ArrowDown", { shiftKey: true }));
    expect(actions.pan).toHaveBeenNthCalledWith(1, -PAN_STEP, -0);
    expect(actions.pan).toHaveBeenNthCalledWith(2, -0, -PAN_STEP_LARGE);
  });

  it("arrows move the selection instead of panning when nodes are selected", () => {
    const { actions, keymap } = setup(true);
    expect(keymap.handle(press("ArrowLeft"))).toBe(true);
    expect(keymap.handle(press("ArrowUp", { shiftKey: true }))).toBe(true);
    expect(actions.moveSelection).toHaveBeenNthCalledWith(1, -1, 0, false);
    expect(actions.moveSelection).toHaveBeenNthCalledWith(2, 0, -1, true);
    expect(actions.pan).not.toHaveBeenCalled();
  });

  it("unknown keys and chords with Ctrl, Cmd or Alt are left alone", () => {
    const { actions, keymap } = setup();
    expect(keymap.handle(press("x"))).toBe(false);
    expect(keymap.handle(press("f", { ctrlKey: true }))).toBe(false);
    expect(keymap.handle(press("0", { metaKey: true }))).toBe(false);
    expect(keymap.handle(press("-", { altKey: true }))).toBe(false);
    expect(actions.fit).not.toHaveBeenCalled();
    expect(actions.zoomStep).not.toHaveBeenCalled();
  });
});

describe("text fields", () => {
  const field = (html: string) => {
    const host = document.createElement("div");
    host.innerHTML = html;
    document.body.append(host);
    return host.firstElementChild as HTMLElement;
  };

  it("ignores every key inside inputs, textareas, selects and editable elements", () => {
    const { actions, keymap } = setup();
    for (const element of [field("<input>"), field("<textarea></textarea>"), field("<select><option>a</option></select>"), field("<div contenteditable='true'><span>x</span></div>").firstElementChild!]) {
      expect(isEditableTarget(element)).toBe(true);
      expect(keymap.handle(press("f", {}, element))).toBe(false);
      expect(keymap.handle(press("+", {}, element))).toBe(false);
      expect(keymap.handle(press("ArrowLeft", {}, element))).toBe(false);
    }
    expect(actions.fit).not.toHaveBeenCalled();
    expect(actions.zoomStep).not.toHaveBeenCalled();
    expect(actions.pan).not.toHaveBeenCalled();
  });

  it("does not treat buttons, svg shapes or the page as text fields", () => {
    expect(isEditableTarget(field("<button>x</button>"))).toBe(false);
    expect(isEditableTarget(document.createElementNS("http://www.w3.org/2000/svg", "g"))).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
    expect(isEditableTarget(document.body)).toBe(false);
  });
});

describe("registering keys", () => {
  it("lets a later ticket add a key, take over one, and remove it again", () => {
    const { keymap } = setup();
    const added = vi.fn();
    const remove = keymap.register({ id: "later.c", keys: ["c"], run: added });
    expect(keymap.handle(press("C"))).toBe(true);
    expect(added).toHaveBeenCalledOnce();
    remove();
    expect(keymap.handle(press("c"))).toBe(false);
  });

  it("tries the newest binding first and falls through when it returns false", () => {
    const { actions, keymap } = setup();
    keymap.register({ id: "later.f", keys: ["f"], run: () => false });
    expect(keymap.handle(press("f"))).toBe(true);
    expect(actions.fit).toHaveBeenCalledOnce();
    keymap.register({ id: "later.f2", keys: ["f"], run: () => undefined });
    expect(keymap.handle(press("f"))).toBe(true);
    expect(actions.fit).toHaveBeenCalledOnce();
  });

  it("refuses two bindings with the same id", () => {
    const { keymap } = setup();
    expect(() => keymap.register({ id: "navigation.fit", keys: ["g"], run: () => undefined })).toThrow(/already registered/);
    expect(keymap.idsFor("f")).toEqual(["navigation.fit"]);
  });
});
