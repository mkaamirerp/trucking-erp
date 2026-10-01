import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FuelProcessedSummary } from "../../api";

const apiMocks = vi.hoisted(() => ({
  getFuelProcessedBatch: vi.fn(),
  getFuelBvdImportRows: vi.fn(),
  getFuelNationwideImportRows: vi.fn(),
  getFuelNationwideSourceReconciliation: vi.fn(),
}));

vi.mock("./processedFuelProviderRenderers", () => ({
  getProcessedFuelEvidenceRenderer: (code: string) => {
    if (code === "NATIONWIDE") {
      return function NationwideEvidenceMock() {
        return <div data-testid="nationwide-evidence-mock">Nationwide evidence</div>;
      };
    }
    return null;
  },
  getProcessedFuelRecordOverlay: () => null,
}));

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    getFuelProcessedBatch: apiMocks.getFuelProcessedBatch,
    getFuelBvdImportRows: apiMocks.getFuelBvdImportRows,
    getFuelNationwideImportRows: apiMocks.getFuelNationwideImportRows,
    getFuelNationwideSourceReconciliation: apiMocks.getFuelNationwideSourceReconciliation,
  };
});

import FuelRecentActivitySection from "./FuelRecentActivitySection";

const nationwideSummary: FuelProcessedSummary = {
  batch_id: 8,
  provider_code: "NATIONWIDE",
  source_import_ref: "eab57e99-c4bf-40e3-ba2e-21141729a8d8",
  source_storage_ref: null,
  account_reference: "ACCT",
  invoice_number: "20250522B-06142026",
  period_start: null,
  period_end: null,
  due_date: null,
  finalized_at: "2026-03-01T12:00:00Z",
  batch_status: "FINALIZED",
  transaction_count: 12,
  control_count: 14,
  currency_totals: [
    { currency: "CAD", amount: "1263.85" },
    { currency: "USD", amount: "5197.67" },
  ],
  provider_control_totals: [{ currency: "USD", amount: "5197.69" }],
  cad_transaction_total: "1263.85",
  usd_transaction_total: "5197.67",
  usd_provider_control: "5197.69",
  purchase_card_count: 0,
  purchase_card_numbers: [],
  total_amount: "",
  currency: null,
  read_only: true,
  review_status: "SOURCE_REVIEWED",
};

describe("FuelRecentActivitySection", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    apiMocks.getFuelProcessedBatch.mockResolvedValue({
      ...nationwideSummary,
      canonical_transactions: [{ id: 1, batch_id: 8, total_amount: "10", currency_raw: "USD" }],
    });
    apiMocks.getFuelNationwideImportRows.mockResolvedValue([
      { id: 1, row_type: "TRANSACTION", import_id: nationwideSummary.source_import_ref },
    ]);
    apiMocks.getFuelNationwideSourceReconciliation.mockResolvedValue({});
    apiMocks.getFuelBvdImportRows.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function renderSection() {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <FuelRecentActivitySection
          activity={[nationwideSummary]}
          loading={false}
          onOpenProcessed={vi.fn()}
        />,
      );
      await new Promise((r) => setTimeout(r, 0));
    });
  }

  it("expands Nationwide into shared processed shell, not BVD workspace", async () => {
    await renderSection();
    const expandBtn = container.querySelector(
      `[data-testid="fuel-activity-invoice-${nationwideSummary.batch_id}"] button`,
    ) as HTMLButtonElement;
    await act(async () => {
      expandBtn.click();
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(container.querySelector(`[data-testid="fuel-processed-shell-8"]`)).toBeTruthy();
    expect(container.textContent).toContain("Nationwide 20250522B-06142026");
    expect(container.textContent).not.toContain("BVD 20250522B");
    expect(apiMocks.getFuelBvdImportRows).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="nationwide-evidence-mock"]')).toBeTruthy();
    expect(apiMocks.getFuelProcessedBatch).toHaveBeenCalledWith(8);
  });
});
