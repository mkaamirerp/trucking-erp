import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FuelBvdRow } from "../../api";

const apiMocks = vi.hoisted(() => ({
  getFuelBvdImportRows: vi.fn(),
  getFuelBvdSourceReconciliation: vi.fn(),
  saveFuelBvdReview: vi.fn(),
  getFuelBvdImportSummary: vi.fn(),
  processFuelBvdImport: vi.fn(),
}));

const defaultRecon = {
  passed: true,
  transaction_total: "0",
  all_unit_total: "0",
  provider_grand_total: "0",
  difference: "0.00",
  checks: [],
};

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    getFuelBvdImportRows: apiMocks.getFuelBvdImportRows,
    getFuelBvdSourceReconciliation: apiMocks.getFuelBvdSourceReconciliation,
    saveFuelBvdReview: apiMocks.saveFuelBvdReview,
    getFuelBvdImportSummary: apiMocks.getFuelBvdImportSummary,
    processFuelBvdImport: apiMocks.processFuelBvdImport,
  };
});

vi.mock("./BvdParsedStatementView", () => ({
  default: () => <div data-testid="bvd-parsed-view">statement</div>,
}));

vi.mock("./BvdReviewCorrectionsPanel", () => ({
  default: () => <div data-testid="bvd-review-corrections-panel">corrections</div>,
}));

vi.mock("./BvdPdfPopupModal", () => ({
  default: () => null,
}));

vi.mock("./loadBvdPdfDocument", () => ({
  loadBvdPdfDocument: vi.fn(),
}));

const navigateMock = vi.hoisted(() => vi.fn());

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

import FuelBvdProcessingWorkspace from "./FuelBvdProcessingWorkspace";
import { buildFuelProcessedReturnPath } from "./bvdUploadCompletion";

function headerRow(status: string): FuelBvdRow {
  return {
    id: 1,
    import_id: "import-972201",
    row_type: "HEADER",
    review_status: status,
    invoice_number: "972201",
  } as FuelBvdRow;
}

describe("FuelBvdProcessingWorkspace", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    apiMocks.getFuelBvdImportRows.mockReset();
    apiMocks.getFuelBvdSourceReconciliation.mockReset();
    apiMocks.getFuelBvdSourceReconciliation.mockResolvedValue(defaultRecon);
    apiMocks.saveFuelBvdReview.mockReset();
    apiMocks.getFuelBvdImportSummary.mockReset();
    apiMocks.processFuelBvdImport.mockReset();
    navigateMock.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function renderWorkspace(variant: "route" | "overlay" = "route", onProcessed = vi.fn()) {
    act(() => {
      root.render(
        <MemoryRouter>
          <FuelBvdProcessingWorkspace
            importId="import-972201"
            variant={variant}
            onProcessed={onProcessed}
            onClose={vi.fn()}
          />
        </MemoryRouter>,
      );
    });
  }

  function clickButton(label: string) {
    const btn = Array.from(container.querySelectorAll("button")).find((b) =>
      b.textContent?.includes(label),
    );
    expect(btn).toBeTruthy();
    act(() => {
      btn!.click();
    });
  }

  it("overlay variant renders full-screen shell", async () => {
    apiMocks.getFuelBvdImportRows.mockResolvedValue([headerRow("PENDING")]);
    renderWorkspace("overlay");
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="fuel-processing-overlay"]')).toBeTruthy();
  });

  it("Save review calls API", async () => {
    apiMocks.getFuelBvdImportRows
      .mockResolvedValueOnce([headerRow("PENDING")])
      .mockResolvedValueOnce([headerRow("IN_REVIEW")]);
    apiMocks.saveFuelBvdReview.mockResolvedValue({ saved_corrections: 0 });
    renderWorkspace();
    await act(async () => {
      await Promise.resolve();
    });
    clickButton("Save review");
    await act(async () => {
      await Promise.resolve();
    });
    expect(apiMocks.saveFuelBvdReview).toHaveBeenCalledWith("import-972201", []);
  });

  it("route variant navigates to fuel on process", async () => {
    apiMocks.getFuelBvdImportRows.mockResolvedValue([headerRow("IN_REVIEW")]);
    apiMocks.getFuelBvdImportSummary.mockResolvedValue({
      import_id: "import-972201",
      invoice_number: "972201",
      row_count: 24,
      transaction_count: 2,
      correction_count: 0,
      review_status: "IN_REVIEW",
    });
    apiMocks.processFuelBvdImport.mockResolvedValue({
      import_id: "import-972201",
      invoice_number: "972201",
      review_status: "SOURCE_REVIEWED",
    });
    renderWorkspace("route");
    await act(async () => {
      await Promise.resolve();
    });
    clickButton("Process");
    await act(async () => {
      await Promise.resolve();
    });
    clickButton("Confirm process");
    await act(async () => {
      await Promise.resolve();
    });
    expect(navigateMock).toHaveBeenCalledWith(buildFuelProcessedReturnPath("972201"), { replace: true });
  });

  it("overlay variant calls onProcessed instead of navigate", async () => {
    const onProcessed = vi.fn();
    apiMocks.getFuelBvdImportRows.mockResolvedValue([headerRow("IN_REVIEW")]);
    apiMocks.getFuelBvdImportSummary.mockResolvedValue({
      import_id: "import-972201",
      invoice_number: "972201",
      row_count: 1,
      transaction_count: 1,
      correction_count: 0,
      review_status: "IN_REVIEW",
    });
    apiMocks.processFuelBvdImport.mockResolvedValue({
      import_id: "import-972201",
      invoice_number: "972201",
      review_status: "SOURCE_REVIEWED",
    });
    renderWorkspace("overlay", onProcessed);
    await act(async () => {
      await Promise.resolve();
    });
    clickButton("Process");
    await act(async () => {
      await Promise.resolve();
    });
    clickButton("Confirm process");
    await act(async () => {
      await Promise.resolve();
    });
    expect(onProcessed).toHaveBeenCalledWith({ importId: "import-972201", invoiceNumber: "972201" });
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
