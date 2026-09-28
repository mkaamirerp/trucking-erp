import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  listFuelProviders: vi.fn(),
  listFuelReviewQueue: vi.fn(),
  listFuelBvdImports: vi.fn(),
  listFuelBvdCompletedHistory: vi.fn(),
  uploadFuelBvdPdf: vi.fn(),
  discardFuelBvdStage: vi.fn(),
}));

vi.mock("../api", () => ({
  listFuelProviders: apiMocks.listFuelProviders,
  listFuelReviewQueue: apiMocks.listFuelReviewQueue,
  listFuelBvdImports: apiMocks.listFuelBvdImports,
  listFuelBvdCompletedHistory: apiMocks.listFuelBvdCompletedHistory,
  uploadFuelBvdPdf: apiMocks.uploadFuelBvdPdf,
  discardFuelBvdStage: apiMocks.discardFuelBvdStage,
  getFuelBvdUploadErrorDisplay: () => ({ title: "Error", message: "fail" }),
}));

const processingMock = vi.hoisted(() => vi.fn());
const processedMock = vi.hoisted(() => vi.fn());

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

vi.mock("./fuelBvdReview/FuelBvdProcessedRecordView", () => ({
  default: (props: { importId: string; onClose?: () => void }) => {
    processedMock(props);
    return (
      <div data-testid="fuel-processed-overlay-mock">
        <button type="button" onClick={() => props.onClose?.()}>Mock close processed</button>
      </div>
    );
  },
}));

import FuelMainPage from "./FuelMainPage";

describe("FuelMainPage", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    apiMocks.listFuelProviders.mockResolvedValue([
      { provider_code: "BVD", display_name: "BVD", connection_methods: [], supported_connection_methods: [] },
      { provider_code: "WEX", display_name: "WEX", connection_methods: [], supported_connection_methods: [] },
    ]);
    apiMocks.listFuelReviewQueue.mockResolvedValue([]);
    apiMocks.listFuelBvdImports.mockResolvedValue([]);
    apiMocks.listFuelBvdCompletedHistory.mockResolvedValue([]);
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
    expect(container.textContent).not.toContain("In queue");
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
    expect(container.querySelector('[data-testid="fuel-home"]')).toBeTruthy();
  });

  it("process closes overlay and refetches history", async () => {
    apiMocks.uploadFuelBvdPdf.mockResolvedValue({ import_id: "new-import-2", row_count: 1, parse_status: "SUCCESS" });
    await renderFuel();
    const initialHistoryCalls = apiMocks.listFuelBvdCompletedHistory.mock.calls.length;
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
    expect(apiMocks.listFuelBvdCompletedHistory.mock.calls.length).toBeGreaterThan(initialHistoryCalls);
  });

  it("Open triggers processed overlay", async () => {
    apiMocks.listFuelBvdCompletedHistory.mockResolvedValue([
      {
        provider: "BVD",
        import_id: "done-1",
        invoice_number: "972201",
        review_status: "SOURCE_REVIEWED",
        read_only: true,
        unit_count: 1,
        unit_numbers: [],
        total_amount: "1",
        currency: "CN",
        categories: [],
        taxes: [],
        processed_at: new Date().toISOString(),
      },
    ]);
    await renderFuel();
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    const openBtn = container.querySelector('[data-testid="fuel-activity-open-done-1"]') as HTMLButtonElement;
    await act(async () => {
      openBtn.click();
    });
    expect(container.querySelector('[data-testid="fuel-processed-overlay-mock"]')).toBeTruthy();
    expect(processedMock).toHaveBeenCalled();
  });
});
