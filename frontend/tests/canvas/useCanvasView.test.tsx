import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { useCanvasView } from "../../src/models/canvas/useCanvasView.ts";
import type { ViewMemory } from "../../src/models/canvas/view.ts";

let root: Root | null = null;
afterEach(() => { act(() => root?.unmount()); root = null; });

function mount(initial: string) {
  const result: { current: ViewMemory } = { current: undefined as unknown as ViewMemory };
  root = createRoot(document.createElement("div"));
  function Probe({ line }: { line: string }) { result.current = useCanvasView(line); return null; }
  const render = (key: string) => act(() => root!.render(createElement(Probe, { line: key })));
  render(initial);
  return { result, render };
}

describe("useCanvasView", () => {
  it("keeps the view and the fitted flag across renders of the same line (saves and reloads)", () => {
    const { result, render } = mount("o|m|line");
    const first = result.current;
    first.markFitted();
    first.remember({ x: 5, y: 6, scale: 2 });
    render("o|m|line");
    expect(result.current).toBe(first);
    expect(result.current.view).toEqual({ x: 5, y: 6, scale: 2 });
    expect(result.current.fitted).toBe(true);
  });

  it("resets when another line is shown (the ?line= parameter changes)", () => {
    const { result, render } = mount("o|m|base");
    result.current.markFitted();
    result.current.remember({ x: 5, y: 6, scale: 2 });
    render("o|m|scenario");
    expect(result.current.view).toBeNull();
    expect(result.current.fitted).toBe(false);
    expect(result.current.key).toBe("o|m|scenario");
  });

  it("resets when the tab is left and opened again (a new mount)", () => {
    const { result } = mount("o|m|l");
    result.current.markFitted();
    act(() => root!.unmount());
    root = null;
    const again = mount("o|m|l");
    expect(again.result.current.fitted).toBe(false);
    expect(again.result.current.view).toBeNull();
  });
});
