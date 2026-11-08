import type ContextPad from "diagram-js/lib/features/context-pad/ContextPad.js";

import type { GraphDrawing } from "./GraphDrawing";
import { isNodeElement, type GraphElement } from "./model";

/** Line icons (Lucide's "arrow-right" and "trash-2") as markup, because the pad's entries are plain HTML. */
const ICONS = {
  connect: '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
  remove: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',
};

function entryHtml(name: keyof typeof ICONS, label: string): string {
  const escaped = label.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  return `<button type="button" class="entry shadow-pad-entry shadow-pad-${name}" draggable="true" aria-label="${escaped}" title="${escaped}"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${ICONS[name]}</svg></button>`;
}

/**
 * The buttons beside the selected element: a node has Connect (drag from it to another node, or click it and then the node) and Delete;
 * a connection has Delete. Nothing is offered on a read-only canvas. The pad asks `GraphDrawing`, which asks the parent.
 */
export class GraphContextPad {
  static $inject = ["contextPad", "graphDrawing"];

  constructor(contextPad: ContextPad, private readonly drawing: GraphDrawing) {
    contextPad.registerProvider(this as never);
  }

  getContextPadEntries(element: GraphElement) {
    if (!this.drawing.canEdit(element)) return {};
    const texts = this.drawing.texts;
    const entries: Record<string, unknown> = {};
    if (isNodeElement(element)) {
      const start = (event: Event, target: GraphElement) => this.drawing.startConnect(event, target);
      entries.connect = { group: "edit", title: texts.connect, html: entryHtml("connect", texts.connect), action: { click: start, dragstart: start } };
    }
    entries.remove = { group: "edit", title: texts.remove, html: entryHtml("remove", texts.remove), action: { click: (_event: Event, target: GraphElement) => this.drawing.handlers?.remove([target.id]) } };
    return entries;
  }
}
