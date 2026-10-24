import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 300_000,
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "https://demo.truckerp.me",
    trace: "on-first-retry",
  },
});
