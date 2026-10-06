import { describe, expect, it } from "vitest";
import type { TollPdfReviewRow } from "../../api";
import { nextTollReviewSort, sortTollReviewRows } from "./tollReviewRowSort";

function row(partial: Partial<TollPdfReviewRow> & { source_row_order: number }): TollPdfReviewRow {
  return {
    row_id: partial.source_row_order,
    source_page_number: 1,
    post_date: "2023-03-01",
    entry_date: "2023-03-01",
    entry_time: "10:00",
    exit_date: null,
    exit_time: null,
    agency_raw: "ILTOLL",
    entry_location: "A",
    entry_lane: "1",
    exit_location: null,
    exit_lane: null,
    transponder_number: "02400000001",
    plate_number: null,
    trip_charge: "7.35",
    trip_charge_raw: "(7.35)",
    ...partial,
  };
}

describe("tollReviewRowSort", () => {
  it("sorts agency ascending then descending", () => {
    const rows = [row({ source_row_order: 1, agency_raw: "WVPA" }), row({ source_row_order: 2, agency_raw: "ILTOLL" })];
    const asc = sortTollReviewRows(rows, { column: "agency", direction: "asc" });
    expect(asc.map((item) => item.agency_raw)).toEqual(["ILTOLL", "WVPA"]);
    const desc = sortTollReviewRows(rows, { column: "agency", direction: "desc" });
    expect(desc.map((item) => item.agency_raw)).toEqual(["WVPA", "ILTOLL"]);
  });

  it("sorts trip charge as decimal", () => {
    const rows = [row({ source_row_order: 1, trip_charge: "14.65" }), row({ source_row_order: 2, trip_charge: "7.35" })];
    const asc = sortTollReviewRows(rows, { column: "charge", direction: "asc" });
    expect(asc.map((item) => item.trip_charge)).toEqual(["7.35", "14.65"]);
  });

  it("keeps source order as a stable tie-break", () => {
    const rows = [row({ source_row_order: 4, agency_raw: "ILTOLL" }), row({ source_row_order: 1, agency_raw: "ILTOLL" })];
    const sorted = sortTollReviewRows(rows, { column: "agency", direction: "asc" });
    expect(sorted.map((item) => item.source_row_order)).toEqual([4, 1]);
  });

  it("toggles the same column and starts ascending on a new column", () => {
    const first = nextTollReviewSort(null, "agency");
    expect(first).toEqual({ column: "agency", direction: "asc" });
    expect(nextTollReviewSort(first, "agency")).toEqual({ column: "agency", direction: "desc" });
    expect(nextTollReviewSort(first, "charge")).toEqual({ column: "charge", direction: "asc" });
  });
});
