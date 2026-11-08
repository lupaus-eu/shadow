// jsdom has no SVG layout and no SVG transform lists. diagram-js and tiny-svg need both, so the few calls they make get small stand-ins:
// measuring answers 0, and a transform list writes its combined matrix into the `transform` attribute, which is what a browser would show.
type Matrix = { a: number; b: number; c: number; d: number; e: number; f: number };
const identity = (): Matrix => ({ a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 });
const multiply = (m: Matrix, n: Matrix): Matrix => ({
  a: m.a * n.a + m.c * n.b, b: m.b * n.a + m.d * n.b, c: m.a * n.c + m.c * n.d, d: m.b * n.c + m.d * n.d, e: m.a * n.e + m.c * n.f + m.e, f: m.b * n.e + m.d * n.f + m.f,
});

function transformItem() {
  return {
    type: 0,
    matrix: identity(),
    angle: 0,
    setMatrix(matrix: Matrix) { this.matrix = { ...matrix }; },
    setTranslate(x: number, y: number) { this.matrix = { ...identity(), e: x, f: y }; },
    setScale(x: number, y: number) { this.matrix = { ...identity(), a: x, d: y }; },
    setRotate(angle: number) { const r = (angle * Math.PI) / 180; this.matrix = { a: Math.cos(r), b: Math.sin(r), c: -Math.sin(r), d: Math.cos(r), e: 0, f: 0 }; },
  };
}

class FakeSVGMatrix {
  a = 1; b = 0; c = 0; d = 1; e = 0; f = 0;
  private static of(matrix: Matrix) { return Object.assign(new FakeSVGMatrix(), matrix); }
  // `canvas.viewbox(box)` builds its matrix as `createSVGMatrix().scale(s).translate(x, y)`.
  scale(factor: number) { return FakeSVGMatrix.of(multiply(this, { a: factor, b: 0, c: 0, d: factor, e: 0, f: 0 })); }
  translate(x: number, y: number) { return FakeSVGMatrix.of(multiply(this, { a: 1, b: 0, c: 0, d: 1, e: x, f: y })); }
}
(globalThis as { SVGMatrix?: unknown }).SVGMatrix ??= FakeSVGMatrix;

function install() {
  const svg = globalThis.SVGSVGElement?.prototype as unknown as Record<string, unknown> | undefined;
  const element = globalThis.SVGElement?.prototype as unknown as Record<string, unknown> | undefined;
  if (!svg || !element) return;
  svg.createSVGTransform = transformItem;
  svg.createSVGTransformFromMatrix = (matrix: Matrix) => { const item = transformItem(); item.setMatrix(matrix); return item; };
  svg.createSVGMatrix = () => new FakeSVGMatrix();
  svg.createSVGPoint = () => ({ x: 0, y: 0, matrixTransform() { return this; } });
  if (!element.getBBox) element.getBBox = () => ({ x: 0, y: 0, width: 0, height: 0 });
  if (!Object.getOwnPropertyDescriptor(element, "transform")) {
    Object.defineProperty(element, "transform", {
      get(this: Element & { __items?: ReturnType<typeof transformItem>[] }) {
        const owner = this;
        const items = (owner.__items ??= []);
        const write = () => {
          const m = items.reduce((total, item) => multiply(total, item.matrix), identity());
          owner.setAttribute("transform", `matrix(${m.a} ${m.b} ${m.c} ${m.d} ${m.e} ${m.f})`);
        };
        return {
          baseVal: {
            get numberOfItems() { return items.length; },
            createSVGTransformFromMatrix(matrix: Matrix) { const item = transformItem(); item.setMatrix(matrix); return item; },
            clear() { items.length = 0; write(); },
            appendItem(item: ReturnType<typeof transformItem>) { items.push(item); write(); return item; },
            consolidate() { const item = transformItem(); item.setMatrix(items.reduce((total, one) => multiply(total, one.matrix), identity())); return item; },
          },
        };
      },
    });
  }
}
install();
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
