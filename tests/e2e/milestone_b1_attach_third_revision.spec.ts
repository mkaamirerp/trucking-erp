/**
 * Milestone B1 — attach a genuinely new third revised RC on load 1010 (demo).
 */
import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import fs from "node:fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REV3 = path.resolve(
  __dirname,
  "../../docs/reports/milestone_b1_evidence/Armstrong_B1_revision3_test.pdf",
);
const SHOT = path.resolve(__dirname, "../../docs/reports/milestone_b1_screenshots");
const email = process.env.E2E_LOGIN_EMAIL ?? "";
const password = process.env.E2E_LOGIN_PASSWORD ?? "";
const LOAD_ID = process.env.E2E_B1_LOAD_ID ?? "1010";

function sha256File(p: string) {
  return createHash("sha256").update(fs.readFileSync(p)).digest("hex");
}

test.describe("Milestone B1 new third revision attach", () => {
  test.skip(!email || !password, "Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD");
  test.skip(!fs.existsSync(REV3), `Missing fixture ${REV3}`);
  test.use({ ignoreHTTPSErrors: true, baseURL: "https://demo.truckerp.me" });

  test("new revision stored_new true, refresh, all downloads, dedupe", async ({ page, request }) => {
    fs.mkdirSync(SHOT, { recursive: true });
    const rev3Sha = sha256File(REV3);
    const origin = "https://demo.truckerp.me";

    await page.goto("/login");
    await page.getByPlaceholder("admin@company.com").fill(email);
    await page.getByPlaceholder("••••••••").fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 90_000 });

    await page.goto(`/loads/${LOAD_ID}`);
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    const rateBefore = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    await page.screenshot({ path: `${SHOT}/04-before-third-revision.png`, fullPage: true });

    const [fileChooser] = await Promise.all([
      page.waitForEvent("filechooser"),
      page.getByRole("button", { name: /Attach revised PDF/i }).click(),
    ]);
    const [attachResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/loads/${LOAD_ID}/rate-confirmation-revised-attachment`) &&
          r.request().method() === "POST",
        { timeout: 120_000 },
      ),
      fileChooser.setFiles(REV3),
    ]);
    expect(attachResp.status()).toBe(200);
    const attachBody = await attachResp.json();
    test.info().annotations.push({ type: "attach_new", description: JSON.stringify(attachBody) });
    expect(attachBody.stored_new).toBe(true);
    expect(attachBody.revision_index).toBe(3);
    expect(attachBody.sha256).toBe(rev3Sha);

    await expect(page.getByText(/revised rate confirmation attached/i)).toBeVisible({ timeout: 15_000 });
    await page.screenshot({ path: `${SHOT}/05-after-third-revision-success.png`, fullPage: true });

    const rateAfterAttach = await page.getByRole("textbox", { name: /linehaul rate/i }).inputValue();
    expect(rateAfterAttach).toBe(rateBefore);

    await page.reload();
    await page.getByTestId("rate-confirmation-pdf-viewer").waitFor({ state: "visible", timeout: 120_000 });
    await page.screenshot({ path: `${SHOT}/06-after-reload-third-revision.png`, fullPage: true });

    const cookies = await page.context().cookies();
    const cookieHeader = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    const headers = { Cookie: cookieHeader, Host: "demo.truckerp.me" };

    const original = await request.get(`${origin}/api/v1/loads/${LOAD_ID}/rate-confirmation-pdf`, {
      headers,
    });
    expect(original.status()).toBe(200);
    const origSha = createHash("sha256").update(await original.body()).digest("hex");

    const revisedCount = Number(original.headers()["x-revised-rate-confirmations"] || "0");
    expect(revisedCount).toBe(3);

    const rev1Sha = createHash("sha256")
      .update(
        await (
          await request.get(`${origin}/api/v1/loads/${LOAD_ID}/rate-confirmation-pdf?revision=1`, {
            headers,
          })
        ).body(),
      )
      .digest("hex");
    const rev2Sha = createHash("sha256")
      .update(
        await (
          await request.get(`${origin}/api/v1/loads/${LOAD_ID}/rate-confirmation-pdf?revision=2`, {
            headers,
          })
        ).body(),
      )
      .digest("hex");
    const rev3 = await request.get(`${origin}/api/v1/loads/${LOAD_ID}/rate-confirmation-pdf?revision=3`, {
      headers,
    });
    expect(rev3.status()).toBe(200);
    const rev3DownloadSha = createHash("sha256").update(await rev3.body()).digest("hex");
    expect(rev3DownloadSha).toBe(rev3Sha);

    test.info().annotations.push({ type: "original_pdf_sha256", description: origSha });
    test.info().annotations.push({ type: "revision_1_sha256", description: rev1Sha });
    test.info().annotations.push({ type: "revision_2_sha256", description: rev2Sha });
    test.info().annotations.push({ type: "revision_3_sha256", description: rev3DownloadSha });

    const [fileChooser2] = await Promise.all([
      page.waitForEvent("filechooser"),
      page.getByRole("button", { name: /Attach revised PDF/i }).click(),
    ]);
    const [dupResp] = await Promise.all([
      page.waitForResponse(
        (r) =>
          r.url().includes(`/loads/${LOAD_ID}/rate-confirmation-revised-attachment`) &&
          r.request().method() === "POST",
        { timeout: 120_000 },
      ),
      fileChooser2.setFiles(REV3),
    ]);
    const dupBody = await dupResp.json();
    test.info().annotations.push({ type: "attach_dup", description: JSON.stringify(dupBody) });
    expect(dupBody.stored_new).toBe(false);
    expect(dupBody.revised_count).toBe(3);

    const afterDup = await request.get(`${origin}/api/v1/loads/${LOAD_ID}/rate-confirmation-pdf`, {
      headers,
    });
    expect(Number(afterDup.headers()["x-revised-rate-confirmations"] || "0")).toBe(3);

    await page.screenshot({ path: `${SHOT}/07-after-duplicate-third-revision.png`, fullPage: true });
  });
});
