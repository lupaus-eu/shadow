import assert from "node:assert/strict";
import { test } from "node:test";

import { startChangePoll } from "../../src/yearclock/change-poll.ts";

function fakeTimers() {
  const timers = new Map<number, { callback: () => void; delay: number }>();
  let next = 1;
  return {
    timers,
    setTimer: (callback: () => void, delay: number) => { timers.set(next, { callback, delay }); return next++; },
    clearTimer: (handle: unknown) => { timers.delete(handle as number); },
    fire: async () => { const [id, timer] = [...timers.entries()][0]; timers.delete(id); timer.callback(); await new Promise((resolve) => setImmediate(resolve)); },
  };
}

test("polls while visible, pauses while hidden, and stops after a change", async () => {
  const clock = fakeTimers();
  let visible = true;
  const answers = [false, true];
  let checks = 0;
  let notified = 0;
  const poll = startChangePoll({ intervalMs: 60_000, isVisible: () => visible, check: async () => { checks += 1; return answers.shift() ?? false; }, onChanges: () => { notified += 1; }, setTimer: clock.setTimer, clearTimer: clock.clearTimer });
  assert.equal(clock.timers.size, 1);
  assert.equal([...clock.timers.values()][0].delay, 60_000);
  await clock.fire();
  assert.equal(checks, 1);
  assert.equal(clock.timers.size, 1);
  visible = false;
  poll.visibilityChanged();
  assert.equal(clock.timers.size, 0);
  visible = true;
  poll.visibilityChanged();
  assert.equal(clock.timers.size, 1);
  await clock.fire();
  assert.equal(checks, 2);
  assert.equal(notified, 1);
  assert.equal(clock.timers.size, 0);
  poll.visibilityChanged();
  assert.equal(clock.timers.size, 0);
});

test("a failed check keeps polling and stop clears the timer", async () => {
  const clock = fakeTimers();
  const poll = startChangePoll({ intervalMs: 1000, isVisible: () => true, check: async () => { throw new Error("offline"); }, onChanges: () => assert.fail("no change"), setTimer: clock.setTimer, clearTimer: clock.clearTimer });
  await clock.fire();
  assert.equal(clock.timers.size, 1);
  poll.stop();
  assert.equal(clock.timers.size, 0);
});
