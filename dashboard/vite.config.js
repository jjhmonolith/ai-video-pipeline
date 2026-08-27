import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react()],
  base: "/",
  build: {
    outDir: fileURLToPath(new URL("../src/ai_video_pipeline/dashboard_static", import.meta.url)),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        entryFileNames: "assets/dashboard.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: (assetInfo) => assetInfo.name?.endsWith(".css")
          ? "assets/dashboard.css"
          : "assets/[name][extname]",
      },
    },
  },
});
