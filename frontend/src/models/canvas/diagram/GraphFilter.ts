import type Canvas from "diagram-js/lib/core/Canvas.js";

import type { CanvasFilter } from "../type-list";
import { isConnectionElement, isNodeElement, type GraphElement, type RegistryLike } from "./model";

export const HIDDEN_MARKER = "shadow-hidden";
export const DIM_MARKER = "shadow-dim";
export const MATCH_MARKER = "shadow-match";

/**
 * Hides and dims elements with markers (classes on the element's group), never by removing them from the model: a node of a hidden type
 * and every connection that touches one are `shadow-hidden`; while a search is active matching nodes are `shadow-match` and the rest
 * `shadow-dim` (a connection stays undimmed when one of its ends matches). `apply` is idempotent, so it can run after every load.
 */
export class GraphFilter {
  static $inject = ["canvas", "elementRegistry"];

  constructor(private readonly canvas: Canvas, private readonly registry: RegistryLike) {}

  apply(filter: CanvasFilter): void {
    const { hiddenTypeIds, matchIds } = filter;
    const hiddenNode = (node: GraphElement | undefined) => !!node && isNodeElement(node) && hiddenTypeIds.has(node.businessObject.node.node_type_id);
    const matches = (node: GraphElement | undefined) => !!node && !!matchIds?.has(node.id);
    for (const element of this.registry.filter((item) => !!item.parent)) {
      let hidden = false;
      let match = false;
      let dim = false;
      if (isNodeElement(element)) {
        hidden = hiddenNode(element);
        match = !hidden && matches(element);
        dim = !hidden && !!matchIds && !match;
      } else if (isConnectionElement(element)) {
        hidden = hiddenNode(element.source) || hiddenNode(element.target);
        dim = !hidden && !!matchIds && !matches(element.source) && !matches(element.target);
      }
      this.mark(element, HIDDEN_MARKER, hidden);
      this.mark(element, MATCH_MARKER, match);
      this.mark(element, DIM_MARKER, dim);
    }
  }

  private mark(element: GraphElement, marker: string, on: boolean) {
    const has = this.canvas.hasMarker(element as never, marker);
    if (on && !has) this.canvas.addMarker(element as never, marker);
    if (!on && has) this.canvas.removeMarker(element as never, marker);
  }
}
