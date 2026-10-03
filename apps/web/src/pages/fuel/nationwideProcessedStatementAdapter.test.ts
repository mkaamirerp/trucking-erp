import { describe, expect, it } from "vitest";
import {
  adaptNationwideImportRowsForProcessedStatement,
  applyNationwideCanonicalPricesToStatementRows,
  deriveNationwideRetailUnitPriceFromSource,
} from "./nationwideProcessedStatementAdapter";
import { processedStatementCellDisplay } from "./processedStatementCellDisplay";

describe("adaptNationwideImportRowsForProcessedStatement", () => {
  it("maps billed, derived retail, and USA discount into statement columns", () => {
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
        usa_discount: "0.00",
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
    expect(rows[0].retail).toBe("1.2345");
    expect(processedStatementCellDisplay(rows[0], "retail")).toBe("1.2345");
    expect(processedStatementCellDisplay(rows[0], "billed")).toBe("1.2345");
    expect(processedStatementCellDisplay(rows[0], "disc_amt")).toBe("0.00");
    expect(rows[1].notes_raw ?? "").toBe("");
    expect(processedStatementCellDisplay(rows[1], "disc_amt")).toBe("0.00");
  });

  it("derives retail from billed, volume, and USA discount (Fultonville)", () => {
    const rows = adaptNationwideImportRowsForProcessedStatement([
      {
        id: 12,
        import_id: "nw-1",
        row_type: "TRANSACTION",
        ex_gst_per_unit: "4.629",
        usa_discount: "5.92",
        total: "33.38",
        currency: "USD",
        volume: "7.21",
      },
    ]);
    expect(processedStatementCellDisplay(rows[0], "billed")).toBe("4.629");
    expect(processedStatementCellDisplay(rows[0], "disc_amt")).toBe("5.92");
    expect(processedStatementCellDisplay(rows[0], "retail")).toBe("5.450082");
  });
});

describe("deriveNationwideRetailUnitPriceFromSource", () => {
  it("matches backend Fultonville unit retail", () => {
    expect(deriveNationwideRetailUnitPriceFromSource("4.629", "7.21", "5.92")).toBe(
      "5.450082",
    );
  });
});

describe("applyNationwideCanonicalPricesToStatementRows", () => {
  it("overrides adapter fields from processed canonical transactions", () => {
    const rows = adaptNationwideImportRowsForProcessedStatement([
      {
        id: 99,
        import_id: "nw-1",
        row_type: "TRANSACTION",
        ex_gst_per_unit: "4.629",
        usa_discount: "5.92",
        volume: "7.21",
        total: "33.38",
        currency: "USD",
      },
    ]);
    const merged = applyNationwideCanonicalPricesToStatementRows(rows, [
      {
        id: 1,
        batch_id: 1,
        source_row_id: "99",
        retail_amount: "5.4501",
        billed_amount: "4.6290",
        provider_discount_amount: "5.9200",
      },
    ]);
    expect(merged[0].retail).toBe("5.4501");
    expect(merged[0].billed).toBe("4.6290");
    expect(merged[0].disc_amt).toBe("5.9200");
  });
});
