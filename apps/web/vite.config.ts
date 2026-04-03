import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

/** Embedded at compile time so you can confirm the served bundle (see load detail footer). */
const UI_BUILD_ID = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);

export default defineConfig({
  define: {
    __UI_BUILD_ID__: JSON.stringify(UI_BUILD_ID),
  },
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
  server: {
    port: 5173,
    strictPort: false,
    hmr: { host: "localhost", port: 5173 },
    proxy: {
      "/api": {
        target: process.env.API_PROXY_TARGET || "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
