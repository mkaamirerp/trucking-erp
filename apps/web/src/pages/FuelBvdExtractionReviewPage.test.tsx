import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FuelBvdRow } from "../api";

const apiMocks = vi.hoisted(() => ({
  getFuelBvdImportRows: vi.fn(),
  getFuelBvdSourceReconciliation: vi.fn(),
}));

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getFuelBvdImportRows: apiMocks.getFuelBvdImportRows,
    getFuelBvdSourceReconciliation: apiMocks.getFuelBvdSourceReconciliation,
  };
});

vi.mock("./fuelBvdReview/FuelBvdProcessingWorkspace", () => ({
  default: () => <div data-testid="fuel-processing-workspace">workspace</div>,
}));

import FuelBvdExtractionReviewPage from "./FuelBvdExtractionReviewPage";

function headerRow(status: string): FuelBvdRow {
  return {
    id: 1,
    import_id: "import-locked",
    row_type: "HEADER",
    review_status: status,
    invoice_number: "972201",
  } as FuelBvdRow;
}

describe("FuelBvdExtractionReviewPage (route compatibility)", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    apiMocks.getFuelBvdImportRows.mockReset();
    apiMocks.getFuelBvdSourceReconciliation.mockResolvedValue({ passed: true, checks: [] });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("renders workspace for IN_REVIEW import", async () => {
    apiMocks.getFuelBvdImportRows.mockResolvedValue([headerRow("IN_REVIEW")]);
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/fuel/bvd/import-972201/review"]}>
          <Routes>
            <Route path="/fuel/bvd/:importId/review" element={<FuelBvdExtractionReviewPage />} />
          </Routes>
        </MemoryRouter>,
      );
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="fuel-processing-workspace"]')).toBeTruthy();
  });

  it("redirects SOURCE_REVIEWED review URL to detail", async () => {
    apiMocks.getFuelBvdImportRows.mockResolvedValue([headerRow("SOURCE_REVIEWED")]);
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/fuel/bvd/import-locked/review"]}>
          <Routes>
            <Route path="/fuel/bvd/:importId/review" element={<FuelBvdExtractionReviewPage />} />
            <Route path="/fuel/bvd/:importId/detail" element={<div data-testid="fuel-bvd-detail-page">detail</div>} />
          </Routes>
        </MemoryRouter>,
      );
      await Promise.resolve();
    });
    expect(container.querySelector('[data-testid="fuel-bvd-detail-page"]')).toBeTruthy();
  });
});
