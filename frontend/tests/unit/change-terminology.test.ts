import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

// ADR-0052: the dated item on a line is a Change and its steps are Edits. This guard keeps the old names (event, changes[]) out of
// the web interface: it scans frontend/src and the specs for the stale identifiers, routes, fields and URL parameter.
const STALE = [
  /TimelineEvent/, /LineEvent/, /EventEdit/, /EventChange/, /EventPanel/, /EventEditor/, /timeline-events/, /reloadEvents/, /eventIsLast/,
  /\?event=/, /get\("event"\)/, /\/events\b/, /branch_event/, /event_id/, /event_count/, /latest_event/, /event_title/, /event_date/,
  /missing_branch_event/, /before_branch_event/, /change_counts/, /events_per_line/, /changesCount/, /describeChange/,
  /sourceEventId/, /startingEvent/, /\bchanges: \[/, /EventRow/, /ListedEvent/,
];
// Not part of this rename: the platform support console reads the legacy Yearclock events of a shared Shadow.
const ALLOWED: Array<{ file: string; pattern: RegExp }> = [
  { file: "src/platform/platform-client.ts", pattern: /\/events\b/ },
];
const root = fileURLToPath(new URL("../..", import.meta.url));

function files(directory: string): string[] {
  return readdirSync(directory).flatMap((name) => {
    const path = join(directory, name);
    return statSync(path).isDirectory() ? files(path) : /\.(ts|tsx)$/.test(name) ? [path] : [];
  });
}

test("the web interface uses Change and Edit, not the old event and changes[] names", () => {
  const found: string[] = [];
  for (const path of [...files(join(root, "src")), ...files(join(root, "tests/browser")), ...files(join(root, "tests/canvas"))]) {
    const name = path.slice(root.length);
    readFileSync(path, "utf8").split("\n").forEach((line, index) => {
      for (const pattern of STALE) {
        if (pattern.test(line) && !ALLOWED.some((allowed) => allowed.file === name && allowed.pattern.test(line))) found.push(`${name}:${index + 1} ${pattern}`);
      }
    });
  }
  assert.deepEqual(found, [], "stale names of the old vocabulary (ADR-0052)");
});
