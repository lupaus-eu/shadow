import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * The Authentik sign-in pages load the application's own stylesheet (ADR-0039). The built file
 * has a hashed name, so it is published a second time as /theme.css, a fixed address that the
 * edge serves without caching. There is one stylesheet (docs/design/ui-foundation.md).
 */
function publishThemeStylesheet(): Plugin {
  return {
    name: "publish-theme-stylesheet",
    apply: "build",
    generateBundle(_options, bundle) {
      const sheets = Object.values(bundle).filter((file) => file.type === "asset" && file.fileName.endsWith(".css"));
      if (sheets.length !== 1 || sheets[0].type !== "asset") throw new Error(`Expected one stylesheet, found ${sheets.length}`);
      this.emitFile({ type: "asset", fileName: "theme.css", source: sheets[0].source });
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), publishThemeStylesheet()],
  // Yearclock owns host ports 8100-8199; see docs/architecture/docker.md.
  server: {
    host: "0.0.0.0",
    port: 8173,
    strictPort: true,
  },
  preview: {
    port: 8175,
    strictPort: true,
  },
});
