import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import {
  activeBvdTxnTaxColumns,
  bvdTxnDiscountDisplay,
  bvdTxnTaxDisplay,
  sumBvdTxnMoneyField,
} from "./fuelBvdTxnMoneyColumns";
import { compareFuelBvdTxnRows, sortFuelBvdTransactions } from "./fuelBvdTxnTableSort";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../../..");
const fixture972201 = JSON.parse(
  readFileSync(join(repoRoot, "tests/fixtures/fuel_bvd_972201_expected.json"), "utf-8"),
) as { rows: FuelBvdRow[] };

function txn(id: number, partial: Partial<FuelBvdRow> = {}): FuelBvdRow {
  return {
    id,
    import_id: "imp",
    row_type: "TRANSACTION",
    transaction_date: "2026-07-23 02:17:56",
    unit_number: "1100",
    driver_name: "DRIVER",
    prod: "TA",
    qty: "100.00",
    hst: "0.00",
    gst: "0.00",
    pst: "0.00",
    qst: "0.00",
    disc_amt: "0.00",
    final_amt: "500.00",
    cur: "CN",
    ...partial,
  } as FuelBvdRow;
}

const rows972201 = fixture972201.rows
  .filter((r) => r.row_type === "TRANSACTION")
  .map((r, i) => ({ ...r, id: i + 1, import_id: "972201" })) as FuelBvdRow[];

/** Demo permanent 838710 shape: discounts, all source taxes zero. */
const rows838710Like: FuelBvdRow[] = [
  txn(1, { disc_amt: "44.24", hst: "0.00", gst: "0.00", pst: "0.00", qst: "0.00", final_amt: "155.77" }),
  txn(2, { disc_amt: "80.56", hst: "0.00", gst: "0.00", pst: "0.00", qst: "0.00", final_amt: "519.47" }),
  txn(3, { disc_amt: "0.00", hst: "0.00", gst: "0.00", pst: "0.00", qst: "0.00", final_amt: "65.60" }),
];

describe("fuelBvdTxnMoneyColumns", () => {
  it("zero discount displays 0.00", () => {
    expect(bvdTxnDiscountDisplay(txn(1, { disc_amt: "0.00" }))).toBe("0.00");
    expect(bvdTxnDiscountDisplay(txn(1, { disc_amt: "0" }))).toBe("0.00");
    expect(bvdTxnDiscountDisplay(txn(1, { disc_amt: "" }))).toBe("0.00");
    expect(bvdTxnDiscountDisplay(txn(1, {}))).toBe("0.00");
  });

  it("non-zero discount displays formatted amount", () => {
    expect(bvdTxnDiscountDisplay(txn(1, { disc_amt: "40.00" }))).toBe("40.00");
    expect(bvdTxnDiscountDisplay(txn(1, { disc_amt: "1,370.76" }))).toBe("1,370.76");
  });

  it("HST column appears only when any row has non-zero HST", () => {
    expect(activeBvdTxnTaxColumns([txn(1, { hst: "0.00" })])).toEqual([]);
    expect(activeBvdTxnTaxColumns([txn(1, { hst: "5.25" })]).map((c) => c.field)).toEqual(["hst"]);
  });

  it("GST PST QST columns follow the same invoice-level rule", () => {
    const rows = [
      txn(1, { gst: "0.00", pst: "0.00", qst: "0.00" }),
      txn(2, { gst: "1.00", pst: "2.00", qst: "0.00" }),
    ];
    expect(activeBvdTxnTaxColumns(rows).map((c) => c.field)).toEqual(["gst", "pst"]);
  });

  it("tax type zero across entire invoice stays hidden", () => {
    const rows = [txn(1, { hst: "10.00", gst: "0.00", pst: "0.00", qst: "0.00" })];
    expect(activeBvdTxnTaxColumns(rows).map((c) => c.field)).toEqual(["hst"]);
  });

  it("active tax column shows row-level zero as 0.00", () => {
    expect(bvdTxnTaxDisplay(txn(1, { hst: "0.00" }), "hst")).toBe("0.00");
    expect(bvdTxnTaxDisplay(txn(1, { gst: "5.25" }), "gst")).toBe("5.25");
  });

  it("972201 shows only HST among tax columns", () => {
    expect(activeBvdTxnTaxColumns(rows972201).map((c) => c.field)).toEqual(["hst"]);
    expect(sumBvdTxnMoneyField(rows972201, "disc_amt")).toBe(0);
    expect(sumBvdTxnMoneyField(rows972201, "hst")).toBeCloseTo(393.57, 2);
    expect(sumBvdTxnMoneyField(rows972201, "gst")).toBe(0);
  });

  it("838710-like set shows no tax columns and non-zero discount totals", () => {
    expect(activeBvdTxnTaxColumns(rows838710Like)).toEqual([]);
    expect(sumBvdTxnMoneyField(rows838710Like, "disc_amt")).toBeCloseTo(124.8, 2);
    expect(sumBvdTxnMoneyField(rows838710Like, "hst")).toBe(0);
  });

  it("discount and tax sorting uses numeric money comparison", () => {
    const rows = [
      txn(1, { disc_amt: "100.00", hst: "10.00" }),
      txn(2, { disc_amt: "5.00", hst: "50.00" }),
    ];
    const byDisc = sortFuelBvdTransactions(rows, { column: "discount", direction: "asc" });
    expect(byDisc.map((r) => r.id)).toEqual([2, 1]);
    const byHst = sortFuelBvdTransactions(rows, { column: "hst", direction: "desc" });
    expect(byHst.map((r) => r.id)).toEqual([2, 1]);
    expect(compareFuelBvdTxnRows(rows[0], rows[1], "discount")).toBeGreaterThan(0);
  });
});
