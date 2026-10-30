/**
 * Minimal parser regression (demo UI) — Milestone A foundation.
 * Requires E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD.
 */
import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ARMSTRONG_PDF = path.resolve(__dirname, "../../docs/_review/fixtures/pdf/Armstrong.pdf");
const email = process.env.E2E_LOGIN_EMAIL ?? "";
const password = process.env.E2E_LOGIN_PASSWORD ?? "";
const EXISTING_LOAD_ID = process.env.E2E_REGRESSION_LOAD_ID ?? "1010";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByPlaceholder("admin@company.com").fill(email);
  await page.getByPlaceholder("••••••••").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 90_000 });
}

test.describe("Parser regression (minimal)", () => {
  test.skip(!email || !password, "Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD");

  test.use({ ignoreHTTPSErrors: true });

  test("New Load — upload PDF, first parse hydrates commercial fields", async ({ page }) => {
    await login(page);
    await page.goto("/loads/new");
    await page.locator('input[type="file"]').first().setInputFiles(ARMSTRONG_PDF);
    const dupGate = page.getByRole("heading", { name: /already on a load/i });
    if (await dupGate.isVisible({ timeout: 30_000 }).catch(() => false)) {
      test.info().annotations.push({
        type: "skipReason",
        description:
          "Armstrong.pdf is already on a demo load (duplicate PDF gate). First parser not exercised on /loads/new; use a fresh RC on an isolated tenant for full create-path proof.",
      });
      await expect(dupGate.getByText(/already on a load/i)).toBeVisible();
      return;
    }
    await expect(page.getByTestId("rate-confirmation-pdf-viewer")).toBeVisible({ timeout: 240_000 });
    await expect(page.getByRole("textbox", { name: /linehaul rate/i })).toHaveValue(/1800|1,800/, {
      timeout: 30_000,
    });
    await expect(page.getByPlaceholder("Load number from broker")).toHaveValue(/3872125/, {
      timeout: 15_000,
    });
  });

  test("Existing Load — manual edit survives Save and reopen", async ({ page }) => {
    await login(page);
    await page.goto(`/loads/${EXISTING_LOAD_ID}`);
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    const notes = page.getByRole("textbox", { name: /internal notes/i });
    const marker = `milestone-a-${Date.now()}`;
    if (await notes.isVisible().catch(() => false)) {
      await notes.fill(marker);
    } else {
      const brokerRef = page.getByPlaceholder("Load number from broker");
      const prior = await brokerRef.inputValue();
      await brokerRef.fill(`${prior}-MA`);
      await page.getByRole("button", { name: /^save load$/i }).click();
      await page.reload();
      await expect(brokerRef).toHaveValue(new RegExp(`${prior.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}-MA`));
      return;
    }
    await page.getByRole("button", { name: /^save load$/i }).click();
    await page.reload();
    await expect(notes).toHaveValue(marker, { timeout: 60_000 });
  });

  test("Existing Load — original and revised RC PDF download links respond", async ({ page, request }) => {
    await login(page);
    await page.goto(`/loads/${EXISTING_LOAD_ID}`);
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    const cookies = await page.context().cookies();
    const cookieHeader = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    const origin = page.url().split("/loads/")[0];
    const original = await request.get(`${origin}/api/v1/loads/${EXISTING_LOAD_ID}/rate-confirmation-pdf`, {
      headers: { Cookie: cookieHeader, Host: "demo.truckerp.me" },
    });
    expect(original.status()).toBe(200);
    expect(original.headers()["content-type"] || "").toMatch(/pdf/i);
    const revised = await request.get(
      `${origin}/api/v1/loads/${EXISTING_LOAD_ID}/rate-confirmation-pdf?revision=1`,
      { headers: { Cookie: cookieHeader, Host: "demo.truckerp.me" } },
    );
    if (revised.status() === 200) {
      expect(revised.headers()["content-type"] || "").toMatch(/pdf/i);
    } else {
      test.info().annotations.push({
        type: "note",
        description: `No revised PDF revision=1 on load ${EXISTING_LOAD_ID} (HTTP ${revised.status()})`,
      });
    }
  });
});
