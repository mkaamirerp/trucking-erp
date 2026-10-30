/**
 * Milestone B2 frontend verification (demo) — uses global-setup storageState (one login per run).
 */
import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import fs from "node:fs";
import { DEMO_AUTH_FILE } from "./global-setup";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SHOT = path.resolve(__dirname, "../../docs/reports/milestone_b2_screenshots");
const EVIDENCE = path.resolve(__dirname, "../../docs/reports/milestone_b2_evidence");
const LOAD_ID_ENV = process.env.E2E_B1_LOAD_ID ?? "1010";
const ARMSTRONG_PDF = path.resolve(__dirname, "../../docs/_review/fixtures/pdf/Armstrong.pdf");
const REVISED_RC_PDF = path.resolve(
  "/home/admin/archive/truckerp_reparse_audit_2026-10-30/fixtures_reparse/Armstrong_TEST_rate_2000.pdf",
);

let activeLoadId = Number(LOAD_ID_ENV);

test.describe.configure({ mode: "serial" });

test.describe("Milestone B2 frontend verification", () => {
  test.skip(!process.env.E2E_LOGIN_EMAIL || !process.env.E2E_LOGIN_PASSWORD, "Set E2E_LOGIN_* env");
  test.skip(!fs.existsSync(DEMO_AUTH_FILE), "Run playwright with global-setup (default config) first");

  test.use({
    ignoreHTTPSErrors: true,
    baseURL: "https://demo.truckerp.me",
    storageState: DEMO_AUTH_FILE,
  });

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext({
      storageState: DEMO_AUTH_FILE,
      baseURL: "https://demo.truckerp.me",
      ignoreHTTPSErrors: true,
    });
    const req = ctx.request;

    let probe = await req.get(`/api/v1/loads/${activeLoadId}`);
    if (!probe.ok()) {
      const list = await req.get("/api/v1/loads?limit=1");
      const listed = await list.json();
      if (listed.total > 0 && listed.items?.[0]?.id) {
        activeLoadId = listed.items[0].id;
        probe = await req.get(`/api/v1/loads/${activeLoadId}`);
      }
    }

    if (!probe.ok()) {
      test.skip(!fs.existsSync(ARMSTRONG_PDF), `Missing ${ARMSTRONG_PDF}`);
      const page = await ctx.newPage();
      await page.goto("/loads/new");
      await page.locator('input[type="file"]').first().setInputFiles(ARMSTRONG_PDF);
      await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 240_000 });
      await page.getByRole("button", { name: /^create load$/i }).click();
      for (let attempt = 0; attempt < 90; attempt++) {
        const m = page.url().match(/\/loads\/(\d+)/);
        if (m) {
          activeLoadId = Number(m[1]);
          break;
        }
        const list = await req.get("/api/v1/loads?limit=1");
        const listed = await list.json();
        if (listed.total > 0 && listed.items?.[0]?.id) {
          activeLoadId = listed.items[0].id;
          break;
        }
        await page.waitForTimeout(2000);
      }
      if (!activeLoadId) {
        await ctx.close();
        throw new Error("Create load did not produce a load row within timeout.");
      }
      await page.close();
    }

    const revisedHeader = await req.get(`/api/v1/loads/${activeLoadId}/rate-confirmation-pdf`);
    if (!revisedHeader.ok()) {
      await ctx.close();
      throw new Error(`Load ${activeLoadId} has no rate confirmation PDF (${revisedHeader.status()}).`);
    }

    test.skip(!fs.existsSync(REVISED_RC_PDF), `Missing ${REVISED_RC_PDF}`);
    const page = await ctx.newPage();
    await page.goto(`/loads/${activeLoadId}`);
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    const [fc] = await Promise.all([
      page.waitForEvent("filechooser"),
      page.getByRole("button", { name: /Attach revised PDF/i }).click(),
    ]);
    const [attachResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/loads/${activeLoadId}/rate-confirmation-revised-attachment`) &&
          r.request().method() === "POST",
        { timeout: 120_000 },
      ),
      fc.setFiles(REVISED_RC_PDF),
    ]);
    if (!attachResp.ok()) {
      const t = await attachResp.text();
      await ctx.close();
      throw new Error(`Attach revised PDF failed (${attachResp.status()}): ${t.slice(0, 300)}`);
    }
    await ctx.close();
    fs.mkdirSync(EVIDENCE, { recursive: true });
    fs.writeFileSync(path.join(EVIDENCE, "active_load_id.txt"), String(activeLoadId));
  });

  test("1 — Parse PDF shows extraction; load form unchanged", async ({ page }) => {
    fs.mkdirSync(SHOT, { recursive: true });
    await page.goto(`/loads/${activeLoadId}`);
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    await expect(page.getByTestId("parse-revised-pdf")).toBeVisible();
    const rateBefore = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    await page.screenshot({ path: `${SHOT}/verify-01-before-parse.png`, fullPage: true });

    const parseRespPromise = page.waitForResponse(
      (r) =>
        r.url().includes(`/loads/${activeLoadId}/rate-confirmation-parse-reference`) &&
        r.request().method() === "POST",
      { timeout: 300_000 },
    );
    await page.getByTestId("parse-revised-pdf").click();
    const parseResp = await parseRespPromise;
    expect(parseResp.status()).toBe(200);
    const parseBody = await parseResp.json();
    test.info().annotations.push({ type: "parse_reference", description: JSON.stringify(parseBody).slice(0, 2000) });

    await page.getByTestId("parse-reference-review").waitFor({ state: "visible", timeout: 30_000 });
    await expect(page.locator("#parse-reference-title")).toContainText(/parse pdf/i);
    await expect(page.getByText("Extracted PDF", { exact: true })).toBeVisible();
    const rowCount = await page.locator("table tbody tr").count();
    expect(rowCount).toBeGreaterThan(0);

    const rateAfterOpen = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    expect(rateAfterOpen).toBe(rateBefore);
    await page.screenshot({ path: `${SHOT}/verify-02-parse-panel.png`, fullPage: true });
  });

  test("2 — Use extracted rate only; Save; reopen matches", async ({ page }) => {
    await page.goto(`/loads/${activeLoadId}`);
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    const rateBefore = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();

    await page.getByTestId("parse-revised-pdf").click();
    await page.getByTestId("parse-reference-review").waitFor({ state: "visible", timeout: 300_000 });

    const useRate = page.getByTestId("parse-use-field-rate");
    await expect(useRate).toBeVisible({ timeout: 15_000 });
    await useRate.click();
    const rateInForm = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    expect(rateInForm).not.toBe(rateBefore);
    await page.getByTestId("parse-reference-close").click();
    await page.screenshot({ path: `${SHOT}/verify-03-rate-in-form-not-saved.png`, fullPage: true });

    await page.getByRole("button", { name: /^save load$/i }).click();
    await expect(page.getByRole("button", { name: /^saved$/i })).toBeVisible({ timeout: 90_000 });
    await page.screenshot({ path: `${SHOT}/verify-04-after-save.png`, fullPage: true });

    await page.reload();
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    const rateAfterReload = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    expect(rateAfterReload).toBe(rateInForm);
    test.info().annotations.push({ type: "rate_before", description: rateBefore });
    test.info().annotations.push({ type: "rate_after_save", description: rateAfterReload });
  });

  test("3 — Parse again, close without Use; form unchanged", async ({ page }) => {
    await page.goto(`/loads/${activeLoadId}`);
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    const rateBefore = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();

    await page.getByTestId("parse-revised-pdf").click();
    await page.getByTestId("parse-reference-review").waitFor({ state: "visible", timeout: 300_000 });
    await page.getByTestId("parse-reference-close").click();
    await expect(page.getByTestId("parse-reference-review")).toBeHidden();

    const rateAfter = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    expect(rateAfter).toBe(rateBefore);
    await page.screenshot({ path: `${SHOT}/verify-05-close-without-use.png`, fullPage: true });
  });

  test("4 — Original and revised PDFs download with stable hashes", async ({ page, request }) => {
    const cookies = await page.context().cookies();
    const cookieHeader = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    const headers = { Cookie: cookieHeader, Host: "demo.truckerp.me" };
    const origin = "https://demo.truckerp.me";

    const orig = await request.get(`${origin}/api/v1/loads/${activeLoadId}/rate-confirmation-pdf`, { headers });
    expect(orig.status()).toBe(200);
    const origSha = createHash("sha256").update(await orig.body()).digest("hex");
    const n = Number(orig.headers()["x-revised-rate-confirmations"] || "0");
    expect(n).toBeGreaterThan(0);

    const revShas: string[] = [];
    for (let rev = 1; rev <= n; rev++) {
      const r = await request.get(`${origin}/api/v1/loads/${activeLoadId}/rate-confirmation-pdf?revision=${rev}`, {
        headers,
      });
      expect(r.status()).toBe(200);
      revShas.push(createHash("sha256").update(await r.body()).digest("hex"));
    }

    fs.mkdirSync(EVIDENCE, { recursive: true });
    fs.writeFileSync(
      path.join(EVIDENCE, "pdf_download_verification.json"),
      JSON.stringify({ load_id: activeLoadId, original_sha256: origSha, revised_count: n, revised_sha256: revShas }, null, 2),
    );
    test.info().annotations.push({ type: "original_sha256", description: origSha });
    test.info().annotations.push({ type: "revised_sha256_list", description: revShas.join(",") });

    await page.goto(`/loads/${activeLoadId}`);
    await page.screenshot({ path: `${SHOT}/verify-06-pdf-retention.png`, fullPage: true });
  });
});
