import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const devApiProxyTarget =
  process.env.VITE_DEV_API_PROXY_TARGET?.trim() || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": devApiProxyTarget
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts"
  }
});
