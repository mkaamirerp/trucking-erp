/**
 * Task 12b — full demo journey: parse timer, create load, inline PDF headers.
 *
 *   E2E_LOGIN_EMAIL=... E2E_LOGIN_PASSWORD=... \
 *   npx playwright test tests/e2e/task12b_full_journey.spec.ts -c tests/e2e/playwright.config.ts
 */
import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ARMSTRONG_PDF = path.resolve(
  __dirname,
  "../../docs/_review/fixtures/pdf/Armstrong.pdf",
);

const baseURL = process.env.E2E_BASE_URL ?? "https://demo.truckerp.me";
const email = process.env.E2E_LOGIN_EMAIL;
const password = process.env.E2E_LOGIN_PASSWORD;

test.describe("Task 12b demo journey", () => {
  test.skip(!email || !password, "Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD");

  test("parse timer, create load, inline PDF headers", async ({ page, context }) => {
    const checks: Record<string, boolean> = {};
    let createLoadClicks = 0;
    let draftPdfUrl: string | null = null;
    let loadPdfUrl: string | null = null;

    await page.goto(`${baseURL}/login`);
    await page.getByLabel(/email/i).fill(email!);
    await page.getByLabel(/password/i).fill(password!);
    await page.getByRole("button", { name: /sign in|log in/i }).click();
    await page.waitForURL(/\/(dashboard|loads)/, { timeout: 90_000 });

    await page.goto(`${baseURL}/loads/new`);
    await expect(page.getByRole("button", { name: /upload & parse pdf/i })).toBeVisible({
      timeout: 30_000,
    });

    page.on("response", async (res) => {
      const url = res.url();
      if (url.includes("/rate-confirmation-pdf") && res.status() === 200) {
        const cd = (res.headers()["content-disposition"] ?? "").toLowerCase();
        if (url.includes("/load-workspace-drafts/")) draftPdfUrl = url;
        if (/\/loads\/\d+\/rate-confirmation-pdf/.test(url)) loadPdfUrl = url;
        if (url.includes("/load-workspace-drafts/")) checks.draftPdfInline = cd.includes("inline");
        if (/\/loads\/\d+\/rate-confirmation-pdf/.test(url))
          checks.loadPdfInline = cd.includes("inline");
      }
    });

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(ARMSTRONG_PDF);

    const parsingBtn = page.getByRole("button", { name: /^parsing/i });
    await expect(parsingBtn).toBeVisible({ timeout: 15_000 });
    checks.parseTimerVisible = true;
    await expect(parsingBtn).toHaveText(/Parsing…\s+[1-9]\d*s/, { timeout: 120_000 });
    checks.parseTimerCounted = true;

    await expect(page.getByTestId("rate-confirmation-pdf-viewer")).toBeVisible({
      timeout: 60_000,
    });
    checks.pdfVisibleAfterParse = true;
    await page.screenshot({ path: "/tmp/task12b-after-parse.png", fullPage: true });

    const createBtn = page.getByRole("button", { name: /^create load$/i });
    await expect(createBtn).toBeEnabled({ timeout: 60_000 });
    await createBtn.click();
    createLoadClicks += 1;

    await page.waitForURL(/\/loads\/\d+(?:\?|$)/, { timeout: 120_000 });
    checks.urlIsLoadDetail = !page.url().includes("/loads/draft/");
    await expect(page.getByText(/ready/i).first()).toBeVisible({ timeout: 60_000 });
    checks.statusReady = true;
    await expect(page.getByTestId("rate-confirmation-pdf-viewer")).toBeVisible({ timeout: 30_000 });
    checks.pdfOnLoadPage = true;
    await expect(page.getByText(/status & assignment/i)).toBeVisible({ timeout: 30_000 });
    checks.statusAssignment = true;
    await page.screenshot({ path: "/tmp/task12b-after-create.png", fullPage: true });

    const openTab = page.getByRole("link", { name: /open in new tab/i });
    if (await openTab.isVisible()) {
      const [popup] = await Promise.all([context.waitForEvent("page"), openTab.click()]);
      await popup.waitForLoadState("domcontentloaded");
      checks.openInNewTab = true;
    }

    await page.waitForTimeout(2000);
    if (draftPdfUrl) checks.draftPdfFetched = true;
    if (loadPdfUrl) checks.loadPdfFetched = true;

    test.info().annotations.push(
      { type: "finalUrl", description: page.url() },
      { type: "createLoadClicks", description: String(createLoadClicks) },
      { type: "checks", description: JSON.stringify(checks) },
    );

    expect(checks.parseTimerVisible).toBe(true);
    expect(checks.parseTimerCounted).toBe(true);
    expect(checks.urlIsLoadDetail).toBe(true);
    expect(checks.statusReady).toBe(true);
    expect(checks.pdfOnLoadPage).toBe(true);
    expect(checks.statusAssignment).toBe(true);
    expect(createLoadClicks).toBe(1);
    expect(checks.draftPdfInline ?? checks.loadPdfInline).toBeTruthy();
    expect(checks.loadPdfInline).toBe(true);
  });
});
