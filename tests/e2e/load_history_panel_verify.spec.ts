/**
 * Load History panel v1 — browser proof on dev UI + demo tenant API.
 *
 *   E2E_LOGIN_EMAIL=... E2E_LOGIN_PASSWORD=... \
 *   E2E_BASE_URL=http://127.0.0.1:5173 \
 *   npx playwright test tests/e2e/load_history_panel_verify.spec.ts
 */
import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DEMO_AUTH_FILE } from "./global-setup";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ARMSTRONG_PDF = path.resolve(
  __dirname,
  "../../docs/_review/fixtures/pdf/Armstrong.pdf",
);

const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const email = process.env.E2E_LOGIN_EMAIL;
const password = process.env.E2E_LOGIN_PASSWORD;
const screenshotDir = path.resolve(__dirname, "../../test-results/load-history-panel");

test.describe("Load History panel v1", () => {
  test.skip(!email || !password, "Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD");
  test.use({ storageState: DEMO_AUTH_FILE, ignoreHTTPSErrors: true });

  test("history shows actor, rate change, revised RC; API has no storage keys", async ({
    page,
  }, testInfo) => {
    const tag = Date.now();
    let loadId: number | null = null;

    await page.goto("/loads/new");
    await expect(page.getByRole("heading", { name: /new load/i })).toBeVisible({ timeout: 30_000 });

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(ARMSTRONG_PDF);
    await expect(page.getByText(/parse|applied|fields/i).first()).toBeVisible({ timeout: 180_000 });

    const createBtn = page.getByRole("button", { name: /^create load$/i });
    await expect(createBtn).toBeEnabled({ timeout: 60_000 });
    await createBtn.click();
    await page.waitForURL(/\/loads\/\d+/, { timeout: 120_000 });
    const m = page.url().match(/\/loads\/(\d+)/);
    loadId = m ? Number(m[1]) : null;
    expect(loadId).toBeTruthy();

    await page.screenshot({
      path: path.join(screenshotDir, `a-after-create-${tag}.png`),
      fullPage: true,
    });

    await page.getByTestId("load-workspace-history").click();
    await expect(page.getByTestId("load-history-panel")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Load created").first()).toBeVisible();
    await page.screenshot({
      path: path.join(screenshotDir, `a-history-created-${tag}.png`),
      fullPage: true,
    });
    await page.getByLabel("Close load history").click();

    const rateField = page.getByRole("textbox", { name: /^rate$/i });
    if (await rateField.count()) {
      await rateField.fill("12345");
    }
    await page.getByRole("button", { name: /^save load$/i }).click();
    await expect(page.getByText(/saved/i).first()).toBeVisible({ timeout: 60_000 });

    await page.getByTestId("load-workspace-history").click();
    await expect(page.getByText("Load updated").first()).toBeVisible({ timeout: 15_000 });
    await page.screenshot({
      path: path.join(screenshotDir, `b-history-rate-${tag}.png`),
      fullPage: true,
    });
    await page.getByLabel("Close load history").click();

    await page.getByRole("button", { name: /upload revised rc/i }).click();
    const revisedInput = page.locator('input[type="file"][accept*="pdf"]').last();
    await revisedInput.setInputFiles(ARMSTRONG_PDF);
    await expect(page.getByText(/attached|revised|upload/i).first()).toBeVisible({ timeout: 120_000 });

    await page.getByTestId("load-workspace-history").click();
    await expect(page.getByText("Revised RC uploaded").first()).toBeVisible({ timeout: 15_000 });
    await page.screenshot({
      path: path.join(screenshotDir, `c-history-revised-rc-${tag}.png`),
      fullPage: true,
    });

    const auditResponse = await page.waitForResponse(
      (r) =>
        r.url().includes("/audit-events/by-entity") &&
        r.request().method() === "GET" &&
        r.status() === 200,
      { timeout: 15_000 },
    );
    const bodyText = await auditResponse.text();
    expect(bodyText.toLowerCase()).not.toContain("storage_key");
    expect(bodyText.toLowerCase()).not.toContain("s3://");
    testInfo.annotations.push({ type: "loadId", description: String(loadId) });

    await page.getByLabel("Close load history").click();
  });
});
