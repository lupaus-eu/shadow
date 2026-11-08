import BaseRenderer from "diagram-js/lib/draw/BaseRenderer.js";
import type EventBus from "diagram-js/lib/core/EventBus.js";
import { append, attr, classes, create } from "tiny-svg";

import { isConnectionElement, isNodeElement, type ChangeMark, type GraphElement } from "./model";
import { FALLBACK_FILL, NODE_HEIGHT, NODE_WIDTH, arrowHead, contrastingInk, shapeKind, shapePath, shortenName, toPoints, wrapLabel, type Point } from "./shapes";

const NAME_LINE_LENGTH = 22;
/** Three lines of 22 hold a name of the 60 code points a label may have; with three lines the text is a little smaller to fit the 56 px node. */
const NAME_LINES = 3;
const BADGE: Record<Exclude<ChangeMark, null>, string> = { added: "+", updated: "~" };

function text(parent: SVGElement, value: string, attrs: Record<string, string | number>, className: string) {
  const element = create("text");
  attr(element, attrs);
  classes(element).add(className);
  element.textContent = value;
  append(parent, element);
  return element;
}

/** The connection's label sits on the middle of its longest segment, lifted a little above the line. */
function labelPoint(waypoints: Point[]): Point {
  let best = { from: waypoints[0], to: waypoints[1] ?? waypoints[0], length: -1 };
  for (let at = 0; at < waypoints.length - 1; at++) {
    const length = Math.hypot(waypoints[at + 1].x - waypoints[at].x, waypoints[at + 1].y - waypoints[at].y);
    if (length > best.length) best = { from: waypoints[at], to: waypoints[at + 1], length };
  }
  return { x: (best.from.x + best.to.x) / 2, y: (best.from.y + best.to.y) / 2 - 6 };
}

/**
 * Draws Shadow nodes and connections. A node's outline follows the node type's `shape` (an unknown value is a rounded rectangle) and its
 * fill the type's colour, with text in whichever of dark or white contrasts more. A connection is a solid or dashed line with arrowheads
 * where the connection type has them, and its type name as label. Selection, hover and the change marks are drawn by CSS classes and the
 * "+" and "~" badges, so no state is shown by colour alone.
 */
export class GraphRenderer extends BaseRenderer {
  static $inject = ["eventBus"];

  constructor(eventBus: EventBus) {
    super(eventBus, 1500);
  }

  canRender(element: unknown) {
    return isNodeElement(element) || isConnectionElement(element);
  }

  drawShape(visuals: SVGElement, shape: unknown): SVGElement {
    const element = shape as GraphElement;
    if (!isNodeElement(element)) throw new Error("GraphRenderer draws node shapes only");
    const { node, nodeType, change } = element.businessObject;
    const width = element.width || NODE_WIDTH;
    const height = element.height || NODE_HEIGHT;
    const kind = shapeKind(nodeType?.shape);
    const fill = nodeType?.color || FALLBACK_FILL;
    const ink = contrastingInk(fill);

    let body: SVGElement;
    if (kind === "ellipse") {
      body = create("ellipse");
      attr(body, { cx: width / 2, cy: height / 2, rx: width / 2, ry: height / 2 });
    } else if (kind === "diamond" || kind === "hexagon") {
      body = create("path");
      attr(body, { d: shapePath(kind, width, height) });
    } else {
      body = create("rect");
      attr(body, { width, height, rx: kind === "rectangle" ? 0 : 8, ry: kind === "rectangle" ? 0 : 8 });
    }
    attr(body, { fill });
    classes(body).add("shadow-node-body");
    attr(body, { "data-shape": kind });
    append(visuals, body);

    const name = shortenName(node.name);
    const lines = wrapLabel(name, NAME_LINE_LENGTH, NAME_LINES);
    const typeLine = nodeType?.name ?? "";
    const compact = lines.length > 2;
    const lineHeight = compact ? 12 : 14;
    const fontSize = compact ? 11 : 12;
    const block = lines.length * lineHeight + (typeLine ? 12 : 0);
    let y = (height - block) / 2 + (compact ? 10 : 11);
    const label = create("g");
    classes(label).add("shadow-node-label");
    attr(label, { fill: ink, "pointer-events": "none" });
    const title = create("title");
    title.textContent = typeLine ? `${node.name} (${typeLine})` : node.name;
    append(label, title);
    for (const line of lines) {
      text(label, line, { x: width / 2, y, "text-anchor": "middle", "font-size": fontSize, "font-weight": 600, fill: ink }, "shadow-node-name");
      y += lineHeight;
    }
    if (typeLine) text(label, typeLine, { x: width / 2, y: y - 1, "text-anchor": "middle", "font-size": 10, fill: ink, opacity: 0.85 }, "shadow-node-type");
    append(visuals, label);

    if (change) {
      const badge = create("g");
      classes(badge).add("shadow-change-badge");
      attr(badge, { "data-change": change, transform: `translate(${width - 4} 4)` });
      const disc = create("circle");
      attr(disc, { r: 9 });
      append(badge, disc);
      text(badge, BADGE[change], { y: 4, "text-anchor": "middle", "font-size": 13, "font-weight": 700 }, "shadow-change-glyph");
      append(visuals, badge);
    }

    // The group is a button for keyboards and screen readers, named like the old canvas named its nodes.
    const group = visuals.parentNode as SVGElement | null;
    if (group) attr(group, { role: "button", tabindex: 0, "aria-label": `${node.name} (${nodeType?.name ?? ""})` });
    return body;
  }

  drawConnection(visuals: SVGElement, connection: unknown): SVGElement {
    const element = connection as GraphElement;
    if (!isConnectionElement(element)) throw new Error("GraphRenderer draws connections only");
    const { connectionType, change } = element.businessObject;
    const waypoints = element.waypoints ?? [];
    const line = create("polyline");
    attr(line, { points: toPoints(waypoints), fill: "none" });
    if (connectionType?.style === "dashed") attr(line, { "stroke-dasharray": "6 4" });
    classes(line).add("shadow-connection-line");
    append(visuals, line);

    if (waypoints.length >= 2) {
      const ends: [string | undefined, Point, Point][] = [
        [connectionType?.target_end, waypoints[waypoints.length - 2], waypoints[waypoints.length - 1]],
        [connectionType?.source_end, waypoints[1], waypoints[0]],
      ];
      for (const [style, from, tip] of ends) {
        if (style !== "arrow") continue;
        const head = create("polygon");
        attr(head, { points: toPoints(arrowHead(from, tip)) });
        classes(head).add("shadow-connection-arrow");
        append(visuals, head);
      }
      const at = labelPoint(waypoints);
      const mark = change ? `${BADGE[change]} ` : "";
      const name = connectionType?.name ?? "";
      if (name || mark) text(visuals, `${mark}${shortenName(name)}`, { x: at.x, y: at.y, "text-anchor": "middle", "font-size": 11 }, "shadow-connection-label");
    }
    return line;
  }

  getShapePath(shape: unknown): string {
    const element = shape as GraphElement;
    const kind = isNodeElement(element) ? shapeKind(element.businessObject.nodeType?.shape) : "roundrectangle";
    return shapePath(kind, element.width, element.height, element.x, element.y);
  }

  getConnectionPath(connection: unknown): string {
    const waypoints = (connection as GraphElement).waypoints ?? [];
    return waypoints.map((point, at) => `${at === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ");
  }
}
