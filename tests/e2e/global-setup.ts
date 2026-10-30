/**
 * One login per Playwright run — saves storageState to avoid 429 on demo.
 */
import { chromium, type FullConfig } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const DEMO_AUTH_FILE = path.join(__dirname, ".auth", "demo-user.json");

async function globalSetup(_config: FullConfig) {
  const email = process.env.E2E_LOGIN_EMAIL ?? "";
  const password = process.env.E2E_LOGIN_PASSWORD ?? "";
  if (!email || !password) {
    throw new Error("Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD before running Playwright.");
  }

  fs.mkdirSync(path.dirname(DEMO_AUTH_FILE), { recursive: true });

  if (fs.existsSync(DEMO_AUTH_FILE)) {
    const ageMs = Date.now() - fs.statSync(DEMO_AUTH_FILE).mtimeMs;
    if (ageMs < 60 * 60 * 1000) {
      console.log(`Reusing Playwright storageState (${Math.round(ageMs / 1000)}s old) → ${DEMO_AUTH_FILE}`);
      return;
    }
  }

  const baseURL = process.env.E2E_BASE_URL ?? "https://demo.truckerp.me";
  const browser = await chromium.launch();
  const context = await browser.newContext({ ignoreHTTPSErrors: true, baseURL });
  const page = await context.newPage();

  const loginResponsePromise = page.waitForResponse(
    (r) => r.url().includes("/api/v1/auth/login") && r.request().method() === "POST",
    { timeout: 120_000 },
  );

  await page.goto("/login");
  await page.getByPlaceholder("admin@company.com").fill(email);
  await page.getByPlaceholder("••••••••").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();

  const loginResp = await loginResponsePromise;
  if (loginResp.status() === 429) {
    const body = await loginResp.text();
    await browser.close();
    throw new Error(`Demo login rate-limited (429). Do not retry until lockout expires. Body: ${body.slice(0, 400)}`);
  }
  if (loginResp.status() !== 200) {
    const body = await loginResp.text();
    await browser.close();
    throw new Error(`Demo login failed (${loginResp.status()}): ${body.slice(0, 400)}`);
  }

  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 120_000 });
  await context.storageState({ path: DEMO_AUTH_FILE });
  await browser.close();
  console.log(`Saved Playwright storageState → ${DEMO_AUTH_FILE}`);
}

export default globalSetup;
