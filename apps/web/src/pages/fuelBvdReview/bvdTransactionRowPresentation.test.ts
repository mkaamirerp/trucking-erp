import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { bvdProductDisplayLabel } from "./bvdProductDisplay";
import {
  bvdTxnDiscountAmount,
  bvdTxnNonZeroTaxLines,
  bvdTxnPriceDisplay,
  formatBvdTransactionDateTime,
  formatBvdTxnLocationShort,
  formatCanonicalCalendarDate,
} from "./bvdTransactionRowPresentation";

function txn(partial: Partial<FuelBvdRow>): FuelBvdRow {
  return {
    id: 1,
    import_id: "x",
    row_type: "TRANSACTION",
    ...partial,
  } as FuelBvdRow;
}

describe("bvdProductDisplayLabel", () => {
  it("J: unknown product code remains visible", () => {
    expect(bvdProductDisplayLabel("XX")).toBe("XX");
    expect(bvdProductDisplayLabel("TA")).toBe("Fuel");
  });
});

describe("bvdTxnNonZeroTaxLines", () => {
  it("D: HST non-zero, GST/PST/QST zero — only HST", () => {
    const lines = bvdTxnNonZeroTaxLines(
      txn({ hst: "185.33", gst: "0.00", pst: "0.00", qst: "0.00" }),
    );
    expect(lines.map((l) => l.key)).toEqual(["hst"]);
  });

  it("E: all taxes zero — empty list", () => {
    expect(bvdTxnNonZeroTaxLines(txn({ hst: "0", gst: "0.00", pst: "", qst: "0" }))).toEqual([]);
  });
});

describe("bvdTxnDiscountAmount", () => {
  it("F: discount zero omitted", () => {
    expect(bvdTxnDiscountAmount(txn({ disc_amt: "0.00" }))).toBeNull();
  });

  it("G: discount non-zero shown", () => {
    expect(bvdTxnDiscountAmount(txn({ disc_amt: "-12.50" }))).toBe("-12.50");
  });
});

describe("bvdTxnPriceDisplay", () => {
  it("H: retail equals billed — billed only flag", () => {
    const d = bvdTxnPriceDisplay(txn({ retail: "2.2390", billed: "2.2390" }));
    expect(d.showRetail).toBe(false);
  });

  it("I: retail differs from billed — both flagged", () => {
    const d = bvdTxnPriceDisplay(txn({ retail: "2.50", billed: "2.39" }));
    expect(d.showRetail).toBe(true);
  });
});

describe("formatCanonicalCalendarDate / formatBvdTransactionDateTime date-only", () => {
  it("renders YYYY-MM-DD as calendar date without timezone shift or clock time", () => {
    const input = "2026-06-09";
    expect(formatCanonicalCalendarDate(input)).toBe("Jun 9, 2026");
    expect(formatBvdTransactionDateTime(input)).toBe("Jun 9, 2026");
    expect(formatBvdTransactionDateTime(input)).not.toMatch(/Jun 8/);
    expect(formatBvdTransactionDateTime(input)).not.toMatch(/20:00/);
  });

  it("keeps calendar day on DST-adjacent date-only values (no previous-day shift)", () => {
    const input = "2026-03-08";
    expect(formatBvdTransactionDateTime(input)).toBe("Mar 8, 2026");
    expect(formatBvdTransactionDateTime(input)).not.toMatch(/Mar 7/);
    expect(formatBvdTransactionDateTime(input)).not.toMatch(/:\d{2}/);
  });

  it("still formats BVD datetime strings with local time", () => {
    const formatted = formatBvdTransactionDateTime("2026-07-23 02:17:56");
    expect(formatted).toMatch(/Jul 23/);
    expect(formatted).toMatch(/02:17/);
  });
});

describe("formatBvdTxnLocationShort", () => {
  it("dedupes identical site name and city", () => {
    expect(
      formatBvdTxnLocationShort(
        txn({ site_name: "BOWMANVILLE", site_city: "BOWMANVILLE", prov_st: "ON" }),
      ),
    ).toBe("Bowmanville, ON");
  });
});
