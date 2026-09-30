import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { operationalCell } from "./bvdParsedDisplay";
import {
  buildProcessedStatementSearchHaystack,
  filterProcessedStatementRows,
  processedStatementRowMatchesSearch,
} from "./fuelProcessedStatementSearch";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../../..");
const fixture972201 = JSON.parse(
  readFileSync(join(repoRoot, "tests/fixtures/fuel_bvd_972201_expected.json"), "utf-8"),
) as { rows: FuelBvdRow[] };

function txn(id: number, partial: Partial<FuelBvdRow> = {}): FuelBvdRow {
  return {
    id,
    import_id: "imp-a",
    row_type: "TRANSACTION",
    transaction_date: "2025-12-12 10:00:00",
    unit_number: "1103",
    driver_name: "Nathnel Example",
    card_number: "4237061",
    auth_code: "E345296820",
    express_code: "5359948",
    prod: "DF",
    payee_raw: "lumper fee",
    final_amt: "203.00",
    ...partial,
  } as FuelBvdRow;
}

const rows972201 = fixture972201.rows
  .filter((r) => r.row_type === "TRANSACTION")
  .map((r, i) => ({ ...r, id: i + 1, import_id: "972201" })) as FuelBvdRow[];

describe("fuelProcessedStatementSearch", () => {
  const ctx = { headerCardNumber: "4237111" };

  it("empty search returns all rows when date is all", () => {
    const rows = [txn(1), txn(2, { unit_number: "9999" })];
    expect(filterProcessedStatementRows(rows, "", { kind: "all" }, ctx)).toHaveLength(2);
  });

  it("unit partial and exact search", () => {
    expect(processedStatementRowMatchesSearch(txn(1), "1103", ctx)).toBe(true);
    expect(processedStatementRowMatchesSearch(txn(1), "110", ctx)).toBe(true);
    expect(processedStatementRowMatchesSearch(txn(1), "1104", ctx)).toBe(false);
  });

  it("driver case-insensitive search", () => {
    expect(processedStatementRowMatchesSearch(txn(1, { driver_name: "NATHNEL" }), "nathnel", ctx)).toBe(
      true,
    );
  });

  it("card/account search uses row and header card", () => {
    expect(processedStatementRowMatchesSearch(txn(1, { card_number: "4237061" }), "4237061", ctx)).toBe(
      true,
    );
    expect(processedStatementRowMatchesSearch(txn(1, { card_number: "" }), "4237111", ctx)).toBe(true);
  });

  it("auth and provider reference search", () => {
    expect(processedStatementRowMatchesSearch(txn(1), "e345296820", ctx)).toBe(true);
    expect(processedStatementRowMatchesSearch(txn(1), "5359948", ctx)).toBe(true);
  });

  it("product search includes display label", () => {
    const hay = buildProcessedStatementSearchHaystack(txn(1, { prod: "TA" }), ctx);
    expect(hay).toContain("fuel");
    expect(processedStatementRowMatchesSearch(txn(1, { prod: "DF" }), "def", ctx)).toBe(true);
  });

  it("provider reason search", () => {
    expect(processedStatementRowMatchesSearch(txn(1), "lumper", ctx)).toBe(true);
  });

  it("amount search matches formatted money", () => {
    expect(processedStatementRowMatchesSearch(txn(1, { final_amt: "1,610.96" }), "1610.96", ctx)).toBe(
      true,
    );
    expect(processedStatementRowMatchesSearch(txn(1), "203.00", ctx)).toBe(true);
  });

  it("date search matches transaction timestamp", () => {
    expect(processedStatementRowMatchesSearch(txn(1), "2025-12-12", ctx)).toBe(true);
  });

  it("search is limited to provided row set (statement scope)", () => {
    const invoiceA = [txn(1, { import_id: "a" })];
    const invoiceB = [txn(2, { import_id: "b", unit_number: "1103" })];
    expect(filterProcessedStatementRows(invoiceA, "1103", { kind: "all" }, ctx)).toHaveLength(1);
    expect(filterProcessedStatementRows(invoiceB, "1103", { kind: "all" }, ctx)).toHaveLength(1);
    expect(invoiceA[0].import_id).not.toBe(invoiceB[0].import_id);
  });

  it("972201 fixture supports unit and date filtering without mutating rows", () => {
    const before = rows972201.map((r) => r.unit_number);
    const jul23 = filterProcessedStatementRows(
      rows972201,
      "",
      { kind: "week", year: 2026, month: 7, week: 4 },
      { headerCardNumber: "4237111" },
    );
    expect(jul23.length).toBeGreaterThan(0);
    expect(rows972201.map((r) => r.unit_number)).toEqual(before);
    const byUnit = filterProcessedStatementRows(rows972201, "1100", { kind: "all" }, ctx);
    expect(byUnit.every((r) => operationalCell(r, "unit_number").includes("1100"))).toBe(true);
  });

  it("search + custom date combine", () => {
    const rows = [
      txn(1, { transaction_date: "2025-12-12 00:00:00", unit_number: "1103" }),
      txn(2, { transaction_date: "2025-12-15 00:00:00", unit_number: "1103" }),
      txn(3, { transaction_date: "2025-12-12 00:00:00", unit_number: "2200" }),
    ];
    const filtered = filterProcessedStatementRows(rows, "1103", {
      kind: "custom",
      from: "2025-12-12",
      to: "2025-12-14",
    }, ctx);
    expect(filtered.map((r) => r.id)).toEqual([1]);
  });
});
