/**
 * Milestone B2 — simplified parse workflow (demo).
 */
import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import fs from "node:fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SHOT = path.resolve(__dirname, "../../docs/reports/milestone_b2_screenshots");
const ARM = path.resolve(
  "/home/admin/archive/truckerp_reparse_audit_2026-10-30/fixtures_reparse/Armstrong.pdf",
);
const email = process.env.E2E_LOGIN_EMAIL ?? "";
const password = process.env.E2E_LOGIN_PASSWORD ?? "";
const LOAD_ID = process.env.E2E_B1_LOAD_ID ?? "1010";

async function login(page: import("@playwright/test").Page) {
  await page.goto("/login");
  await page.getByPlaceholder("admin@company.com").fill(email);
  await page.getByPlaceholder("••••••••").fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 90_000 });
}

test.describe("Milestone B2 workflow", () => {
  test.skip(!email || !password, "Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD");
  test.use({ ignoreHTTPSErrors: true, baseURL: "https://demo.truckerp.me" });

  test("A — New Load Armstrong parse regression", async ({ page }) => {
    test.skip(!fs.existsSync(ARM), `Missing ${ARM}`);
    fs.mkdirSync(SHOT, { recursive: true });
    await login(page);
    await page.goto("/loads/new");
    await page.locator('input[type="file"]').first().setInputFiles(ARM);
    const dupGate = page.getByRole("heading", { name: /already on a load/i });
    if (await dupGate.isVisible({ timeout: 45_000 }).catch(() => false)) {
      test.info().annotations.push({
        type: "note",
        description: "Armstrong.pdf duplicate on demo — first parser exercised on existing load 1010 in test B.",
      });
      await page.screenshot({ path: `${SHOT}/A-duplicate-gate.png`, fullPage: true });
      return;
    }
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 180_000 });
    await page.screenshot({ path: `${SHOT}/A-new-load-parsed.png`, fullPage: true });
    await expect(page.getByRole("textbox", { name: /linehaul rate/i })).not.toHaveValue("");
  });

  test("B–E — Parse attached revision on load 1010", async ({ page, request }) => {
    fs.mkdirSync(SHOT, { recursive: true });
    await login(page);
    await page.goto(`/loads/${LOAD_ID}`);
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    const rateBefore = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    await page.screenshot({ path: `${SHOT}/B-before-parse.png`, fullPage: true });

    await page.getByTestId("parse-revised-pdf").click();
    await page.getByTestId("parse-reference-review").waitFor({ state: "visible", timeout: 180_000 });
    await page.screenshot({ path: `${SHOT}/B-parse-panel-open.png`, fullPage: true });
    const rateDuring = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    expect(rateDuring).toBe(rateBefore);

    const rateRow = page.getByTestId("parse-use-field-rate");
    if (await rateRow.isVisible()) {
      await rateRow.click();
      const rateForm = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
      expect(rateForm).not.toBe(rateBefore);
      await page.screenshot({ path: `${SHOT}/C-rate-applied-form-only.png`, fullPage: true });
      await page.getByRole("button", { name: /^save load$/i }).click();
      await expect(page.getByRole("button", { name: /^saved$/i })).toBeVisible({ timeout: 60_000 });
      await page.screenshot({ path: `${SHOT}/C-after-save.png`, fullPage: true });
      await page.reload();
      await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
      const rateAfter = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
      expect(rateAfter).toBe(rateForm);
    }

    await page.goto(`/loads/${LOAD_ID}`);
    await page.getByTestId("parse-revised-pdf").click();
    await page.getByTestId("parse-reference-review").waitFor({ state: "visible", timeout: 180_000 });
    await page.getByTestId("parse-reference-close").click();
    await expect(page.getByTestId("parse-reference-review")).toBeHidden();
    await page.screenshot({ path: `${SHOT}/D-closed-without-use.png`, fullPage: true });

    const cookies = await page.context().cookies();
    const cookieHeader = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    const origin = "https://demo.truckerp.me";
    const headers = { Cookie: cookieHeader, Host: "demo.truckerp.me" };
    const orig = await request.get(`${origin}/api/v1/loads/${LOAD_ID}/rate-confirmation-pdf`, { headers });
    const origSha = createHash("sha256").update(await orig.body()).digest("hex");
    const n = Number(orig.headers()["x-revised-rate-confirmations"] || "0");
    expect(n).toBeGreaterThan(0);
    for (let rev = 1; rev <= n; rev++) {
      const r = await request.get(`${origin}/api/v1/loads/${LOAD_ID}/rate-confirmation-pdf?revision=${rev}`, {
        headers,
      });
      expect(r.status()).toBe(200);
      expect((await r.body()).length).toBeGreaterThan(1000);
    }
    test.info().annotations.push({ type: "original_pdf_sha256", description: origSha });
    await page.screenshot({ path: `${SHOT}/E-pdf-links-ok.png`, fullPage: true });
  });
});
