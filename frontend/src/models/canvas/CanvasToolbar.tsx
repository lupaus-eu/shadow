import { BoxSelect, Maximize, Minus, MoveRight, Plus, Redo2, Undo2 } from "lucide-react";

import type { ReactNode } from "react";

import { Button, IconButton, cx } from "../../ui";
import { MAX_ZOOM, MIN_ZOOM, zoomPercent } from "./view";

export type CanvasToolbarTexts = {
  toolbar: string;
  zoomIn: string;
  zoomOut: string;
  fit: string;
  actualSize: string;
  /** Names the percentage readout, e.g. "Zoom 75 %". */
  zoomLevel: (percent: number) => string;
  undo: string;
  redo: string;
  connect: string;
  lasso: string;
};

/** The drawing controls: undo and redo (writable canvases only), connect mode (writable only) and the lasso (always, selecting changes nothing). */
export type CanvasToolbarEdit = {
  writable: boolean;
  canUndo: boolean;
  canRedo: boolean;
  /** Undo or redo is running. */
  busy: boolean;
  connecting: boolean;
  lasso: boolean;
};

export type CanvasToolbarEditActions = { undo(): void; redo(): void; toggleConnect(): void; toggleLasso(): void };

export type CanvasToolbarActions = { zoomIn(): void; zoomOut(): void; fit(): void; actualSize(): void };

/**
 * Zoom controls over the top left of the canvas: zoom out and in, the readout, Fit and 100 %. It only shows and asks; the view
 * itself is moved by `GraphNavigation`. Every control is a labelled button, and the readout is plain text that is not announced on each change.
 */
export function CanvasToolbar({ scale, texts, actions, edit, editActions }: { scale: number; texts: CanvasToolbarTexts; actions: CanvasToolbarActions; edit?: CanvasToolbarEdit; editActions?: CanvasToolbarEditActions }) {
  const percent = zoomPercent(scale);
  return (
    <div role="toolbar" aria-label={texts.toolbar} className="absolute left-2 top-2 z-10 flex max-w-[calc(100%-1rem)] flex-wrap items-center gap-1 rounded-[var(--radius-card)] border border-line bg-surface p-1 shadow-[var(--shadow-overlay)]">
      <IconButton label={texts.zoomOut} icon={<Minus size={16} />} disabled={scale <= MIN_ZOOM + 0.0005} onClick={actions.zoomOut} />
      <output aria-label={texts.zoomLevel(percent)} aria-live="off" data-testid="zoom-readout" className="min-w-[52px] text-center text-[13px] font-medium tabular-nums text-ink">{percent} %</output>
      <IconButton label={texts.zoomIn} icon={<Plus size={16} />} disabled={scale >= MAX_ZOOM - 0.0005} onClick={actions.zoomIn} />
      <IconButton label={texts.fit} icon={<Maximize size={16} />} onClick={actions.fit} />
      <Button aria-label={texts.actualSize} title={texts.actualSize} onClick={actions.actualSize}>100 %</Button>
      {edit && editActions ? (
        <>
          <span role="separator" aria-orientation="vertical" className="mx-1 h-5 w-px bg-line" />
          {edit.writable ? (
            <>
              <IconButton label={texts.undo} icon={<Undo2 size={16} />} disabled={!edit.canUndo || edit.busy} onClick={editActions.undo} />
              <IconButton label={texts.redo} icon={<Redo2 size={16} />} disabled={!edit.canRedo || edit.busy} onClick={editActions.redo} />
              <ToggleButton label={texts.connect} pressed={edit.connecting} onClick={editActions.toggleConnect}><MoveRight size={16} /></ToggleButton>
            </>
          ) : null}
          <ToggleButton label={texts.lasso} pressed={edit.lasso} onClick={editActions.toggleLasso}><BoxSelect size={16} /></ToggleButton>
        </>
      ) : null}
    </div>
  );
}

/** A toolbar button that stays pressed (connect mode, lasso): `aria-pressed` and a filled background carry the state, not colour alone. */
function ToggleButton({ label, pressed, onClick, children }: { label: string; pressed: boolean; onClick(): void; children: ReactNode }) {
  return (
    <button
      type="button" aria-label={label} title={label} aria-pressed={pressed} onClick={onClick}
      className={cx("inline-flex h-8 w-8 cursor-pointer items-center justify-center rounded-[var(--radius-control)] border text-ink pointer-coarse:h-11 pointer-coarse:w-11", pressed ? "border-accent bg-accent-soft text-accent shadow-[inset_0_0_0_1px_var(--color-accent)]" : "border-transparent bg-transparent hover:bg-surface-subtle")}
    >
      {children}
    </button>
  );
}
