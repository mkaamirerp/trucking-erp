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

const processedOverlayMock = vi.hoisted(() => vi.fn());

vi.mock("./processedFuelProviderRenderers", () => ({
  getProcessedFuelRecordOverlay: () =>
    function MockOverlay(props: { sourceImportRef: string; onClose?: () => void }) {
      processedOverlayMock(props);
      return (
        <div data-testid="fuel-processed-overlay-from-activity">
          <button type="button" onClick={() => props.onClose?.()}>Close overlay</button>
        </div>
      );
    },
}));

import FuelRecentActivitySection from "./FuelRecentActivitySection";
import {
  MANUAL_ENTRY_ACTIVITY_GROUP_BATCH_ID,
  buildFuelRecentActivityDisplay,
} from "./fuelRecentActivityDisplay";
import { getProcessedFuelRecordOverlay } from "./processedFuelProviderRenderers";

const bvdTxn = {
  id: 1,
  import_id: "bvd-uuid-1",
  row_type: "TRANSACTION",
  transaction_date: "2025-01-02",
  prod: "DF",
  final_amt: "10.00",
  cur: "US",
};

const bvdSummary: FuelProcessedSummary = {
  batch_id: 42,
  provider_code: "BVD",
  source_import_ref: "bvd-uuid-1",
  source_storage_ref: null,
  account_reference: null,
  invoice_number: "972201",
  period_start: null,
  period_end: null,
  due_date: null,
  finalized_at: new Date().toISOString(),
  batch_status: "FINALIZED",
  transaction_count: 1,
  control_count: 0,
  currency_totals: [],
  currency_financial_summaries: [
    { currency: "CN", total_amount: "1", discount_amount: "0.00" },
  ],
  provider_control_totals: [],
  cad_transaction_total: "1",
  usd_transaction_total: null,
  usd_provider_control: null,
  purchase_card_count: 1,
  purchase_card_numbers: [],
  total_amount: "1",
  currency: "CN",
  read_only: true,
  review_status: "SOURCE_REVIEWED",
};

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
  currency_financial_summaries: [
    { currency: "CAD", total_amount: "1263.85", discount_amount: "0.00" },
    { currency: "USD", total_amount: "5197.67", discount_amount: "34.56" },
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
    processedOverlayMock.mockReset();
    apiMocks.getFuelProcessedBatch.mockImplementation(async (batchId: number) => ({
      batch_id: batchId,
      source_import_ref: batchId === 8 ? nationwideSummary.source_import_ref : bvdSummary.source_import_ref,
      canonical_transactions: [],
      total_amount: "10",
      currency: "USD",
    }));
    apiMocks.getFuelNationwideImportRows.mockResolvedValue([
      { id: 1, row_type: "TRANSACTION", import_id: nationwideSummary.source_import_ref },
    ]);
    apiMocks.getFuelNationwideSourceReconciliation.mockResolvedValue({});
    apiMocks.getFuelBvdImportRows.mockResolvedValue([bvdTxn]);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function renderSection(
    activity: FuelProcessedSummary[],
    onOpenProcessed?: (batchId: number, provider: string, ref: string | null) => void,
  ) {
    const activityItems = buildFuelRecentActivityDisplay(activity, 50);
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <FuelRecentActivitySection
          activityItems={activityItems}
          loading={false}
          onOpenProcessed={onOpenProcessed}
        />,
      );
      await new Promise((r) => setTimeout(r, 0));
    });
  }

  async function expandBatch(batchId: number) {
    const expandBtn = container.querySelector(
      `[data-testid="fuel-activity-invoice-${batchId}"] button`,
    ) as HTMLButtonElement;
    await act(async () => {
      expandBtn.click();
      await new Promise((r) => setTimeout(r, 80));
    });
  }

  it("shows tight per-currency sub-rows for mixed Nationwide invoice", async () => {
    await renderSection([nationwideSummary], vi.fn());
    expect(container.querySelector('[data-testid="fuel-activity-currency-line-CAD"]')?.textContent).toBe("CAD");
    const cadRow = container.querySelector('[data-currency-band="CAD"]');
    const usdRow = container.querySelector('[data-currency-band="USD"]');
    expect(cadRow?.className).not.toContain("continuation");
    expect(usdRow?.className).toContain("continuation");
    expect(container.textContent).toContain("0.00");
    expect(container.textContent).toContain("34.56");
    expect(container.querySelector('[data-testid="fuel-activity-invoice-total-line-CAD"]')?.textContent).toBe(
      "1263.85 CAD",
    );
    expect(container.querySelector('[data-testid="fuel-activity-invoice-total-line-USD"]')?.textContent).toBe(
      "5197.67 USD",
    );
    expect(container.querySelectorAll('[data-testid="fuel-activity-invoice-8"]').length).toBe(1);
  });

  it("expands Nationwide into TruckERP workspace without inline source evidence", async () => {
    await renderSection([nationwideSummary], vi.fn());
    await expandBatch(8);
    expect(container.querySelector(`[data-testid="fuel-processed-shell-8"]`)).toBeTruthy();
    expect(container.textContent).toContain("Nationwide 20250522B-06142026");
    expect(container.textContent).not.toMatch(/Source evidence/i);
    expect(container.querySelector('[data-testid="fuel-processed-evidence-8"]')).toBeNull();
    expect(container.querySelector('[data-testid="truckerp-processed-fuel-workspace"]')).toBeTruthy();
    expect(apiMocks.getFuelBvdImportRows).not.toHaveBeenCalled();
  });

  it("expands BVD into TruckERP workspace without inline BVD evidence panel", async () => {
    await renderSection([bvdSummary], vi.fn());
    await expandBatch(42);
    expect(container.querySelector('[data-testid="truckerp-processed-fuel-workspace"]')).toBeTruthy();
    expect(container.textContent).not.toMatch(/Source evidence/i);
    expect(apiMocks.getFuelBvdImportRows).toHaveBeenCalledWith("bvd-uuid-1");
  });

  it("Open source from expanded workspace passes batch lineage; row stays expanded", async () => {
    const onOpenProcessed = vi.fn();
    await renderSection([nationwideSummary], onOpenProcessed);
    await expandBatch(8);
    const openBtn = container.querySelector('[data-testid="fuel-open-source-8"]') as HTMLButtonElement;
    await act(async () => {
      openBtn.click();
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(onOpenProcessed).toHaveBeenCalledWith(8, "NATIONWIDE", nationwideSummary.source_import_ref);
    expect(container.querySelector('[data-testid="fuel-activity-detail-8"]')).toBeTruthy();
  });

  it("MANUAL_ENTRY with receipt shows Open source; DIRECT manual hides it", async () => {
    const receiptManual: FuelProcessedSummary = {
      ...bvdSummary,
      batch_id: 12,
      provider_code: "MANUAL_ENTRY",
      source_import_ref: "stage-uuid",
      source_storage_ref: "storage/manual/receipt.jpg",
      invoice_number: "41868",
      currency_financial_summaries: [
        { currency: "USD", total_amount: "1050.02", discount_amount: "0.00" },
      ],
    };
    const directManual: FuelProcessedSummary = {
      ...receiptManual,
      batch_id: 13,
      source_storage_ref: null,
    };
    apiMocks.getFuelProcessedBatch.mockImplementation(async (batchId: number) => ({
      batch_id: batchId,
      source_import_ref: "stage-uuid",
      canonical_transactions: [{ id: 1, batch_id: batchId, currency: "USD", total_amount: "1050.02" }],
      operational_transactions: [
        {
          id: 1,
          batch_id: batchId,
          source_row_order: 1,
          source_row_id: "s",
          source_vendor: "MANUAL_ENTRY",
          transaction_datetime_source: "2026-09-12",
          transaction_timezone_source: "DATE_ONLY",
          merchant_site: "Love's",
          site_number: "790",
          provider_raw: { entry_method: "RECEIPT" },
          currency: "USD",
        },
      ],
      currency_financial_summaries: receiptManual.currency_financial_summaries,
      total_amount: "1050.02",
      currency: "USD",
    }));
    await renderSection([receiptManual, directManual], vi.fn());
    expect(container.querySelectorAll('[data-testid="fuel-activity-invoice-12"]').length).toBe(0);
    expect(
      container.querySelector(
        `[data-testid="fuel-activity-invoice-${MANUAL_ENTRY_ACTIVITY_GROUP_BATCH_ID}"]`,
      ),
    ).toBeTruthy();
    await expandBatch(MANUAL_ENTRY_ACTIVITY_GROUP_BATCH_ID);
    expect(container.querySelector('[data-testid="fuel-activity-detail-manual-entry-group"]')).toBeTruthy();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 120));
    });
    expect(container.querySelector('[data-testid="manual-entry-collection-workspace"]')).toBeTruthy();
    expect(container.querySelectorAll('[data-testid="truckerp-processed-fuel-workspace"]').length).toBe(1);
    expect(container.querySelectorAll('[data-testid^="fuel-processed-shell-"]').length).toBe(0);
  });

  it("Nationwide Open source overlay mounts via record overlay registry", async () => {
    const Overlay = getProcessedFuelRecordOverlay("NATIONWIDE");
    expect(Overlay).toBeTruthy();
    const overlayHost = document.createElement("div");
    document.body.appendChild(overlayHost);
    const overlayRoot = createRoot(overlayHost);
    await act(async () => {
      overlayRoot.render(
        <Overlay
          sourceImportRef={nationwideSummary.source_import_ref!}
          variant="overlay"
          onClose={() => undefined}
        />,
      );
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(processedOverlayMock).toHaveBeenCalledWith(
      expect.objectContaining({ sourceImportRef: nationwideSummary.source_import_ref }),
    );
    act(() => overlayRoot.unmount());
    overlayHost.remove();
  });
});
