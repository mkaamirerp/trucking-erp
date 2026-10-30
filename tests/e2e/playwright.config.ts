import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: ".",
  timeout: 300_000,
  globalSetup: path.join(__dirname, "global-setup.ts"),
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://demo.truckerp.me",
    trace: "on-first-retry",
  },
});
