import { describe, expect, it } from "vitest";

import {
  clampZoom, FIT_PADDING, fitView, MAX_ZOOM, MIN_ZOOM, panView, pinchView, prefersReducedMotion, stepScale, tweenView, unionBounds, ViewMemory, wheelFactor, zoomAround, zoomPercent, type View,
} from "../../src/models/canvas/view.ts";

const view = (x = 0, y = 0, scale = 1): View => ({ x, y, scale });

describe("zoom limits", () => {
  it("clamps to 10 % and 400 %", () => {
    expect(MIN_ZOOM).toBe(0.1);
    expect(MAX_ZOOM).toBe(4);
    expect(clampZoom(0.01)).toBe(0.1);
    expect(clampZoom(40)).toBe(4);
    expect(clampZoom(1.5)).toBe(1.5);
    expect(clampZoom(Number.NaN)).toBe(1);
  });

  it("the readout is the rounded percentage of the scale", () => {
    expect(zoomPercent(1)).toBe(100);
    expect(zoomPercent(0.1)).toBe(10);
    expect(zoomPercent(4)).toBe(400);
    expect(zoomPercent(0.3333)).toBe(33);
  });

  it("steps never leave the limits and a step in then out returns", () => {
    expect(stepScale(4, 1)).toBe(4);
    expect(stepScale(0.1, -1)).toBe(0.1);
    expect(stepScale(stepScale(1, 1), -1)).toBeCloseTo(1, 10);
  });

  it("zooming keeps the point under the anchor where it is, and clamps", () => {
    const start = view(100, 50, 1);
    const anchor = { x: 200, y: 120 };
    const next = zoomAround(start, 2, anchor);
    expect(next.scale).toBe(2);
    // Canvas point under the anchor before and after.
    expect(start.x + anchor.x / start.scale).toBeCloseTo(next.x + anchor.x / next.scale);
    expect(start.y + anchor.y / start.scale).toBeCloseTo(next.y + anchor.y / next.scale);
    expect(zoomAround(start, 99, anchor).scale).toBe(4);
    expect(zoomAround(start, 0, anchor).scale).toBe(0.1);
  });

  it("a wheel turned up zooms in, down zooms out, in proportion and capped", () => {
    expect(wheelFactor(-100, 0, false)).toBeGreaterThan(1);
    expect(wheelFactor(100, 0, false)).toBeLessThan(1);
    expect(wheelFactor(-100, 0, true)).toBeGreaterThan(wheelFactor(-100, 0, false));
    expect(wheelFactor(-100000, 0, false)).toBe(wheelFactor(-240, 0, false));
    expect(wheelFactor(-3, 1, false)).toBeCloseTo(wheelFactor(-48, 0, false));
  });
});

describe("pan", () => {
  it("moves the content by screen pixels whatever the zoom", () => {
    expect(panView(view(0, 0, 2), 100, -40)).toEqual({ x: -50, y: 20, scale: 2 });
  });
});

describe("fit", () => {
  const size = { width: 1000, height: 600 };

  it("shows the whole graph with padding, centred", () => {
    const bounds = { x: 0, y: 0, width: 2000, height: 600 };
    const fitted = fitView(bounds, size)!;
    expect(fitted.scale).toBeCloseTo((1000 - 2 * FIT_PADDING) / 2000);
    const left = (bounds.x - fitted.x) * fitted.scale;
    const right = (bounds.x + bounds.width - fitted.x) * fitted.scale;
    expect(left).toBeGreaterThanOrEqual(FIT_PADDING - 0.001);
    expect(size.width - right).toBeGreaterThanOrEqual(FIT_PADDING - 0.001);
    expect((left + right) / 2).toBeCloseTo(size.width / 2);
  });

  it("does not zoom in past 100 % and centres a small graph", () => {
    const fitted = fitView({ x: 100, y: 100, width: 100, height: 50 }, size)!;
    expect(fitted.scale).toBe(1);
    expect(fitted.x + size.width / 2).toBeCloseTo(150);
    expect(fitted.y + size.height / 2).toBeCloseTo(125);
  });

  it("stops at the lower limit for a huge graph", () => {
    expect(fitView({ x: 0, y: 0, width: 1e6, height: 1e6 }, size)!.scale).toBe(0.1);
  });

  it("an empty graph gives 100 % at the origin and no size gives nothing", () => {
    expect(fitView(null, size)).toEqual({ x: 0, y: 0, scale: 1 });
    expect(fitView({ x: 0, y: 0, width: 1, height: 1 }, { width: 0, height: 0 })).toBeNull();
  });

  it("unionBounds covers every rectangle", () => {
    expect(unionBounds([])).toBeNull();
    expect(unionBounds([{ x: 0, y: 0, width: 10, height: 10 }, { x: 50, y: -20, width: 10, height: 10 }])).toEqual({ x: 0, y: -20, width: 60, height: 30 });
  });
});

describe("pinch", () => {
  it("doubling the distance doubles the scale around the midpoint, and moving the midpoint pans", () => {
    const start = { view: view(0, 0, 1), mid: { x: 100, y: 100 }, distance: 50 };
    const doubled = pinchView(start, { mid: { x: 100, y: 100 }, distance: 100 });
    expect(doubled.scale).toBe(2);
    expect(doubled.x + 100 / doubled.scale).toBeCloseTo(100);
    const moved = pinchView(start, { mid: { x: 160, y: 100 }, distance: 50 });
    expect(moved).toEqual({ scale: 1, x: -60, y: 0 });
    expect(pinchView(start, { mid: start.mid, distance: 5000 }).scale).toBe(4);
  });
});

describe("reduced motion", () => {
  const fakeClock = () => {
    let time = 0;
    const frames: ((time: number) => void)[] = [];
    return { frames, advance: (ms: number) => { time += ms; frames.splice(0).forEach((frame) => frame(time)); }, clock: { now: () => time, request: (callback: (time: number) => void) => frames.push(callback), cancel: () => { frames.length = 0; } } };
  };

  it("is read from the prefers-reduced-motion media query", () => {
    expect(prefersReducedMotion((query) => ({ matches: query.includes("reduce") }))).toBe(true);
    expect(prefersReducedMotion((query) => ({ matches: !query.includes("reduce") }))).toBe(false);
    expect(prefersReducedMotion(undefined)).toBe(false);
  });

  it("jumps to the end at once and schedules no frame when motion is reduced", () => {
    const { clock, frames } = fakeClock();
    const seen: View[] = [];
    tweenView(view(), view(300, 0, 2), (next) => seen.push(next), { reduced: true, clock });
    expect(seen).toEqual([view(300, 0, 2)]);
    expect(frames).toHaveLength(0);
  });

  it("eases over several frames and ends exactly on the target when motion is allowed", () => {
    const { clock, advance } = fakeClock();
    const seen: View[] = [];
    tweenView(view(), view(300, 0, 2), (next) => seen.push(next), { reduced: false, clock, duration: 100 });
    expect(seen).toHaveLength(0);
    advance(40);
    expect(seen).toHaveLength(1);
    expect(seen[0].x).toBeGreaterThan(0);
    expect(seen[0].x).toBeLessThan(300);
    advance(100);
    expect(seen.at(-1)).toEqual(view(300, 0, 2));
  });

  it("can be stopped", () => {
    const { clock, advance } = fakeClock();
    const seen: View[] = [];
    const stop = tweenView(view(), view(300), (next) => seen.push(next), { reduced: false, clock, duration: 100 });
    advance(20);
    stop();
    advance(200);
    expect(seen).toHaveLength(1);
  });
});

describe("ViewMemory", () => {
  it("starts empty and unfitted", () => {
    const memory = new ViewMemory("o|m|l");
    expect(memory.view).toBeNull();
    expect(memory.fitted).toBe(false);
  });

  it("keeps the last view and the fitted flag, and clamps a remembered scale", () => {
    const memory = new ViewMemory("o|m|l");
    memory.markFitted();
    memory.remember(view(10, 20, 2));
    memory.remember(view(30, 40, 99));
    expect(memory.view).toEqual(view(30, 40, 4));
    expect(memory.fitted).toBe(true);
  });

  it("hands out copies", () => {
    const memory = new ViewMemory("k");
    memory.remember(view(1, 2, 1));
    memory.view!.x = 99;
    expect(memory.view!.x).toBe(1);
  });
});
