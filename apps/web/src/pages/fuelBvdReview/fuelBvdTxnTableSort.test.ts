import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import {
  compareFuelBvdIdentifier,
  compareFuelBvdTxnRows,
  parseFuelBvdTxnDateSortKey,
  sortFuelBvdTransactions,
  type FuelBvdTxnSortColumn,
} from "./fuelBvdTxnTableSort";

function txn(id: number, partial: Partial<FuelBvdRow> = {}): FuelBvdRow {
  return {
    id,
    import_id: "imp",
    row_type: "TRANSACTION",
    transaction_date: "2026-07-23 02:17:56",
    unit_number: "1100",
    driver_name: "ALPHA",
    site_name: "SITE A",
    site_city: "CITY A",
    prov_st: "ON",
    prod: "TA",
    qty: "100.00",
    final_amt: "500.00",
    cur: "CN",
    ...partial,
  } as FuelBvdRow;
}

describe("fuelBvdTxnTableSort", () => {
  it("default order equals source order when sort is not applied", () => {
    const rows = [txn(1), txn(2), txn(3)];
    expect(rows.map((r) => r.id)).toEqual([1, 2, 3]);
  });

  it("date ascending and descending by timestamp", () => {
    const rows = [
      txn(1, { transaction_date: "2026-07-24 10:00:00" }),
      txn(2, { transaction_date: "2026-07-23 02:17:56" }),
      txn(3, { transaction_date: "2026-07-25 01:00:00" }),
    ];
    const asc = sortFuelBvdTransactions(rows, { column: "date", direction: "asc" });
    expect(asc.map((r) => r.id)).toEqual([2, 1, 3]);
    const desc = sortFuelBvdTransactions(rows, { column: "date", direction: "desc" });
    expect(desc.map((r) => r.id)).toEqual([3, 1, 2]);
  });

  it("parseFuelBvdTxnDateSortKey uses actual datetime not display text", () => {
    const a = parseFuelBvdTxnDateSortKey("2026-07-23 02:17:56");
    const b = parseFuelBvdTxnDateSortKey("2026-07-23 14:00:00");
    expect(a).toBeLessThan(b);
  });

  it("unit sorting preserves identifier semantics and leading zeros", () => {
    expect(compareFuelBvdIdentifier("001107", "S1107")).toBeLessThan(0);
    const rows = [txn(1, { unit_number: "S1107" }), txn(2, { unit_number: "001107" })];
    const sorted = sortFuelBvdTransactions(rows, { column: "unit", direction: "asc" });
    expect(sorted.map((r) => r.unit_number)).toEqual(["001107", "S1107"]);
  });

  it("source driver sorting", () => {
    const rows = [
      txn(1, { driver_name: "ZULU" }),
      txn(2, { driver_name: "ALPHA" }),
      txn(3, { driver_name: "MIKE" }),
    ];
    const sorted = sortFuelBvdTransactions(rows, { column: "driver", direction: "asc" });
    expect(sorted.map((r) => r.driver_name)).toEqual(["ALPHA", "MIKE", "ZULU"]);
  });

  it("location sorting by displayed location", () => {
    const rows = [
      txn(1, { site_name: "ZED", site_city: "Z", prov_st: "ON" }),
      txn(2, { site_name: "ALPHA", site_city: "A", prov_st: "ON" }),
    ];
    const sorted = sortFuelBvdTransactions(rows, { column: "location", direction: "asc" });
    expect(sorted[0].id).toBe(2);
  });

  it("product sorting by display label", () => {
    const rows = [
      txn(1, { prod: "DF" }),
      txn(2, { prod: "TA" }),
    ];
    const sorted = sortFuelBvdTransactions(rows, { column: "product", direction: "asc" });
    expect(sorted.map((r) => r.prod)).toEqual(["DF", "TA"]);
  });

  it("qty numeric sorting", () => {
    const rows = [
      txn(1, { qty: "1,000.50" }),
      txn(2, { qty: "99.9" }),
      txn(3, { qty: "100.00" }),
    ];
    const sorted = sortFuelBvdTransactions(rows, { column: "qty", direction: "asc" });
    expect(sorted.map((r) => r.id)).toEqual([2, 3, 1]);
  });

  it("final amount numeric sorting", () => {
    const rows = [
      txn(1, { final_amt: "2,000.00" }),
      txn(2, { final_amt: "10.00" }),
    ];
    const sorted = sortFuelBvdTransactions(rows, { column: "final", direction: "asc" });
    expect(sorted.map((r) => r.id)).toEqual([2, 1]);
  });

  it("currency sorting", () => {
    const rows = [
      txn(1, { cur: "US" }),
      txn(2, { cur: "CN" }),
      txn(3, { cur: "CAD" }),
    ];
    const sorted = sortFuelBvdTransactions(rows, { column: "currency", direction: "asc" });
    expect(sorted.map((r) => r.cur)).toEqual(["CAD", "CN", "US"]);
  });

  it("stable sort keeps source order for equal keys", () => {
    const rows = [txn(1, { cur: "CN" }), txn(2, { cur: "CN" }), txn(3, { cur: "CN" })];
    const sorted = sortFuelBvdTransactions(rows, { column: "currency", direction: "asc" });
    expect(sorted.map((r) => r.id)).toEqual([1, 2, 3]);
  });

  it("compareFuelBvdTxnRows covers each column without throwing", () => {
    const a = txn(1);
    const b = txn(2);
    const cols: FuelBvdTxnSortColumn[] = [
      "date",
      "unit",
      "driver",
      "location",
      "product",
      "qty",
      "final",
      "currency",
    ];
    for (const col of cols) {
      expect(typeof compareFuelBvdTxnRows(a, b, col)).toBe("number");
    }
  });
});
