import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// The Structure canvas modules need a DOM (diagram-js draws SVG), which Node's own test runner does not give; they run here, in jsdom.
// Pure logic without a DOM stays in tests/unit under `node --test`.
export default defineConfig({
  // diagram-js-minimap's `main` is a CommonJS build that cannot load diagram-js's ES modules under Node; the browser build uses its `module`
  // (ES) file, so the tests are pointed at that one, and Vite (not Node) loads it so its extensionless diagram-js imports resolve.
  resolve: { alias: { "diagram-js-minimap": fileURLToPath(new URL("./node_modules/diagram-js-minimap/dist/index.esm.js", import.meta.url)) } },
  test: {
    environment: "jsdom",
    include: ["tests/canvas/**/*.test.{ts,tsx}"],
    setupFiles: ["tests/canvas/setup.ts"],
    server: { deps: { inline: ["diagram-js-minimap"] } },
  },
});
