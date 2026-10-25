/**
 * Task 17 — unified load workspace layout proof (requires demo credentials).
 * E2E_LOGIN_EMAIL=... E2E_LOGIN_PASSWORD=... npx playwright test tests/e2e/task17_unified_load_layout.spec.ts
 */
import { test, expect } from "@playwright/test";

const email = process.env.E2E_LOGIN_EMAIL;
const password = process.env.E2E_LOGIN_PASSWORD;

test.describe("Task 17 unified load layout", () => {
  test.skip(!email || !password, "Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD");

  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/login");
    await page.getByPlaceholder("admin@company.com").fill(email!);
    await page.getByPlaceholder("••••••••").fill(password!);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL(/\/(dashboard|loads)/);
  });

  test("condensed form and verification panel on load workspace", async ({ page }) => {
    await page.goto("/loads/new");
    await expect(page.getByTestId("load-workspace-verification-panel")).toBeVisible();
    await expect(page.getByTestId("load-workspace-condensed")).toBeVisible();
    await page.screenshot({ path: "tests/e2e/screenshots/task17-new-load.png", fullPage: true });
  });
});
