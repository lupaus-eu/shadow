import { IMAGE_PADDING, IMAGE_SCALE, LEGEND_ROW_PX, TITLE_PX, canvasSize, layoutLegend, type LegendEntry } from "./png";

const STYLE_PROPERTIES = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-opacity", "opacity", "font-size", "font-weight", "text-anchor", "dominant-baseline", "filter", "display", "visibility"];
const FONT = "Helvetica, Arial, sans-serif";

/** A copy of the SVG with the computed paint of every element written inline, because a standalone SVG image loses the page's stylesheet. */
function withInlineStyles(source: SVGSVGElement, sizePx: number): SVGSVGElement {
  const clone = source.cloneNode(true) as SVGSVGElement;
  const from = [source, ...Array.from(source.querySelectorAll("*"))];
  const to = [clone, ...Array.from(clone.querySelectorAll("*"))];
  from.forEach((element, index) => {
    const computed = getComputedStyle(element);
    const target = to[index] as SVGElement;
    for (const property of STYLE_PROPERTIES) target.style.setProperty(property, computed.getPropertyValue(property));
    target.style.setProperty("font-family", FONT);
    target.removeAttribute("class");
    target.removeAttribute("tabindex");
  });
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(sizePx));
  clone.setAttribute("height", String(sizePx));
  return clone;
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("The circle could not be drawn."));
    image.src = url;
  });
}

/** Draw the circle with a title, a subtitle, and a legend onto a white canvas at 2× and return it as a PNG blob. */
export async function circleImage(svg: SVGSVGElement, title: string, subtitle: string, legend: LegendEntry[]): Promise<Blob> {
  const sizePx = Math.round(svg.getBoundingClientRect().width);
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(withInlineStyles(svg, sizePx))], { type: "image/svg+xml;charset=utf-8" }));
  try {
    const image = await loadImage(url);
    const probe = document.createElement("canvas").getContext("2d");
    if (!probe) throw new Error("No canvas");
    probe.font = `13px ${FONT}`;
    const maxWidth = sizePx;
    const layout = layoutLegend(legend, maxWidth, (text) => probe.measureText(text).width);
    const size = canvasSize(sizePx, layout.rows);
    const canvas = document.createElement("canvas");
    canvas.width = size.width;
    canvas.height = size.height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("No canvas");
    context.scale(IMAGE_SCALE, IMAGE_SCALE);
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, size.width, size.height);
    context.fillStyle = "#17212b";
    context.textBaseline = "alphabetic";
    context.font = `600 20px ${FONT}`;
    context.fillText(title, IMAGE_PADDING, IMAGE_PADDING + 22);
    context.font = `13px ${FONT}`;
    context.fillStyle = "#56636e";
    context.fillText(subtitle, IMAGE_PADDING, IMAGE_PADDING + 44);
    context.drawImage(image, IMAGE_PADDING, IMAGE_PADDING + TITLE_PX, sizePx, sizePx);
    context.font = `13px ${FONT}`;
    for (const entry of layout.entries) {
      const x = IMAGE_PADDING + entry.x;
      const y = size.legendTop + entry.row * LEGEND_ROW_PX + 14;
      let textX = x;
      if (entry.color) { context.fillStyle = entry.color; context.fillRect(x, y - 11, 14, 14); textX = x + 20; }
      context.fillStyle = "#17212b";
      context.fillText(entry.label, textX, y);
    }
    return await new Promise<Blob>((resolve, reject) => canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("The image is empty."))), "image/png"));
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Save a blob under a file name through a temporary link. */
export function saveBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
