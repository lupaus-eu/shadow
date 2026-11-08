import { Maximize, Minus, Plus } from "lucide-react";

import { Button, IconButton } from "../../ui";
import { MAX_ZOOM, MIN_ZOOM, zoomPercent } from "./view";

export type CanvasToolbarTexts = {
  toolbar: string;
  zoomIn: string;
  zoomOut: string;
  fit: string;
  actualSize: string;
  /** Names the percentage readout, e.g. "Zoom 75 %". */
  zoomLevel: (percent: number) => string;
};

export type CanvasToolbarActions = { zoomIn(): void; zoomOut(): void; fit(): void; actualSize(): void };

/**
 * Zoom controls over the top left of the canvas: zoom out and in, the readout, Fit and 100 %. It only shows and asks; the view
 * itself is moved by `GraphNavigation`. Every control is a labelled button, and the readout is plain text that is not announced on each change.
 */
export function CanvasToolbar({ scale, texts, actions }: { scale: number; texts: CanvasToolbarTexts; actions: CanvasToolbarActions }) {
  const percent = zoomPercent(scale);
  return (
    <div role="toolbar" aria-label={texts.toolbar} className="absolute left-2 top-2 z-10 flex items-center gap-1 rounded-[var(--radius-card)] border border-line bg-surface p-1 shadow-[var(--shadow-overlay)]">
      <IconButton label={texts.zoomOut} icon={<Minus size={16} />} disabled={scale <= MIN_ZOOM + 0.0005} onClick={actions.zoomOut} />
      <output aria-label={texts.zoomLevel(percent)} aria-live="off" data-testid="zoom-readout" className="min-w-[52px] text-center text-[13px] font-medium tabular-nums text-ink">{percent} %</output>
      <IconButton label={texts.zoomIn} icon={<Plus size={16} />} disabled={scale >= MAX_ZOOM - 0.0005} onClick={actions.zoomIn} />
      <IconButton label={texts.fit} icon={<Maximize size={16} />} onClick={actions.fit} />
      <Button aria-label={texts.actualSize} title={texts.actualSize} onClick={actions.actualSize}>100 %</Button>
    </div>
  );
}
