/**
 * Task 12 — browser: parse Armstrong.pdf on /loads/new, Create load → /loads/:id.
 *
 * Run (requires demo tenant admin credentials):
 *   E2E_LOGIN_EMAIL=... E2E_LOGIN_PASSWORD=... npx playwright test tests/e2e/task12_create_load_navigate.spec.ts
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

test.describe("Task 12 create load navigation", () => {
  test.skip(!email || !password, "Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD");

  test("Create load lands on load detail with Ready status", async ({ page }) => {
    let clickCount = 0;

    await page.goto(`${baseURL}/login`);
    await page.getByLabel(/email/i).fill(email!);
    await page.getByLabel(/password/i).fill(password!);
    await page.getByRole("button", { name: /sign in|log in/i }).click();
    await page.waitForURL(/\/(dashboard|loads)/, { timeout: 60_000 });

    await page.goto(`${baseURL}/loads/new`);
    await expect(page.getByRole("heading", { name: /new load/i })).toBeVisible({ timeout: 30_000 });

    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles(ARMSTRONG_PDF);
    await expect(page.getByText(/parse|applied|fields/i).first()).toBeVisible({ timeout: 180_000 });

    const createBtn = page.getByRole("button", { name: /^create load$/i });
    await expect(createBtn).toBeEnabled({ timeout: 60_000 });
    await createBtn.click();
    clickCount += 1;

    await page.waitForURL(/\/loads\/\d+/, { timeout: 120_000 });
    await expect(page).not.toHaveURL(/\/loads\/draft\//);
    await expect(page.getByText(/ready/i).first()).toBeVisible({ timeout: 60_000 });
    await expect(page.getByTestId("rate-confirmation-pdf-viewer")).toBeVisible({ timeout: 60_000 });

    test.info().annotations.push({ type: "clickCount", description: String(clickCount) });
  });
});
