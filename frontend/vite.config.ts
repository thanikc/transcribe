import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === "build" ? "/static/" : "/",
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8799",
    },
  },
  build: {
    outDir: "../src/transcribe/static",
    emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: {
      output: {
        entryFileNames: "js/main.js",
        chunkFileNames: "js/[name].js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.names?.some((n) => n.endsWith(".css"))) {
            return "css/main[extname]";
          }
          return "assets/[name][extname]";
        },
      },
    },
  },
}));
