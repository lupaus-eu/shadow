import {
  AlignCenterHorizontal, AlignCenterVertical, AlignHorizontalSpaceBetween, AlignStartHorizontal, AlignStartVertical, AlignVerticalSpaceBetween,
  BoxSelect, Download, Magnet, Map as MapIcon, Maximize, Minus, MoveRight, Network, Plus, Redo2, Undo2,
} from "lucide-react";

import type { ReactNode } from "react";

import { Button, IconButton, Menu, cx } from "../../ui";
import type { AlignMode, DistributeAxis } from "./diagram/GraphTools";
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
  snap: string;
  alignLeft: string;
  alignCentre: string;
  alignTop: string;
  alignMiddle: string;
  distributeHorizontal: string;
  distributeVertical: string;
  autoLayout: string;
  minimap: string;
  exportMenu: string;
  exportSvg: string;
  exportPng: string;
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

/** The tidying and viewing tools. `align` needs two selected nodes, `distribute` three; every export item needs something drawn. */
export type CanvasToolbarTools = {
  writable: boolean;
  snap: boolean;
  canAlign: boolean;
  canDistribute: boolean;
  canLayout: boolean;
  /** A layout or an export is running. */
  busy: boolean;
  minimap: boolean;
  canExport: boolean;
};

export type CanvasToolbarToolActions = { toggleSnap(): void; align(mode: AlignMode): void; distribute(axis: DistributeAxis): void; autoLayout(): void; toggleMinimap(): void; exportSvg(): void; exportPng(): void };

export type CanvasToolbarEditActions = { undo(): void; redo(): void; toggleConnect(): void; toggleLasso(): void };

export type CanvasToolbarActions = { zoomIn(): void; zoomOut(): void; fit(): void; actualSize(): void };

/**
 * Zoom controls over the top left of the canvas: zoom out and in, the readout, Fit and 100 %. It only shows and asks; the view
 * itself is moved by `GraphNavigation`. Every control is a labelled button, and the readout is plain text that is not announced on each change.
 */
export function CanvasToolbar({ scale, texts, actions, edit, editActions, tools, toolActions }: { scale: number; texts: CanvasToolbarTexts; actions: CanvasToolbarActions; edit?: CanvasToolbarEdit; editActions?: CanvasToolbarEditActions; tools?: CanvasToolbarTools; toolActions?: CanvasToolbarToolActions }) {
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
      {tools && toolActions ? (
        <>
          <span role="separator" aria-orientation="vertical" className="mx-1 h-5 w-px bg-line" />
          {tools.writable ? (
            <>
              <ToggleButton label={texts.snap} pressed={tools.snap} onClick={toolActions.toggleSnap}><Magnet size={16} /></ToggleButton>
              <IconButton label={texts.alignLeft} icon={<AlignStartVertical size={16} />} disabled={!tools.canAlign} onClick={() => toolActions.align("left")} />
              <IconButton label={texts.alignCentre} icon={<AlignCenterVertical size={16} />} disabled={!tools.canAlign} onClick={() => toolActions.align("centre")} />
              <IconButton label={texts.alignTop} icon={<AlignStartHorizontal size={16} />} disabled={!tools.canAlign} onClick={() => toolActions.align("top")} />
              <IconButton label={texts.alignMiddle} icon={<AlignCenterHorizontal size={16} />} disabled={!tools.canAlign} onClick={() => toolActions.align("middle")} />
              <IconButton label={texts.distributeHorizontal} icon={<AlignHorizontalSpaceBetween size={16} />} disabled={!tools.canDistribute} onClick={() => toolActions.distribute("horizontal")} />
              <IconButton label={texts.distributeVertical} icon={<AlignVerticalSpaceBetween size={16} />} disabled={!tools.canDistribute} onClick={() => toolActions.distribute("vertical")} />
              <IconButton label={texts.autoLayout} icon={<Network size={16} />} disabled={!tools.canLayout || tools.busy} onClick={toolActions.autoLayout} />
              <span role="separator" aria-orientation="vertical" className="mx-1 h-5 w-px bg-line" />
            </>
          ) : null}
          <ToggleButton label={texts.minimap} pressed={tools.minimap} onClick={toolActions.toggleMinimap}><MapIcon size={16} /></ToggleButton>
          <Menu
            align="start"
            trigger={<IconButton label={texts.exportMenu} icon={<Download size={16} />} disabled={!tools.canExport || tools.busy} />}
            items={[{ label: texts.exportSvg, onSelect: toolActions.exportSvg }, { label: texts.exportPng, onSelect: toolActions.exportPng }]}
          />
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
