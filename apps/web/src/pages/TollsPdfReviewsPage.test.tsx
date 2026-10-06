import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  listTollPdfReviews: vi.fn(),
  listTollProviders: vi.fn(),
  getTollPdfReview: vi.fn(),
  uploadTollFile: vi.fn(),
  patchTollPdfReviewRow: vi.fn(),
  processTollPdfReview: vi.fn(),
}));

vi.mock("../api", () => ({
  listTollPdfReviews: apiMocks.listTollPdfReviews,
  listTollProviders: apiMocks.listTollProviders,
  getTollPdfReview: apiMocks.getTollPdfReview,
  uploadTollFile: apiMocks.uploadTollFile,
  patchTollPdfReviewRow: apiMocks.patchTollPdfReviewRow,
  processTollPdfReview: apiMocks.processTollPdfReview,
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
    apiMocks.listTollProviders.mockReset();
    apiMocks.getTollPdfReview.mockReset();
    apiMocks.uploadTollFile.mockReset();
    apiMocks.patchTollPdfReviewRow.mockReset();
    apiMocks.processTollPdfReview.mockReset();
    apiMocks.listTollProviders.mockResolvedValue([
      { provider_code: "EZPASS", provider_name: "E-ZPass", home_state: null, upload_choice: true },
      { provider_code: "PREPASS", provider_name: "PrePass", home_state: null, upload_choice: true },
      { provider_code: "TOLLTAG", provider_name: "TollTag", home_state: "TX", upload_choice: true },
      { provider_code: "EZ_TAG", provider_name: "EZ TAG", home_state: "TX", upload_choice: true },
      { provider_code: "TXTAG", provider_name: "TxTag", home_state: "TX", upload_choice: true },
      { provider_code: "PIKEPASS", provider_name: "PIKEPASS", home_state: "OK", upload_choice: true },
      { provider_code: "IPASS", provider_name: "I-PASS", home_state: "IL", upload_choice: true },
      { provider_code: "SUNPASS", provider_name: "SunPass", home_state: "FL", upload_choice: true },
      { provider_code: "EPASS", provider_name: "E-PASS", home_state: "FL", upload_choice: true },
      { provider_code: "PEACH_PASS", provider_name: "Peach Pass", home_state: "GA", upload_choice: true },
      { provider_code: "NC_QUICK_PASS", provider_name: "NC Quick Pass", home_state: "NC", upload_choice: true },
      { provider_code: "KTAG", provider_name: "K-TAG", home_state: "KS", upload_choice: true },
      { provider_code: "FASTRAK", provider_name: "FasTrak", home_state: "CA", upload_choice: true },
      { provider_code: "GOOD_TO_GO", provider_name: "Good To Go!", home_state: "WA", upload_choice: true },
      { provider_code: "EZPASS_NY", provider_name: "E-ZPass NY", home_state: "NY", upload_choice: true },
      { provider_code: "EZPASS_NJ", provider_name: "E-ZPass NJ", home_state: "NJ", upload_choice: true },
      { provider_code: "EZPASS_PA", provider_name: "E-ZPass PA", home_state: "PA", upload_choice: true },
    ]);
    apiMocks.listTollPdfReviews.mockResolvedValue([listItem]);
    apiMocks.getTollPdfReview.mockResolvedValue({
      ...listItem,
      source_page_count: 7,
      total_row_count: 74,
      row_offset: 0,
      row_limit: 100,
      effective_trip_count: 74,
      effective_total_trip_charge: "854.47",
      effective_reconciliation_ok: true,
      rows: [
        {
          row_id: 1,
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
    expect(host?.textContent).toContain("Upload");
    expect(host?.textContent).toContain("Manual Entry");
    expect(host?.textContent).toContain("E-ZPass");
    expect(host?.textContent).toContain("PrePass");
    expect(host?.textContent).toContain("TollTag");
    expect(host?.textContent).toContain("EZ TAG");
    expect(host?.textContent).toContain("TxTag");
    expect(host?.textContent).toContain("PIKEPASS");
    expect(host?.textContent).toContain("I-PASS");
    expect(host?.textContent).toContain("SunPass");
    expect(host?.textContent).toContain("E-PASS");
    expect(host?.textContent).toContain("Peach Pass");
    expect(host?.textContent).toContain("NC Quick Pass");
    expect(host?.textContent).toContain("K-TAG");
    expect(host?.textContent).toContain("FasTrak");
    expect(host?.textContent).toContain("Good To Go!");
    expect(host?.textContent).toContain("E-ZPass NY");
    expect(host?.textContent).toContain("E-ZPass NJ");
    expect(host?.textContent).toContain("E-ZPass PA");
    const optionValues = Array.from(host!.querySelectorAll("select option")).map(
      (opt) => (opt as HTMLOptionElement).value,
    );
    expect(optionValues).toContain("TOLLTAG");
    expect(optionValues).toContain("SUNPASS");
    expect(optionValues).not.toContain("WVPA");
    expect(host?.textContent).toContain("detects PDF, image, or CSV");
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
    expect(apiMocks.getTollPdfReview).toHaveBeenCalledWith(9, { rowOffset: 0, rowLimit: 500 });
    expect(host?.textContent).toContain("ILTOLL");
    expect(host?.textContent).toContain("2023-03-01");
    expect(host?.textContent).toContain("2023-02-13");
    expect(host?.textContent).toContain("02400000001");
    expect(host?.textContent).toContain("10.00");
    expect(host?.querySelector('[data-testid="toll-review-summary"]')?.textContent).toMatch(/Reconciliation OK/i);
    expect(host?.querySelector('[data-testid="toll-review-sort-agency"]')).toBeTruthy();
    const process = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "Process");
    expect(process).toBeTruthy();
    expect((process as HTMLButtonElement).disabled).toBe(false);
  });

  it("disables Process when effective reconciliation fails", async () => {
    apiMocks.getTollPdfReview.mockResolvedValue({
      ...listItem,
      reconciliation_ok: false,
      effective_reconciliation_ok: false,
      effective_trip_count: 74,
      effective_total_trip_charge: "1.00",
      source_page_count: 7,
      total_row_count: 74,
      row_offset: 0,
      row_limit: 100,
      rows: [],
    });
    await renderPage();
    const expand = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "#9");
    await act(async () => {
      expand!.click();
    });
    const process = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "Process");
    expect(process).toBeTruthy();
    expect((process as HTMLButtonElement).disabled).toBe(true);
  });

  it("clears the PDF file input after a successful upload", async () => {
    apiMocks.listTollPdfReviews.mockReset();
    apiMocks.listTollPdfReviews.mockResolvedValueOnce([]).mockResolvedValueOnce([listItem]);
    apiMocks.uploadTollFile.mockResolvedValue({
      ...listItem,
      source_hash: "abc123",
      duplicate_match_count: 0,
      duplicate_batch_ids: [],
    });
    await renderPage();
    const select = host!.querySelector("select") as HTMLSelectElement;
    await act(async () => {
      select.value = "EZPASS";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const fileInput = host!.querySelector('input[type="file"]') as HTMLInputElement;
    const pdf = new File(["%PDF-1.4"], "wvpa.pdf", { type: "application/pdf" });
    await act(async () => {
      Object.defineProperty(fileInput, "files", { configurable: true, value: [pdf] });
      fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const upload = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "Upload");
    await act(async () => {
      upload!.click();
    });
    expect(apiMocks.uploadTollFile).toHaveBeenCalled();
    expect(apiMocks.uploadTollFile).toHaveBeenCalledWith(expect.any(File), "EZPASS");
    expect(host?.textContent).toContain("E-ZPass file stored for review.");
    expect(host?.textContent).not.toContain("Tolls imported successfully");
    expect((host!.querySelector('input[type="file"]') as HTMLInputElement).value).toBe("");
  });

  it("sorts review rows when a column header is clicked", async () => {
    apiMocks.getTollPdfReview.mockResolvedValue({
      ...listItem,
      source_page_count: 7,
      total_row_count: 2,
      row_offset: 0,
      row_limit: 500,
      effective_trip_count: 2,
      effective_total_trip_charge: "17.65",
      effective_reconciliation_ok: true,
      rows: [
        {
          row_id: 1,
          source_row_order: 1,
          source_page_number: 2,
          post_date: "2023-03-01",
          entry_date: "2023-03-01",
          entry_time: "03:01:29 PM",
          agency_raw: "WVPA",
          entry_location: "83rd St.",
          entry_lane: "54",
          transponder_number: "02400454986",
          trip_charge: "14.65",
          trip_charge_raw: "(14.65)",
        },
        {
          row_id: 2,
          source_row_order: 2,
          source_page_number: 2,
          post_date: "2023-03-01",
          entry_date: "2023-03-01",
          entry_time: "03:53:06 PM",
          agency_raw: "ILTOLL",
          entry_location: "Elgin Rd.",
          entry_lane: "53",
          transponder_number: "02400454986",
          trip_charge: "7.35",
          trip_charge_raw: "(7.35)",
        },
      ],
    });
    await renderPage();
    const expand = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "#9");
    await act(async () => {
      expand!.click();
    });
    const agency = host!.querySelector('[data-testid="toll-review-sort-agency"]') as HTMLButtonElement;
    await act(async () => {
      agency.click();
    });
    const orders = Array.from(host!.querySelectorAll("[data-testid^='toll-review-row-']")).map(
      (row) => row.getAttribute("data-testid"),
    );
    expect(orders).toEqual(["toll-review-row-2", "toll-review-row-1"]);
    expect(agency.getAttribute("aria-sort")).toBe("ascending");
    await act(async () => {
      agency.click();
    });
    expect(agency.getAttribute("aria-sort")).toBe("descending");
  });

  it("uses a processed statement workspace after Process", async () => {
    apiMocks.getTollPdfReview.mockResolvedValue({
      ...listItem,
      status: "PROCESSED",
      review_status: "PROCESSED",
      source_page_count: 7,
      total_row_count: 1,
      rows: [
        {
          row_id: 1,
          source_row_order: 1,
          agency_raw: "ILTOLL",
          trip_charge: "7.35",
        },
      ],
    });
    await renderPage();
    const expand = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "#9");
    await act(async () => {
      expand!.click();
    });
    expect(host?.textContent).toContain("Processed statement");
    expect(host?.textContent).toContain("Processed · read-only");
    expect(host?.textContent).not.toContain("Correct");
    expect(host?.querySelector('[data-testid="tolls-upload"]')?.className).toContain("trk-page--dense");
  });
});
