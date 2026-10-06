import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  listTollPdfReviews: vi.fn(),
  getTollPdfReview: vi.fn(),
  uploadTollPdfFile: vi.fn(),
}));

vi.mock("../api", () => ({
  listTollPdfReviews: apiMocks.listTollPdfReviews,
  getTollPdfReview: apiMocks.getTollPdfReview,
  uploadTollPdfFile: apiMocks.uploadTollPdfFile,
}));

import TollsPdfReviewsPage from "./TollsPdfReviewsPage";

const listItem = {
  batch_id: 9,
  source_type: "FILE",
  file_format: "PDF",
  profile_code: "EZPASS_WVPA_MONTHLY_STATEMENT_PDF",
  filename: "wvpa.pdf",
  source_hash: "abc123",
  status: "PARSED",
  review_status: "NEEDS_REVIEW",
  imported_at: "2026-10-05T12:00:00+00:00",
  statement_date: "2023-04-05",
  account_number: "000000001",
  period_start: "2023-03-01",
  period_end: "2023-03-31",
  source_total_trip_count: 74,
  source_total_trip_charge: "854.47",
  parsed_trip_count: 74,
  parsed_total_trip_charge: "854.47",
  trip_count_matches: true,
  trip_total_matches: true,
  reconciliation_ok: true,
};

let root: Root | null = null;
let host: HTMLDivElement | null = null;

async function renderPage() {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(
      <MemoryRouter>
        <TollsPdfReviewsPage />
      </MemoryRouter>,
    );
  });
}

describe("TollsPdfReviewsPage", () => {
  beforeEach(() => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    apiMocks.listTollPdfReviews.mockReset();
    apiMocks.getTollPdfReview.mockReset();
    apiMocks.uploadTollPdfFile.mockReset();
    apiMocks.listTollPdfReviews.mockResolvedValue([listItem]);
    apiMocks.getTollPdfReview.mockResolvedValue({
      ...listItem,
      source_page_count: 7,
      total_row_count: 74,
      row_offset: 0,
      row_limit: 100,
      rows: [
        {
          source_row_order: 1,
          source_page_number: 1,
          post_date: "2023-03-01",
          entry_date: "2023-02-13",
          entry_time: "14:22",
          exit_date: "2023-02-13",
          exit_time: "14:45",
          agency_raw: "ILTOLL",
          entry_location: "I-90-WEST",
          entry_lane: "12",
          exit_location: "I-94-EAST",
          exit_lane: "08",
          transponder_number: "02400000001",
          plate_number: null,
          trip_charge: "10.00",
          trip_charge_raw: "(10.00)",
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

  it("presents PDF reviews without canonical Date/Unit history", async () => {
    await renderPage();
    expect(host?.textContent).toContain("PDF Reviews");
    expect(host?.textContent).toContain("CSV File Imports");
    expect(host?.textContent).toContain("Manual Entry");
    expect(host?.textContent).toContain("not created from this screen");
    expect(host?.textContent).toContain("NEEDS_REVIEW");
    expect(host?.textContent).toContain("74");
    expect(host?.textContent).toContain("854.47");
    expect(host?.textContent).not.toContain("Tolls imported successfully");
    const headers = Array.from(host!.querySelectorAll("thead th")).map((th) => (th.textContent || "").trim());
    expect(headers).not.toContain("Unit");
    expect(headers).not.toContain("Date/Time");
  });

  it("expands parsed review rows with agency and unmapped charge", async () => {
    await renderPage();
    const expand = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "#9");
    await act(async () => {
      expand!.click();
    });
    expect(apiMocks.getTollPdfReview).toHaveBeenCalledWith(9, { rowOffset: 0, rowLimit: 100 });
    expect(host?.textContent).toContain("ILTOLL");
    expect(host?.textContent).toContain("2023-03-01");
    expect(host?.textContent).toContain("2023-02-13");
    expect(host?.textContent).toContain("02400000001");
    expect(host?.textContent).toContain("10.00");
    expect(host?.textContent).toContain("not canonical Date/Unit/Amount history");
  });

  it("clears the PDF file input after a successful upload", async () => {
    apiMocks.listTollPdfReviews.mockReset();
    apiMocks.listTollPdfReviews.mockResolvedValueOnce([]).mockResolvedValueOnce([listItem]);
    apiMocks.uploadTollPdfFile.mockResolvedValue({
      ...listItem,
      source_hash: "abc123",
      duplicate_match_count: 0,
      duplicate_batch_ids: [],
    });
    await renderPage();
    const fileInput = host!.querySelector('input[type="file"]') as HTMLInputElement;
    const pdf = new File(["%PDF-1.4"], "wvpa.pdf", { type: "application/pdf" });
    await act(async () => {
      Object.defineProperty(fileInput, "files", { configurable: true, value: [pdf] });
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const upload = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "Upload PDF");
    await act(async () => {
      upload!.click();
    });
    expect(apiMocks.uploadTollPdfFile).toHaveBeenCalled();
    expect(apiMocks.uploadTollPdfFile).toHaveBeenCalledWith(
      expect.any(File),
      "EZPASS_WVPA_MONTHLY_STATEMENT_PDF",
    );
    expect(host?.textContent).toContain("E-ZPass/WVPA PDF stored for review.");
    expect(host?.textContent).not.toContain("Tolls imported successfully");
    expect((host!.querySelector('input[type="file"]') as HTMLInputElement).value).toBe("");
  });
});
