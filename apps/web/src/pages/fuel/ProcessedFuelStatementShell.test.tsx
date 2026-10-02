import { readFileSync } from "node:fs";
import { resolve } from "node:path";
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

const recordOverlayMock = vi.hoisted(() => vi.fn());

vi.mock("./processedFuelProviderRenderers", () => ({
  getProcessedFuelRecordOverlay: (code: string) => {
    if (code === "BVD" || code === "NATIONWIDE") {
      return function OverlayMock(props: { sourceImportRef: string; onClose?: () => void }) {
        recordOverlayMock(props);
        return (
          <div data-testid={`${code.toLowerCase()}-record-overlay-mock`}>
            overlay:{props.sourceImportRef}
            <button type="button" onClick={() => props.onClose?.()}>Close</button>
          </div>
        );
      };
    }
    return null;
  },
}));

import ProcessedFuelStatementShell from "./ProcessedFuelStatementShell";
import { getProcessedFuelRecordOverlay } from "./processedFuelProviderRenderers";

const bvdTxn = {
  id: 1,
  import_id: "bvd-import-1",
  row_type: "TRANSACTION",
  transaction_date: "2025-01-02",
  prod: "DF",
  final_amt: "10.00",
  cur: "US",
};

describe("ProcessedFuelStatementShell architecture", () => {
  it("does not mount provider evidence renderers on the main expand path", () => {
    const src = readFileSync(
      resolve(import.meta.dirname, "ProcessedFuelStatementShell.tsx"),
      "utf8",
    );
    expect(src).not.toMatch(/getProcessedFuelEvidenceRenderer/);
    expect(src).not.toMatch(/fuel-processed-evidence/);
    expect(src).not.toMatch(/EvidencePanel/);
  });
});

describe("ProcessedFuelStatementShell", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    recordOverlayMock.mockReset();
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
    if (root) act(() => root.unmount());
    if (container?.parentNode) container.remove();
  });

  async function renderShell(
    providerCode: string,
    providerLabel: string,
    options?: { onOpenSource?: () => void; sourceImportRef?: string },
  ) {
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
          sourceImportRef={options?.sourceImportRef ?? (providerCode === "BVD" ? "bvd-import-1" : "nw-1")}
          onOpenSource={options?.onOpenSource}
        />,
      );
      await new Promise((r) => setTimeout(r, 50));
    });
  }

  it("expanded BVD row shows TruckERP workspace only (no inline source evidence)", async () => {
    await renderShell("BVD", "BVD");
    expect(container.textContent?.toLowerCase()).not.toContain("canonical transactions");
    expect(container.querySelector('[data-testid="fuel-processed-canonical-6"]')).toBeNull();
    expect(container.querySelector('[data-testid="truckerp-processed-fuel-workspace"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="fuel-processed-evidence-6"]')).toBeNull();
    expect(container.textContent).not.toMatch(/Source evidence/i);
  });

  it("expanded Nationwide row shows TruckERP workspace only (no inline native statement)", async () => {
    apiMocks.getFuelProcessedBatch.mockResolvedValue({
      batch_id: 8,
      source_import_ref: "nw-1",
      canonical_transactions: [],
      usd_transaction_total: "100",
    });
    await renderShell("NATIONWIDE", "Nationwide", { sourceImportRef: "nw-1" });
    expect(container.querySelector('[data-testid="truckerp-processed-fuel-workspace"]')).toBeTruthy();
    expect(container.querySelector('[data-testid="fuel-processed-evidence-8"]')).toBeNull();
    expect(container.textContent).not.toMatch(/Source evidence/i);
    expect(container.textContent).not.toContain("Provider Precision Gates");
  });

  it("Open source invokes parent handler with lineage from batch detail", async () => {
    const onOpenSource = vi.fn();
    await renderShell("BVD", "BVD", { onOpenSource });
    const btn = container.querySelector('[data-testid="fuel-open-source-6"]') as HTMLButtonElement;
    expect(btn?.textContent).toBe("Open source");
    expect(container.textContent).not.toContain("Open full invoice");
    await act(async () => {
      btn.click();
    });
    expect(onOpenSource).toHaveBeenCalledTimes(1);
    expect(apiMocks.getFuelProcessedBatch).toHaveBeenCalledWith(6);
  });

  it("BVD Open source overlay uses sourceImportRef (not undefined import path)", async () => {
    const Overlay = getProcessedFuelRecordOverlay("BVD");
    expect(Overlay).toBeTruthy();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <Overlay sourceImportRef="bvd-import-1" variant="overlay" onClose={() => undefined} />,
      );
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(recordOverlayMock).toHaveBeenCalledWith(
      expect.objectContaining({ sourceImportRef: "bvd-import-1" }),
    );
    expect(container.textContent).not.toContain("undefined");
  });

  it("Nationwide Open source overlay uses sourceImportRef", async () => {
    const Overlay = getProcessedFuelRecordOverlay("NATIONWIDE");
    expect(Overlay).toBeTruthy();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <Overlay sourceImportRef="nw-1" variant="overlay" onClose={() => undefined} />,
      );
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(recordOverlayMock).toHaveBeenCalledWith(
      expect.objectContaining({ sourceImportRef: "nw-1" }),
    );
  });
});
