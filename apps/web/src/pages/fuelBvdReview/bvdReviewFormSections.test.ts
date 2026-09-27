import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { buildFormSectionsForPage } from "./bvdReviewFormSections";
import { buildReviewLogicalRows } from "./bvdReviewLines";

describe("buildFormSectionsForPage", () => {
  it("lists each transaction field separately on the form", () => {
    const rows: FuelBvdRow[] = [
      { id: 1, import_id: "x", row_type: "HEADER", source_page: 1 } as FuelBvdRow,
      {
        id: 2,
        import_id: "x",
        row_type: "TRANSACTION",
        source_page: 1,
        source_row_number: 1,
        auth_code: "A1",
        unit_number: "1100",
      } as FuelBvdRow,
    ];
    const logical = buildReviewLogicalRows(rows);
    const sections = buildFormSectionsForPage(rows, logical, 1);
    const txn = sections.find((s) => s.row?.row_type === "TRANSACTION");
    expect(txn).toBeDefined();
    const names = txn!.fields.map((f) => f.fieldName);
    expect(names).toContain("unit_number");
    expect(names).toContain("transaction_date");
    expect(names.indexOf("unit_number")).not.toBe(names.indexOf("transaction_date"));
  });
});
