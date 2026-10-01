import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  getFuelProcessedBatch: vi.fn(),
  getFuelBvdImportRows: vi.fn(),
  getFuelNationwideImportRows: vi.fn(),
}));

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    getFuelProcessedBatch: apiMocks.getFuelProcessedBatch,
    getFuelBvdImportRows: apiMocks.getFuelBvdImportRows,
    getFuelNationwideImportRows: apiMocks.getFuelNationwideImportRows,
  };
});

function nationwideEvidenceMock() {
  return function NationwideEvidenceMock() {
    return <div data-testid="nationwide-source-evidence-panel-mock">Nationwide native evidence</div>;
  };
}

function bvdEvidenceMock() {
  return function BvdEvidenceMock() {
    return <div data-testid="bvd-source-evidence-panel-mock">BVD native evidence</div>;
  };
}

vi.mock("./processedFuelProviderRenderers", () => ({
  getProcessedFuelEvidenceRenderer: (code: string) => {
    if (code === "NATIONWIDE") return nationwideEvidenceMock();
    if (code === "BVD") return bvdEvidenceMock();
    return null;
  },
}));

import ProcessedFuelStatementShell from "./ProcessedFuelStatementShell";

const bvdTxn = {
  id: 1,
  import_id: "bvd-import-1",
  row_type: "TRANSACTION",
  transaction_date: "2025-01-02",
  prod: "DF",
  final_amt: "10.00",
  cur: "US",
};

describe("ProcessedFuelStatementShell", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    apiMocks.getFuelProcessedBatch.mockResolvedValue({
      batch_id: 6,
      source_import_ref: "bvd-import-1",
      canonical_transactions: [{ id: 1, batch_id: 6, product_code_raw: "DF", total_amount: "10", currency_raw: "US" }],
      total_amount: "10",
      currency: "US",
    });
    apiMocks.getFuelBvdImportRows.mockResolvedValue([bvdTxn]);
    apiMocks.getFuelNationwideImportRows.mockResolvedValue([
      { id: 1, row_type: "TRANSACTION", import_id: "nw-1", product: "TA", total: "5", currency: "USD" },
    ]);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function renderShell(providerCode: string, providerLabel: string) {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <ProcessedFuelStatementShell
          batchId={6}
          providerCode={providerCode}
          providerLabel={providerLabel}
          invoiceNumber="838710"
          transactionCount={42}
          controlCount={53}
          sourceImportRef={providerCode === "BVD" ? "bvd-import-1" : "nw-1"}
        />,
      );
      await new Promise((r) => setTimeout(r, 50));
    });
  }

  it("does not render duplicate Canonical transactions block for BVD", async () => {
    await renderShell("BVD", "BVD");
    expect(container.textContent?.toLowerCase()).not.toContain("canonical transactions");
    expect(container.querySelector('[data-testid="fuel-processed-canonical-6"]')).toBeNull();
    expect(container.querySelector('[data-testid="truckerp-processed-fuel-workspace"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="bvd-source-evidence-panel-mock"]')).toBeTruthy();
  });

  it("uses the same TruckERP workspace shell for Nationwide", async () => {
    apiMocks.getFuelProcessedBatch.mockResolvedValue({
      batch_id: 8,
      source_import_ref: "nw-1",
      canonical_transactions: [],
      usd_transaction_total: "100",
    });
    await renderShell("NATIONWIDE", "Nationwide");
    expect(container.textContent?.toLowerCase()).not.toContain("canonical transactions");
    expect(container.querySelector('[data-testid="truckerp-processed-fuel-workspace"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="nationwide-source-evidence-panel-mock"]')).toBeTruthy();
  });
});
