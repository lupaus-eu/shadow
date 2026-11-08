import { defineConfig } from "vitest/config";

// The Structure canvas modules need a DOM (diagram-js draws SVG), which Node's own test runner does not give; they run here, in jsdom.
// Pure logic without a DOM stays in tests/unit under `node --test`.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/canvas/**/*.test.{ts,tsx}"],
    setupFiles: ["tests/canvas/setup.ts"],
  },
});
