import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FuelBvdCompletedBasic } from "../../api";
import FuelRecentActivitySection from "./FuelRecentActivitySection";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return { ...actual, getFuelBvdImportRows: vi.fn() };
});

const row972201: FuelBvdCompletedBasic = {
  provider: "BVD",
  import_id: "import-972201",
  invoice_number: "972201",
  review_status: "SOURCE_REVIEWED",
  read_only: true,
  card_number: "4237111",
  period_start: "2026-07-22 00:00:00",
  period_end: "2026-07-28 23:59:59",
  due_date: "2026-07-30 23:59:59",
  invoice_disc_amt: "0.00",
  total_amount: "3,421.01",
  currency: "CN",
  unit_count: 2,
  unit_numbers: ["1100", "1104"],
  categories: [],
  taxes: [],
};

describe("FuelRecentActivitySection invoice row columns", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("renders finalized invoice columns for 972201", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <MemoryRouter>
          <FuelRecentActivitySection activity={[row972201]} loading={false} />
        </MemoryRouter>,
      );
    });

    const thead = container.querySelector("thead")?.textContent ?? "";
    expect(thead).toMatch(/Account \/ Card/i);
    expect(thead).toMatch(/Period/i);
    expect(thead).toMatch(/CAD Total/i);
    expect(thead).toMatch(/USD Total/i);
    expect(thead).not.toMatch(/Processed/i);
    expect(thead).not.toMatch(/Units/i);

    expect(container.textContent).toContain("BVD");
    expect(container.textContent).toContain("972201");
    expect(container.querySelector('[data-testid="fuel-activity-card-import-972201"]')?.textContent).toBe(
      "4237111",
    );
    expect(container.querySelector('[data-testid="fuel-activity-period-import-972201"]')?.textContent).toBe(
      "Jul 22–28",
    );
    expect(container.querySelector('[data-testid="fuel-activity-due-import-972201"]')?.textContent).toBe(
      "Jul 30, 2026",
    );
    expect(container.querySelector('[data-testid="fuel-activity-payment-import-972201"]')?.textContent).toBe(
      "Not tracked",
    );
    expect(container.querySelector('[data-testid="fuel-activity-discount-import-972201"]')?.textContent).toBe(
      "0.00",
    );
    expect(container.querySelector('[data-testid="fuel-activity-cad-total-import-972201"]')?.textContent).toBe(
      "3,421.01",
    );
    expect(container.querySelector('[data-testid="fuel-activity-usd-total-import-972201"]')?.textContent).toBe(
      "—",
    );
    expect(container.querySelector('[data-testid="fuel-activity-invoice-total-import-972201"]')?.textContent).toBe(
      "3,421.01 CN",
    );
    expect(
      container.querySelector('[data-testid="fuel-activity-invoice-total-import-972201"]')?.getAttribute(
        "data-source-currency",
      ),
    ).toBe("CN");
    expect(container.textContent).not.toContain("Completed");
  });
});
