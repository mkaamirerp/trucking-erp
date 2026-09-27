import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { buildReviewLogicalRows, formatReviewLineNumber, reviewLineForSelection } from "./bvdReviewLines";

describe("buildReviewLogicalRows", () => {
  it("assigns invoice-wide line numbers shared by header and transactions", () => {
    const rows: FuelBvdRow[] = [
      { id: 1, import_id: "x", row_type: "HEADER", source_page: 1, invoice_number: "972201" } as FuelBvdRow,
      {
        id: 2,
        import_id: "x",
        row_type: "TRANSACTION",
        source_page: 1,
        source_row_number: 1,
        auth_code: "A1",
      } as FuelBvdRow,
      {
        id: 3,
        import_id: "x",
        row_type: "TRANSACTION",
        source_page: 1,
        source_row_number: 2,
        auth_code: "A2",
      } as FuelBvdRow,
    ];
    const lines = buildReviewLogicalRows(rows);
    expect(lines[0].reviewLineNumber).toBe(1);
    expect(lines[0].rowType).toBe("HEADER");
    const txn1 = lines.find((l) => l.fuelBvdId === 2);
    expect(txn1?.reviewLineNumber).toBe(2);
    expect(formatReviewLineNumber(txn1!.reviewLineNumber)).toBe("02");
  });

  it("maps all header fields to one shared invoice header line number", () => {
    const rows: FuelBvdRow[] = [
      { id: 1, import_id: "x", row_type: "HEADER", source_page: 1, client_email: "" } as FuelBvdRow,
    ];
    const lines = buildReviewLogicalRows(rows);
    expect(lines).toHaveLength(1);
    const n = reviewLineForSelection(lines, 1, "client_email", "HEADER");
    expect(n).toBe(1);
  });
});
