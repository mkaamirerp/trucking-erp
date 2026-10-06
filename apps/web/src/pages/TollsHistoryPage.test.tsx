import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  listTollFileBatches: vi.fn(),
  getTollFileBatch: vi.fn(),
  uploadTollCsvFile: vi.fn(),
}));

vi.mock("../api", () => ({
  listTollFileBatches: apiMocks.listTollFileBatches,
  getTollFileBatch: apiMocks.getTollFileBatch,
  uploadTollCsvFile: apiMocks.uploadTollCsvFile,
}));

import TollsHistoryPage from "./TollsHistoryPage";

const listItem = {
  batch_id: 7,
  source_type: "FILE",
  file_format: "CSV",
  filename: "portal.csv",
  source_hash: "abc123def4567890",
  status: "PARSED",
  row_count: 1,
  imported_at: "2026-10-04T12:00:00+00:00",
  csv_column_keys: ["Posted Date", "Agency", "Amount", "Plate"],
  csv_raw_header_names: ["Posted Date", "Agency", "Amount", "Plate"],
};

const uploadResult = {
  batch_id: 7,
  source_type: "FILE",
  file_format: "CSV",
  filename: "portal.csv",
  source_hash: "abc123def4567890",
  row_count: 1,
  headers: ["Posted Date", "Agency", "Amount", "Plate"],
  csv_column_keys: ["Posted Date", "Agency", "Amount", "Plate"],
  csv_raw_header_names: ["Posted Date", "Agency", "Amount", "Plate"],
  duplicate_match_count: 1,
  duplicate_batch_ids: [3],
  status: "PARSED",
  preview_rows: [],
};

let root: Root | null = null;
let host: HTMLDivElement | null = null;

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

async function renderPage() {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(
      <MemoryRouter>
        <TollsHistoryPage />
      </MemoryRouter>,
    );
  });
}

function tableHeaders(): string[] {
  return Array.from(host!.querySelectorAll("thead th")).map((th) => (th.textContent || "").trim());
}

describe("TollsHistoryPage", () => {
  beforeEach(() => {
    apiMocks.listTollFileBatches.mockReset();
    apiMocks.getTollFileBatch.mockReset();
    apiMocks.uploadTollCsvFile.mockReset();
    apiMocks.listTollFileBatches.mockResolvedValue([listItem]);
    apiMocks.getTollFileBatch.mockResolvedValue({
      ...listItem,
      headers: ["Posted Date", "Agency", "Amount", "Plate"],
      total_row_count: 1,
      row_offset: 0,
      row_limit: 100,
      rows: [
        {
          source_row_order: 1,
          source_line_number: 2,
          cells: {
            "Posted Date": "2026-03-01 10:05",
            Agency: "Niagara",
            Amount: "$5.25",
            Plate: "ABC123",
          },
          values: ["2026-03-01 10:05", "Niagara", "$5.25", "ABC123"],
        },
      ],
    });
  });

  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
  });

  it("presents File Imports, not canonical toll transaction history", async () => {
    await renderPage();
    expect(host?.textContent).toContain("File Imports");
    expect(host?.textContent).toContain("CSV File Imports");
    expect(host?.textContent).toContain("PDF Reviews");
    expect(host?.textContent).toContain("Manual Entry");
    expect(host?.textContent).toContain("CSV import history");
    expect(host?.textContent).toContain("not canonical toll transaction history");
    expect(host?.textContent).toContain("PARSED");
    expect(host?.textContent).toContain("file received + generic CSV parsed");
    expect(host?.textContent).toContain("not canonical processed");
    expect(host?.textContent).not.toContain("Toll History");
    expect(host?.textContent).not.toContain("Tolls imported successfully");
    const importHeaders = tableHeaders();
    expect(importHeaders).toEqual(["Batch", "Filename", "Format", "Source rows", "Status", "Imported", "Hash"]);
    expect(importHeaders).not.toContain("Date/Time");
    expect(importHeaders).not.toContain("Unit");
    expect(importHeaders).not.toContain("Toll Agency");
    expect(importHeaders).not.toContain("Type");
    expect(importHeaders).not.toContain("Read By");
    expect(importHeaders).not.toContain("Identifier");
  });

  it("expands raw source rows without fabricating normalized Date/Unit columns", async () => {
    await renderPage();
    const expand = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "#7");
    expect(expand).toBeTruthy();
    await act(async () => {
      expand!.click();
    });
    expect(apiMocks.getTollFileBatch).toHaveBeenCalledWith(7, { rowOffset: 0, rowLimit: 100 });
    expect(host?.textContent).toContain("Raw source rows");
    expect(host?.textContent).toContain("Unmapped source data");
    expect(host?.textContent).toContain("Posted Date");
    expect(host?.textContent).toContain("Niagara");
    expect(host?.textContent).toContain("$5.25");
    const rawHeaders = tableHeaders();
    expect(rawHeaders).toContain("Posted Date");
    expect(rawHeaders).toContain("Agency");
    expect(rawHeaders).not.toContain("Date/Time");
    expect(rawHeaders).not.toContain("Unit");
    expect(rawHeaders).not.toContain("Toll Agency");
    expect(rawHeaders).not.toContain("Read By");
    expect(rawHeaders).not.toContain("Identifier");
  });

  it("searches by filename/hash", async () => {
    await renderPage();
    const input = host!.querySelector("input[placeholder='tolls.csv or sha256…']") as HTMLInputElement;
    await act(async () => {
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
      setValue?.call(input, "portal");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const search = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "Search");
    await act(async () => {
      search!.click();
    });
    expect(apiMocks.listTollFileBatches).toHaveBeenLastCalledWith("portal");
  });

  it("upload refreshes import history and reports duplicates without claiming canonical tolls", async () => {
    apiMocks.listTollFileBatches.mockReset();
    apiMocks.listTollFileBatches.mockResolvedValueOnce([]).mockResolvedValueOnce([listItem]);
    apiMocks.uploadTollCsvFile.mockResolvedValue(uploadResult);
    await renderPage();
    expect(host?.textContent).toContain("No CSV imports");

    const fileInput = host!.querySelector('input[type="file"]') as HTMLInputElement;
    const csv = new File(["Posted Date,Agency\n2026-03-01,Niagara\n"], "portal.csv", { type: "text/csv" });
    await act(async () => {
      Object.defineProperty(fileInput, "files", { value: [csv] });
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const upload = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "Upload CSV");
    await act(async () => {
      upload!.click();
    });
    expect(apiMocks.uploadTollCsvFile).toHaveBeenCalled();
    expect(apiMocks.listTollFileBatches.mock.calls.length).toBeGreaterThan(1);
    expect(host?.textContent).toContain("CSV uploaded and stored for mapping.");
    expect(host?.textContent).toContain("earlier import");
    expect(host?.textContent).toContain("both copies are kept");
    expect(host?.textContent).not.toContain("Tolls imported successfully");
    expect(host?.textContent).toContain("portal.csv");
    expect(host?.textContent).toContain("File Imports");
    const clearedInput = host!.querySelector('input[type="file"]') as HTMLInputElement;
    expect(clearedInput.value).toBe("");
    const uploadAfter = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "Upload CSV");
    expect(uploadAfter?.hasAttribute("disabled")).toBe(true);
  });

  it("loads more raw rows instead of rendering an unbounded table up front", async () => {
    apiMocks.getTollFileBatch
      .mockResolvedValueOnce({
        ...listItem,
        row_count: 2,
        headers: ["Posted Date", "Agency", "Amount", "Plate"],
        csv_column_keys: ["Posted Date", "Agency", "Amount", "Plate"],
        total_row_count: 2,
        row_offset: 0,
        row_limit: 1,
        rows: [
          {
            source_row_order: 1,
            source_line_number: 2,
            cells: {
              "Posted Date": "2026-03-01 10:05",
              Agency: "Niagara",
              Amount: "$5.25",
              Plate: "ABC123",
            },
            values: ["2026-03-01 10:05", "Niagara", "$5.25", "ABC123"],
          },
        ],
      })
      .mockResolvedValueOnce({
        ...listItem,
        row_count: 2,
        headers: ["Posted Date", "Agency", "Amount", "Plate"],
        csv_column_keys: ["Posted Date", "Agency", "Amount", "Plate"],
        total_row_count: 2,
        row_offset: 1,
        row_limit: 100,
        rows: [
          {
            source_row_order: 2,
            source_line_number: 3,
            cells: {
              "Posted Date": "2026-03-01 10:42",
              Agency: "I-90",
              Amount: "12.00",
              Plate: "ABC123",
            },
            values: ["2026-03-01 10:42", "I-90", "12.00", "ABC123"],
          },
        ],
      });
    await renderPage();
    const expand = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "#7");
    await act(async () => {
      expand!.click();
    });
    expect(host?.textContent).toContain("Showing 1 of 2");
    expect(host?.textContent).toContain("Niagara");
    expect(host?.textContent).not.toContain("I-90");
    const loadMore = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "Load more");
    expect(loadMore).toBeTruthy();
    await act(async () => {
      loadMore!.click();
    });
    expect(apiMocks.getTollFileBatch).toHaveBeenLastCalledWith(7, { rowOffset: 1, rowLimit: 100 });
    expect(host?.textContent).toContain("I-90");
    expect(host?.textContent).toContain("Showing 2 of 2");
  });
});
