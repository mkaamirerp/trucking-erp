/**
 * Milestone B1 — Attach revised RC on existing load (demo).
 */
import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import fs from "node:fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ARM2000 = path.resolve(
  "/home/admin/archive/truckerp_reparse_audit_2026-10-30/fixtures_reparse/Armstrong_TEST_rate_2000.pdf",
);
const SHOT = path.resolve(__dirname, "../../docs/reports/milestone_b1_screenshots");
const email = process.env.E2E_LOGIN_EMAIL ?? "";
const password = process.env.E2E_LOGIN_PASSWORD ?? "";
const LOAD_ID = process.env.E2E_B1_LOAD_ID ?? "1010";

function sha256File(p: string) {
  return createHash("sha256").update(fs.readFileSync(p)).digest("hex");
}

test.describe("Milestone B1 attach revised PDF", () => {
  test.skip(!email || !password, "Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD");
  test.skip(!fs.existsSync(ARM2000), `Missing fixture ${ARM2000}`);
  test.use({ ignoreHTTPSErrors: true });

  test("attach, dedupe, downloads and unchanged load fields", async ({ page, request }) => {
    fs.mkdirSync(SHOT, { recursive: true });
    const arm2000Sha = sha256File(ARM2000);

    await page.goto("/login");
    await page.getByPlaceholder("admin@company.com").fill(email);
    await page.getByPlaceholder("••••••••").fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 90_000 });

    await page.goto(`/loads/${LOAD_ID}`);
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    const rateBefore = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    await page.screenshot({ path: `${SHOT}/01-before-attach.png`, fullPage: true });

    const [fileChooser] = await Promise.all([
      page.waitForEvent("filechooser"),
      page.getByRole("button", { name: /Attach revised PDF/i }).click(),
    ]);
    const [attachResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/loads/${LOAD_ID}/rate-confirmation-revised-attachment`) &&
          r.request().method() === "POST",
        { timeout: 60_000 },
      ),
      fileChooser.setFiles(ARM2000),
    ]);
    expect(attachResp.status()).toBe(200);
    const attachBody = await attachResp.json();
    test.info().annotations.push({ type: "attach1", description: JSON.stringify(attachBody) });
    await page.screenshot({ path: `${SHOT}/02-after-first-attach.png`, fullPage: true });

    const rateAfterAttach = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    expect(rateAfterAttach).toBe(rateBefore);

    const cookies = await page.context().cookies();
    const cookieHeader = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    const origin = "https://demo.truckerp.me";

    const original = await request.get(`${origin}/api/v1/loads/${LOAD_ID}/rate-confirmation-pdf`, {
      headers: { Cookie: cookieHeader, Host: "demo.truckerp.me" },
    });
    expect(original.status()).toBe(200);
    const origBody = await original.body();
    const origSha = createHash("sha256").update(origBody).digest("hex");

    const revisedCount = Number(original.headers()["x-revised-rate-confirmations"] || "0");
    expect(revisedCount).toBeGreaterThan(0);
    const revised = await request.get(
      `${origin}/api/v1/loads/${LOAD_ID}/rate-confirmation-pdf?revision=${revisedCount}`,
      { headers: { Cookie: cookieHeader, Host: "demo.truckerp.me" } },
    );
    expect(revised.status()).toBe(200);
    const revBody = await revised.body();
    const revSha = createHash("sha256").update(revBody).digest("hex");
    expect(revSha).toBe(arm2000Sha);

    const [fileChooser2] = await Promise.all([
      page.waitForEvent("filechooser"),
      page.getByRole("button", { name: /Attach revised PDF/i }).click(),
    ]);
    const [dupResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/loads/${LOAD_ID}/rate-confirmation-revised-attachment`) &&
          r.request().method() === "POST",
        { timeout: 60_000 },
      ),
      fileChooser2.setFiles(ARM2000),
    ]);
    expect(dupResp.status()).toBe(200);
    const dupBody = await dupResp.json();
    expect(dupBody.stored_new).toBe(false);
    test.info().annotations.push({ type: "attach2", description: JSON.stringify(dupBody) });
    await page.screenshot({ path: `${SHOT}/03-after-duplicate-attach.png`, fullPage: true });

    test.info().annotations.push({ type: "original_pdf_sha256", description: origSha });
    test.info().annotations.push({ type: "revised_pdf_sha256", description: revSha });
  });
});
