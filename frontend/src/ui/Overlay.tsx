import * as AlertDialog from "@radix-ui/react-alert-dialog";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { Button } from "./Button";
import { cx } from "./cx";

export type OverlayLabels = { cancel: string; close: string; dismiss: string; notifications: string };
const DEFAULT_LABELS: OverlayLabels = { cancel: "Cancel", close: "Close", dismiss: "Dismiss", notifications: "Notifications" };
const LabelsContext = createContext<OverlayLabels>(DEFAULT_LABELS);

const OVERLAY = "fixed inset-0 z-40 bg-[rgb(17_28_36/0.32)] print:hidden";

/** Remember what had focus when an overlay opened without a Radix trigger, and give focus back on close. */
function useReturnFocus(open: boolean) {
  const previous = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);
  // Captured on the render that opens the overlay, before Radix moves focus inside it.
  if (open && !wasOpen.current && typeof document !== "undefined") previous.current = document.activeElement as HTMLElement | null;
  wasOpen.current = open;
  return (event: Event) => {
    const target = previous.current;
    previous.current = null;
    if (target && document.contains(target)) { event.preventDefault(); target.focus(); }
  };
}

/** A modal dialog: focus is trapped, Escape closes, and focus returns to the trigger. */
export function Dialog({ open, onOpenChange, title, description, children, footer, className, wide = false }: { open: boolean; onOpenChange: (open: boolean) => void; title: ReactNode; description?: ReactNode; children?: ReactNode; footer?: ReactNode; className?: string; wide?: boolean }) {
  const labels = useContext(LabelsContext);
  const returnFocus = useReturnFocus(open);
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className={OVERLAY} />
        <DialogPrimitive.Content onCloseAutoFocus={returnFocus} className={cx("ui-root fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] -translate-x-1/2 -translate-y-1/2 flex-col rounded-[var(--radius-card)] bg-surface shadow-[var(--shadow-overlay)]", wide ? "w-[min(880px,calc(100vw-32px))]" : "w-[min(560px,calc(100vw-32px))]", className)} {...(description ? {} : { "aria-describedby": undefined })}>
          <div className="flex items-start gap-3 border-b border-line px-5 py-4">
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <DialogPrimitive.Title className="text-base font-semibold">{title}</DialogPrimitive.Title>
              {description ? <DialogPrimitive.Description className="text-[13px] text-ink-muted">{description}</DialogPrimitive.Description> : null}
            </div>
            <DialogPrimitive.Close asChild>
              <button type="button" aria-label={labels.close} className="inline-flex size-8 cursor-pointer items-center justify-center rounded-[var(--radius-control)] text-ink-muted hover:bg-surface-sunken"><X size={18} aria-hidden="true" /></button>
            </DialogPrimitive.Close>
          </div>
          <div className="overflow-auto px-5 py-4">{children}</div>
          {footer ? <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div> : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

/** A side sheet from the right (full screen on phones) for forms next to the content. */
export function Drawer({ open, onOpenChange, title, description, children, footer, width = 440 }: { open: boolean; onOpenChange: (open: boolean) => void; title: ReactNode; description?: ReactNode; children?: ReactNode; footer?: ReactNode; width?: number }) {
  const labels = useContext(LabelsContext);
  const returnFocus = useReturnFocus(open);
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className={OVERLAY} />
        <DialogPrimitive.Content onCloseAutoFocus={returnFocus} {...(description ? {} : { "aria-describedby": undefined })} style={{ width: `min(${width}px, 100vw)` }} className="ui-root print:hidden fixed inset-y-0 right-0 z-50 flex flex-col bg-surface shadow-[var(--shadow-overlay)]">
          <div className="flex items-start gap-3 border-b border-line px-5 py-4">
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <DialogPrimitive.Title className="text-base font-semibold">{title}</DialogPrimitive.Title>
              {description ? <DialogPrimitive.Description className="text-[13px] text-ink-muted">{description}</DialogPrimitive.Description> : null}
            </div>
            <DialogPrimitive.Close asChild>
              <button type="button" aria-label={labels.close} className="inline-flex size-8 cursor-pointer items-center justify-center rounded-[var(--radius-control)] text-ink-muted hover:bg-surface-sunken pointer-coarse:size-11"><X size={18} aria-hidden="true" /></button>
            </DialogPrimitive.Close>
          </div>
          <div className="flex-1 overflow-auto px-5 py-4">{children}</div>
          {footer ? <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div> : null}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export type ConfirmRequest = { title: ReactNode; description?: ReactNode; confirmLabel: string; destructive?: boolean };
type ConfirmFn = (request: ConfirmRequest) => Promise<boolean>;
const ConfirmContext = createContext<ConfirmFn | null>(null);

/** Ask before a consequential action: `if (await confirm({ title, confirmLabel }))`. */
export function useConfirm(): ConfirmFn {
  const confirm = useContext(ConfirmContext);
  if (!confirm) throw new Error("useConfirm needs an OverlayProvider");
  return confirm;
}

export type Toast = { id: number; message: ReactNode };
const ToastContext = createContext<(message: ReactNode) => void>(() => undefined);

/** Show a short success message in the polite toast region. Errors stay next to their action. */
export function useToast(): (message: ReactNode) => void {
  return useContext(ToastContext);
}

/** Provides confirmations, toasts, and localized overlay labels to everything below it. */
export function OverlayProvider({ labels = DEFAULT_LABELS, children }: { labels?: OverlayLabels; children: ReactNode }) {
  const [request, setRequest] = useState<(ConfirmRequest & { resolve: (value: boolean) => void }) | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const confirm = useCallback<ConfirmFn>((next) => new Promise<boolean>((resolve) => setRequest({ ...next, resolve })), []);
  const answer = (value: boolean) => { request?.resolve(value); setRequest(null); };
  const returnFocus = useReturnFocus(request !== null);
  const toast = useCallback((message: ReactNode) => { const id = nextId.current++; setToasts((current) => [...current.slice(-2), { id, message }]); }, []);
  const dismiss = useCallback((id: number) => setToasts((current) => current.filter((item) => item.id !== id)), []);
  return (
    <LabelsContext.Provider value={labels}>
      <ConfirmContext.Provider value={confirm}>
        <ToastContext.Provider value={toast}>
          {children}
          <AlertDialog.Root open={request !== null} onOpenChange={(open) => { if (!open) answer(false); }}>
            <AlertDialog.Portal>
              <AlertDialog.Overlay className={OVERLAY} />
              <AlertDialog.Content onCloseAutoFocus={returnFocus} className="ui-root fixed left-1/2 top-1/2 z-50 flex w-[min(460px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-[var(--radius-card)] bg-surface p-5 shadow-[var(--shadow-overlay)]">
                <AlertDialog.Title className="text-base font-semibold leading-snug">{request?.title}</AlertDialog.Title>
                {request?.description ? <AlertDialog.Description className="text-[13px] text-ink-muted">{request.description}</AlertDialog.Description> : <AlertDialog.Description className="sr-only">{request?.title}</AlertDialog.Description>}
                <div className="flex justify-end gap-2">
                  <AlertDialog.Cancel asChild><Button>{labels.cancel}</Button></AlertDialog.Cancel>
                  <AlertDialog.Action asChild><Button data-confirm-action="" variant={request?.destructive ? "danger" : "primary"} onClick={() => answer(true)}>{request?.confirmLabel}</Button></AlertDialog.Action>
                </div>
              </AlertDialog.Content>
            </AlertDialog.Portal>
          </AlertDialog.Root>
          <Toaster toasts={toasts} onDismiss={dismiss} labels={labels} />
        </ToastContext.Provider>
      </ConfirmContext.Provider>
    </LabelsContext.Provider>
  );
}

function Toaster({ toasts, onDismiss, labels }: { toasts: Toast[]; onDismiss: (id: number) => void; labels: OverlayLabels }) {
  return (
    <section aria-label={labels.notifications} className="ui-root print:hidden pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(380px,calc(100vw-32px))] flex-col gap-2">
      <div role="status" aria-live="polite" className="flex flex-col gap-2">
        {toasts.map((item) => <ToastItem key={item.id} toast={item} onDismiss={onDismiss} label={labels.dismiss} />)}
      </div>
    </section>
  );
}

function ToastItem({ toast, onDismiss, label }: { toast: Toast; onDismiss: (id: number) => void; label: string }) {
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (paused) return;
    const timer = setTimeout(() => onDismiss(toast.id), 6000);
    return () => clearTimeout(timer);
  }, [paused, toast.id, onDismiss]);
  return (
    <div onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} onFocus={() => setPaused(true)} onBlur={() => setPaused(false)} className="pointer-events-auto flex items-start gap-3 rounded-[10px] border border-line bg-surface px-4 py-3 text-[13px] text-ink shadow-[var(--shadow-overlay)]">
      <span className="mt-1 size-2 shrink-0 rounded-full bg-accent" aria-hidden="true" />
      <p className="flex-1">{toast.message}</p>
      <button type="button" aria-label={label} onClick={() => onDismiss(toast.id)} className="inline-flex size-6 cursor-pointer items-center justify-center rounded-[6px] text-ink-muted hover:bg-surface-sunken"><X size={14} aria-hidden="true" /></button>
    </div>
  );
}

/** A menu of actions behind a button (row actions, the user menu). */
export function Menu({ trigger, items, align = "end" }: { trigger: ReactNode; items: Array<{ label: string; onSelect: () => void; destructive?: boolean; icon?: ReactNode } | "separator">; align?: "start" | "end" }) {
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>{trigger}</DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align={align} sideOffset={6} className="ui-root z-50 min-w-48 rounded-[10px] border border-line bg-surface p-1 shadow-[var(--shadow-overlay)]">
          {items.map((item, index) => item === "separator"
            ? <DropdownMenu.Separator key={index} className="my-1 h-px bg-line" />
            : <DropdownMenu.Item key={item.label} onSelect={item.onSelect} className={cx("flex h-8 cursor-pointer items-center gap-2 rounded-[6px] px-2.5 text-[13px] outline-none data-[highlighted]:bg-surface-sunken pointer-coarse:h-11", item.destructive ? "text-danger" : "text-ink")}>
                {item.icon ? <span aria-hidden="true" className="inline-flex">{item.icon}</span> : null}{item.label}
              </DropdownMenu.Item>)}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}

/** Content anchored to a trigger (the change list, small forms). */
export function Popover({ trigger, children, label, align = "end" }: { trigger: ReactNode; children: ReactNode; label: string; align?: "start" | "center" | "end" }) {
  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content aria-label={label} align={align} sideOffset={6} className="ui-root z-50 w-[min(380px,calc(100vw-32px))] rounded-[var(--radius-card)] border border-line bg-surface p-4 shadow-[var(--shadow-overlay)]">
          {children}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

/** Tabs with the standard keyboard model (arrows move, Home and End jump). */
export function Tabs({ label, value, onValueChange, tabs, className }: { label: string; value: string; onValueChange: (value: string) => void; tabs: Array<{ value: string; label: ReactNode; content: ReactNode }>; className?: string }) {
  return (
    <TabsPrimitive.Root value={value} onValueChange={onValueChange} className={cx("flex min-h-0 flex-col", className)}>
      <TabsPrimitive.List aria-label={label} className="flex gap-1 border-b border-line px-3">
        {tabs.map((tab) => (
          <TabsPrimitive.Trigger key={tab.value} value={tab.value} className="-mb-px h-10 cursor-pointer border-x-0 border-t-0 border-b-2 border-solid border-transparent bg-transparent px-3 text-[13px] font-medium text-ink-muted hover:text-ink data-[state=active]:border-accent data-[state=active]:font-semibold data-[state=active]:text-ink pointer-coarse:h-11">
            {tab.label}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {tabs.map((tab) => <TabsPrimitive.Content key={tab.value} value={tab.value} className="min-h-0 flex-1 overflow-auto focus-visible:outline-none">{tab.content}</TabsPrimitive.Content>)}
    </TabsPrimitive.Root>
  );
}
