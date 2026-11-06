// @vitest-environment node

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import react from "@vitejs/plugin-react";
import { expect, it } from "vitest";

it("allows the installed React-refresh preamble without allowing arbitrary inline scripts", () => {
  const caddyfile = readFileSync(new URL("../local/Caddyfile", import.meta.url), "utf8");
  const scriptSources = caddyfile.match(/script-src ([^;]+);/)?.[1].split(/\s+/);
  // Vite serves this preamble with the default base URL, including its exact whitespace.
  const preamble = react.preambleCode.replace("__BASE__", "/");
  const hash = createHash("sha256").update(preamble).digest("base64");

  expect(scriptSources).toEqual(["'self'", `'sha256-${hash}'`]);
});
