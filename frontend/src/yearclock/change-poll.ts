/** A visibility-aware poll for changes by others (Yearclock V2, P4). No real-time transport; nothing merges. */

export type ChangePollOptions = {
  intervalMs: number;
  isVisible: () => boolean;
  /** Resolves true when others changed the Yearclock since the page loaded. */
  check: () => Promise<boolean>;
  onChanges: () => void;
  setTimer?: (callback: () => void, delay: number) => unknown;
  clearTimer?: (handle: unknown) => void;
};

export type ChangePoll = { stop: () => void; visibilityChanged: () => void };

/** Checks every ``intervalMs`` while visible, pauses while hidden, and stops after the first change. */
export function startChangePoll({ intervalMs, isVisible, check, onChanges, setTimer = (callback, delay) => setTimeout(callback, delay), clearTimer = (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>) }: ChangePollOptions): ChangePoll {
  let handle: unknown = null;
  let stopped = false;
  const schedule = () => {
    if (stopped || handle !== null || !isVisible()) return;
    handle = setTimer(() => {
      handle = null;
      void check().then((changed) => {
        if (stopped) return;
        if (changed) { stopped = true; onChanges(); } else schedule();
      }, () => schedule());
    }, intervalMs);
  };
  schedule();
  return {
    stop: () => { stopped = true; if (handle !== null) clearTimer(handle); handle = null; },
    visibilityChanged: () => {
      if (isVisible()) schedule();
      else if (handle !== null) { clearTimer(handle); handle = null; }
    },
  };
}
