import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  getFuelNationwideImportRows: vi.fn(),
  getFuelNationwideSourceReconciliation: vi.fn(),
  fuelNationwideDocumentUrl: vi.fn(),
}));

vi.mock("../../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api")>();
  return {
    ...actual,
    getFuelNationwideImportRows: apiMocks.getFuelNationwideImportRows,
    getFuelNationwideSourceReconciliation: apiMocks.getFuelNationwideSourceReconciliation,
    fuelNationwideDocumentUrl: apiMocks.fuelNationwideDocumentUrl,
  };
});

vi.mock("../fuelBvdReview/loadBvdPdfDocument", () => ({
  loadBvdPdfDocument: vi.fn().mockResolvedValue({}),
}));

import NationwideProcessedEvidencePanel from "./NationwideProcessedEvidencePanel";
import { loadBvdPdfDocument } from "../fuelBvdReview/loadBvdPdfDocument";

const NATIVE_IMPORT_ID = "eab57e99-c4bf-40e3-ba2e-21141729a8d8";

describe("NationwideProcessedEvidencePanel", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    apiMocks.getFuelNationwideImportRows.mockResolvedValue([
      { row_type: "HEADER", invoice_number: "INV-1" },
      { row_type: "TRANSACTION", import_id: NATIVE_IMPORT_ID },
    ]);
    apiMocks.getFuelNationwideSourceReconciliation.mockResolvedValue(null);
    apiMocks.fuelNationwideDocumentUrl.mockImplementation(
      (importId: string) => `/api/v1/fuel/nationwide/imports/${importId}/document`,
    );
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.clearAllMocks();
  });

  async function renderPanel() {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <NationwideProcessedEvidencePanel
          batchId={8}
          sourceImportRef={NATIVE_IMPORT_ID}
          invoiceNumber="INV-1"
        />,
      );
      await new Promise((r) => setTimeout(r, 0));
    });
  }

  it("loads native rows with sourceImportRef and never uses undefined in document URL", async () => {
    await renderPanel();
    expect(apiMocks.getFuelNationwideImportRows).toHaveBeenCalledWith(NATIVE_IMPORT_ID);
    const pdfBtn = container.querySelector(".bvd-statement__pdf-btn") as HTMLButtonElement;
    await act(async () => {
      pdfBtn.click();
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(apiMocks.fuelNationwideDocumentUrl).toHaveBeenCalledWith(NATIVE_IMPORT_ID);
    const url = apiMocks.fuelNationwideDocumentUrl.mock.results[0]?.value as string;
    expect(url).not.toContain("undefined");
    expect(url).toContain(NATIVE_IMPORT_ID);
    expect(loadBvdPdfDocument).toHaveBeenCalledWith(url);
  });
});
