import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  listFuelProviders: vi.fn(),
  getFuelDashboardStats: vi.fn(),
  listFuelProcessed: vi.fn(),
  uploadFuelBvdPdf: vi.fn(),
  discardFuelBvdStage: vi.fn(),
}));

vi.mock("../api", () => ({
  listFuelProviders: apiMocks.listFuelProviders,
  getFuelDashboardStats: apiMocks.getFuelDashboardStats,
  listFuelProcessed: apiMocks.listFuelProcessed,
  uploadFuelBvdPdf: apiMocks.uploadFuelBvdPdf,
  discardFuelBvdStage: apiMocks.discardFuelBvdStage,
  getFuelBvdUploadErrorDisplay: () => ({ title: "Error", message: "fail" }),
  getFuelNationwideUploadErrorDisplay: () => ({ title: "Error", message: "fail" }),
  uploadFuelNationwidePdf: vi.fn(),
  discardFuelNationwideStage: vi.fn(),
}));

const processingMock = vi.hoisted(() => vi.fn());
const processedMock = vi.hoisted(() => vi.fn());

vi.mock("./fuelNationwideReview/FuelNationwideProcessingWorkspace", () => ({
  default: () => null,
}));

vi.mock("./fuelBvdReview/FuelBvdProcessingWorkspace", () => ({
  default: (props: { importId: string; onProcessed?: (p: { importId: string; invoiceNumber?: string }) => void }) => {
    processingMock(props);
    return (
      <div data-testid="fuel-processing-overlay-mock">
        <button type="button" onClick={() => props.onProcessed?.({ importId: props.importId, invoiceNumber: "972201" })}>
          Mock process done
        </button>
      </div>
    );
  },
}));

vi.mock("./fuel/processedFuelProviderRenderers", () => ({
  getProcessedFuelEvidenceRenderer: () => null,
  getProcessedFuelRecordOverlay: () =>
    function MockProcessedOverlay(props: { sourceImportRef: string; onClose?: () => void }) {
      processedMock(props);
      return (
        <div data-testid="fuel-processed-overlay-mock">
          <button type="button" onClick={() => props.onClose?.()}>Mock close processed</button>
        </div>
      );
    },
}));

import FuelMainPage from "./FuelMainPage";

const processedRow = {
  batch_id: 42,
  provider_code: "BVD",
  source_import_ref: "done-1",
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
  currency_totals: [{ currency: "CN", amount: "1" }],
  provider_control_totals: [],
  cad_transaction_total: "1",
  usd_transaction_total: null,
  usd_provider_control: null,
  purchase_card_count: 1,
  purchase_card_numbers: ["1234"],
  total_amount: "1",
  currency: "CN",
  read_only: true,
  review_status: "SOURCE_REVIEWED",
};

describe("FuelMainPage", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    apiMocks.listFuelProviders.mockResolvedValue([
      { provider_code: "BVD", display_name: "BVD", connection_methods: [], supported_connection_methods: [] },
      { provider_code: "WEX", display_name: "WEX", connection_methods: [], supported_connection_methods: [] },
    ]);
    apiMocks.getFuelDashboardStats.mockResolvedValue({
      needs_review_count: 3,
      processed_last_7_days_count: 7,
    });
    apiMocks.listFuelProcessed.mockResolvedValue([]);
    apiMocks.uploadFuelBvdPdf.mockReset();
    apiMocks.discardFuelBvdStage.mockResolvedValue({ discarded: true });
    processingMock.mockReset();
    processedMock.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function renderFuel() {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/fuel"]}>
          <Routes>
            <Route path="/fuel" element={<FuelMainPage />} />
          </Routes>
        </MemoryRouter>,
      );
      await new Promise((r) => setTimeout(r, 0));
    });
  }

  it("renders provider combobox without pills, workflow steps, or design notes", async () => {
    await renderFuel();
    expect(container.querySelector('[data-testid="fuel-provider-combobox"]')).toBeTruthy();
    expect(container.textContent).not.toContain("1.Upload");
    expect(container.querySelector('[data-design-notes="true"]')).toBeNull();
    expect(container.textContent).toContain("Needs review");
    expect(container.textContent).toContain("Processed last 7 days");
    expect(apiMocks.getFuelDashboardStats).toHaveBeenCalled();
    expect(apiMocks.listFuelProcessed).toHaveBeenCalled();
  });

  it("upload opens processing overlay on fuel home", async () => {
    apiMocks.uploadFuelBvdPdf.mockResolvedValue({ import_id: "new-import-1", row_count: 1, parse_status: "SUCCESS" });
    await renderFuel();
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["%PDF"], "test.pdf", { type: "application/pdf" });
    await act(async () => {
      Object.defineProperty(fileInput, "files", { value: [file] });
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(apiMocks.uploadFuelBvdPdf).toHaveBeenCalled();
    expect(container.querySelector('[data-testid="fuel-processing-overlay-mock"]')).toBeTruthy();
  });

  it("process closes overlay and refetches processed Fuel list", async () => {
    apiMocks.uploadFuelBvdPdf.mockResolvedValue({ import_id: "new-import-2", row_count: 1, parse_status: "SUCCESS" });
    await renderFuel();
    const initialCalls = apiMocks.listFuelProcessed.mock.calls.length;
    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["%PDF"], "test.pdf", { type: "application/pdf" });
    await act(async () => {
      Object.defineProperty(fileInput, "files", { value: [file] });
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      await new Promise((r) => setTimeout(r, 0));
    });
    const doneBtn = container.querySelector('[data-testid="fuel-processing-overlay-mock"] button') as HTMLButtonElement;
    await act(async () => {
      doneBtn.click();
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(container.querySelector('[data-testid="fuel-processing-overlay-mock"]')).toBeNull();
    expect(apiMocks.listFuelProcessed.mock.calls.length).toBeGreaterThan(initialCalls);
  });

  it("Open source triggers processed overlay via batch lineage", async () => {
    apiMocks.listFuelProcessed.mockResolvedValue([processedRow]);
    await renderFuel();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    const openBtn = container.querySelector('[data-testid="fuel-activity-open-42"]') as HTMLButtonElement;
    await act(async () => {
      openBtn.click();
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(processedMock).toHaveBeenCalledWith(
      expect.objectContaining({ sourceImportRef: "done-1" }),
    );
    expect(container.querySelector('[data-testid="fuel-processed-overlay-mock"]')).toBeTruthy();
  });

  it("Close on processed source overlay returns to Fuel home", async () => {
    apiMocks.listFuelProcessed.mockResolvedValue([processedRow]);
    await renderFuel();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    const openBtn = container.querySelector('[data-testid="fuel-activity-open-42"]') as HTMLButtonElement;
    await act(async () => {
      openBtn.click();
      await new Promise((r) => setTimeout(r, 0));
    });
    const closeBtn = container.querySelector(
      '[data-testid="fuel-processed-overlay-mock"] button',
    ) as HTMLButtonElement;
    await act(async () => {
      closeBtn.click();
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(container.querySelector('[data-testid="fuel-processed-overlay-mock"]')).toBeNull();
    expect(container.querySelector('[data-testid="fuel-home"]')).toBeTruthy();
  });
});
