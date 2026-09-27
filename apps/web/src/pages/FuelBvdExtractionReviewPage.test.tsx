import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FuelBvdRow } from "../api";

const apiMocks = vi.hoisted(() => ({
  getFuelBvdImportRows: vi.fn(),
  saveFuelBvdReview: vi.fn(),
  getFuelBvdImportSummary: vi.fn(),
  processFuelBvdImport: vi.fn(),
}));

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getFuelBvdImportRows: apiMocks.getFuelBvdImportRows,
    saveFuelBvdReview: apiMocks.saveFuelBvdReview,
    getFuelBvdImportSummary: apiMocks.getFuelBvdImportSummary,
    processFuelBvdImport: apiMocks.processFuelBvdImport,
  };
});

vi.mock("./fuelBvdReview/BvdParsedStatementView", () => ({
  default: () => <div data-testid="bvd-parsed-view">statement</div>,
}));

vi.mock("./fuelBvdReview/BvdPdfPopupModal", () => ({
  default: () => null,
}));

vi.mock("./fuelBvdReview/loadBvdPdfDocument", () => ({
  loadBvdPdfDocument: vi.fn(),
}));

const assignMock = vi.hoisted(() => vi.fn());

vi.stubGlobal("location", { ...window.location, assign: assignMock });

import FuelBvdExtractionReviewPage from "./FuelBvdExtractionReviewPage";
import { buildBvdUploadCompletedPath } from "./fuelBvdReview/bvdUploadCompletion";

function headerRow(status: string): FuelBvdRow {
  return {
    id: 1,
    import_id: "import-972201",
    row_type: "HEADER",
    review_status: status,
    invoice_number: "972201",
  } as FuelBvdRow;
}

describe("FuelBvdExtractionReviewPage actions", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    apiMocks.getFuelBvdImportRows.mockReset();
    apiMocks.saveFuelBvdReview.mockReset();
    apiMocks.getFuelBvdImportSummary.mockReset();
    apiMocks.processFuelBvdImport.mockReset();
    assignMock.mockReset();
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  function renderPage() {
    act(() => {
      root.render(
        <MemoryRouter initialEntries={["/fuel/bvd/import-972201/review"]}>
          <Routes>
            <Route path="/fuel/bvd/:importId/review" element={<FuelBvdExtractionReviewPage />} />
          </Routes>
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

  it("Save review calls API with zero corrections and shows success", async () => {
    apiMocks.getFuelBvdImportRows
      .mockResolvedValueOnce([headerRow("PENDING")])
      .mockResolvedValueOnce([headerRow("IN_REVIEW")]);
    apiMocks.saveFuelBvdReview.mockResolvedValue({ saved_corrections: 0 });

    renderPage();
    await act(async () => {
      await Promise.resolve();
    });

    clickButton("Save review");
    await act(async () => {
      await Promise.resolve();
    });

    expect(apiMocks.saveFuelBvdReview).toHaveBeenCalledWith("import-972201", []);
    expect(container.textContent).toContain("Review saved");
  });

  it("Process calls process API on confirm", async () => {
    apiMocks.getFuelBvdImportRows
      .mockResolvedValueOnce([headerRow("IN_REVIEW")])
      .mockResolvedValueOnce([headerRow("SOURCE_REVIEWED")]);
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
      row_count: 24,
      transaction_count: 2,
      correction_count: 0,
      review_status: "SOURCE_REVIEWED",
    });
    renderPage();
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

    expect(apiMocks.processFuelBvdImport).toHaveBeenCalledWith("import-972201");
    expect(assignMock).toHaveBeenCalledWith(buildBvdUploadCompletedPath("972201"));
  });

  it("shows save review API errors", async () => {
    apiMocks.getFuelBvdImportRows.mockResolvedValue([headerRow("PENDING")]);
    apiMocks.saveFuelBvdReview.mockRejectedValue(new Error("Network error"));

    renderPage();
    await act(async () => {
      await Promise.resolve();
    });

    clickButton("Save review");
    await act(async () => {
      await Promise.resolve();
    });

    expect(container.textContent).toContain("Network error");
  });

  it("shows reconciliation failure from process API", async () => {
    apiMocks.getFuelBvdImportRows.mockResolvedValue([headerRow("IN_REVIEW")]);
    apiMocks.getFuelBvdImportSummary.mockResolvedValue({
      import_id: "import-972201",
      invoice_number: "972201",
      row_count: 24,
      transaction_count: 2,
      correction_count: 0,
      review_status: "IN_REVIEW",
    });
    const err = new Error(
      JSON.stringify({
        detail: {
          code: "BVD_SOURCE_RECONCILIATION_FAILED",
          message: "Required BVD source validations did not pass",
          reconciliation: {
            checks: [{ code: "CORE_TXN_TOTAL_VS_PROVIDER_GRAND", status: "FAIL", difference: "0.01" }],
          },
        },
      }),
    );
    (err as Error & { status?: number }).status = 400;
    apiMocks.processFuelBvdImport.mockRejectedValue(err);

    renderPage();
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

    expect(container.textContent).toContain("Source reconciliation failed");
    expect(container.textContent).toContain("CORE_TXN_TOTAL_VS_PROVIDER_GRAND");
  });
});
