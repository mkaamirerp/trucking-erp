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
}));

vi.mock("../api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api")>();
  return {
    ...actual,
    getFuelBvdImportRows: apiMocks.getFuelBvdImportRows,
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
    apiMocks.getFuelBvdImportRows.mockResolvedValue(goldenRows());
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
      await new Promise((r) => setTimeout(r, 0));
    });
  }

  it("G: full stored detail still shows zero-value provider tax columns on transactions", async () => {
    await renderPage();
    expect(container.textContent).toContain("BVD full stored detail");
    expect(container.textContent).toContain("GST");
    expect(container.textContent).toContain("0.00");
  });

  it("H: original PDF remains accessible from full stored detail", async () => {
    await renderPage();
    const btn = container.querySelector("button.bvd-statement__pdf-btn");
    expect(btn?.textContent).toMatch(/View original PDF/i);
  });
});
