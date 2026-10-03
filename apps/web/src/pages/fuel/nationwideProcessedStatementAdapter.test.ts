import { describe, expect, it } from "vitest";
import { adaptNationwideImportRowsForProcessedStatement } from "./nationwideProcessedStatementAdapter";
import { processedStatementCellDisplay } from "./processedStatementCellDisplay";

describe("adaptNationwideImportRowsForProcessedStatement", () => {
  it("maps unit price and discount into shared statement columns", () => {
    const rows = adaptNationwideImportRowsForProcessedStatement([
      {
        id: 10,
        import_id: "nw-1",
        row_type: "TRANSACTION",
        unit_number: "788",
        volume: "674.17",
        ex_gst_per_unit: "1.2345",
        total: "1263.85",
        currency: "CAD",
        product: "DIESEL",
        city: "Niagara-On-The-Lake",
        prov_st: "ON",
      },
      {
        id: 11,
        import_id: "nw-1",
        row_type: "TRANSACTION",
        usa_discount: "",
        missed_disc: "",
        ex_gst_per_unit: "",
        volume: "100",
        total: "50.00",
        currency: "USD",
      },
    ]);
    expect(rows[0].billed).toBe("1.2345");
    expect(rows[0].retail).toBe("");
    expect(processedStatementCellDisplay(rows[0], "retail")).toBe("0.00");
    expect(processedStatementCellDisplay(rows[0], "billed")).toBe("1.2345");
    expect(processedStatementCellDisplay(rows[0], "disc_amt")).toBe("0.00");
    expect(rows[1].notes_raw ?? "").toBe("");
    expect(processedStatementCellDisplay(rows[1], "disc_amt")).toBe("0.00");
  });

  it("does not map USA Discount into BVD disc_amt column", () => {
    const rows = adaptNationwideImportRowsForProcessedStatement([
      {
        id: 12,
        import_id: "nw-1",
        row_type: "TRANSACTION",
        ex_gst_per_unit: "4.829",
        usa_discount: "3.69",
        total: "357.39",
        currency: "USD",
        volume: "74.01",
      },
    ]);
    expect(processedStatementCellDisplay(rows[0], "disc_amt")).toBe("0.00");
    expect(rows[0].notes_raw).toContain("USA Discount: 3.69");
  });
});
