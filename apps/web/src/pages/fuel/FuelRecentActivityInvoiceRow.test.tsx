import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { FuelProcessedSummary } from "../../api";
import FuelRecentActivitySection from "./FuelRecentActivitySection";

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return { ...actual, getFuelBvdImportRows: vi.fn() };
});

const summary972201: FuelProcessedSummary = {
  batch_id: 972201,
  provider_code: "BVD",
  source_import_ref: "import-972201",
  source_storage_ref: null,
  account_reference: "4237111",
  invoice_number: "972201",
  period_start: "2026-07-22 00:00:00",
  period_end: "2026-07-28 23:59:59",
  due_date: "2026-07-30 23:59:59",
  finalized_at: "2026-07-29T12:00:00Z",
  batch_status: "FINALIZED",
  transaction_count: 2,
  control_count: 0,
  currency_totals: [{ currency: "CN", amount: "3,421.01" }],
  currency_financial_summaries: [
    { currency: "CN", total_amount: "3,421.01", discount_amount: "0.00" },
  ],
  provider_control_totals: [],
  cad_transaction_total: "3,421.01",
  usd_transaction_total: "0.00",
  usd_provider_control: null,
  purchase_card_count: 1,
  purchase_card_numbers: ["4237111"],
  total_amount: "3,421.01",
  currency: "CN",
  read_only: true,
  review_status: "SOURCE_REVIEWED",
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
          <FuelRecentActivitySection activity={[summary972201]} loading={false} />
        </MemoryRouter>,
      );
    });

    const thead = container.querySelector("thead")?.textContent ?? "";
    expect(thead).toMatch(/Account \/ Card/i);
    expect(thead).toMatch(/Period/i);
    expect(thead).toMatch(/Cur/i);
    expect(thead).toMatch(/Discount/i);
    expect(thead).toMatch(/Total/i);
    expect(thead).toMatch(/Invoice Total/i);
    expect(thead).not.toMatch(/Processed/i);
    expect(thead).not.toMatch(/Units/i);

    expect(container.textContent).toContain("BVD");
    expect(container.textContent).toContain("972201");
    expect(container.querySelector('[data-testid="fuel-activity-card-972201"]')?.textContent).toBe(
      "4237111",
    );
    expect(container.textContent).toContain("Jul 22–28");
    expect(container.textContent).toContain("Jul 30, 2026");
    expect(container.textContent).toContain("Not tracked");
    expect(container.textContent).toContain("0.00");
    expect(container.querySelector('[data-testid="fuel-activity-currency-line-CN"]')?.textContent).toBe(
      "CN",
    );
    expect(
      container.querySelector('[data-testid="fuel-activity-invoice-total-line-CN"]')?.textContent,
    ).toBe("3,421.01 CN");
    expect(container.textContent).not.toContain("Completed");
  });
});
