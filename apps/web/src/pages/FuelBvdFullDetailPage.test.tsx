import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { FuelBvdRow } from "../api";
import FuelBvdFullDetailPage from "./FuelBvdFullDetailPage";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../..");
const golden = JSON.parse(
  readFileSync(join(repoRoot, "tests/fixtures/fuel_bvd_972201_expected.json"), "utf-8"),
) as { rows: Record<string, unknown>[] };

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
    fuelBvdDocumentUrl: (id: string) => `/api/fuel/bvd/imports/${id}/document`,
  };
});

vi.mock("./fuelBvdReview/BvdPdfPopupModal", () => ({
  default: () => null,
}));

vi.mock("./fuelBvdReview/loadBvdPdfDocument", () => ({
  loadBvdPdfDocument: vi.fn(),
}));

function goldenRows(): FuelBvdRow[] {
  return golden.rows.map((r, i) => ({
    id: i + 1,
    import_id: "import-972201",
    review_status: "SOURCE_REVIEWED",
    ...r,
  })) as FuelBvdRow[];
}

describe("FuelBvdFullDetailPage", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    apiMocks.getFuelBvdImportRows.mockReset();
    apiMocks.getFuelBvdSourceReconciliation.mockReset();
    apiMocks.getFuelBvdImportRows.mockResolvedValue(goldenRows());
    apiMocks.getFuelBvdSourceReconciliation.mockResolvedValue({
      passed: true,
      transaction_total: "3421.01",
      checks: [],
    });
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  async function renderPage() {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/fuel/bvd/import-972201/detail"]}>
          <Routes>
            <Route path="/fuel/bvd/:importId/detail" element={<FuelBvdFullDetailPage />} />
          </Routes>
        </MemoryRouter>,
      );
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
  }

  it("G/H: full stored detail shows all provider transaction columns including zero taxes", async () => {
    await renderPage();
    expect(container.textContent).toContain("BVD full stored detail");
    const purchases = container.querySelector('[data-testid="bvd-purchases-full-table"]');
    expect(purchases).toBeTruthy();
    expect(container.querySelector(".bvd-txn-rows")).toBeNull();
    expect(purchases?.textContent).toContain("GST");
    expect(purchases?.textContent).toContain("0.00");
    expect(purchases?.textContent).toContain("Disc Rate");
  });

  it("H: original PDF remains accessible from full stored detail", async () => {
    await renderPage();
    const btn = container.querySelector("button.bvd-statement__pdf-btn");
    expect(btn?.textContent).toMatch(/View original PDF/i);
  });
});
