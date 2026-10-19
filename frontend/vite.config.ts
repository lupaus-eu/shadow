import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const devApiProxyTarget = process.env.VITE_DEV_API_PROXY_TARGET?.trim() || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    allowedHosts: ["app.localhost"],
    hmr: {
      protocol: "wss",
      host: "app.localhost",
      clientPort: 443
    },
    proxy: {
      "/api": {
        target: devApiProxyTarget,
        changeOrigin: false
      }
    }
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts"
  }
});
