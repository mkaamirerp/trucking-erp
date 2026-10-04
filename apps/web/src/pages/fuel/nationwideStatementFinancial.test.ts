import { describe, expect, it } from "vitest";
import type { FuelNationwideRow } from "../../api";
import {
  nationwideExTaxLineAmount,
  nationwideStatementFinancialFields,
} from "./nationwideStatementFinancial";

function nw(partial: Partial<FuelNationwideRow>): FuelNationwideRow {
  return {
    id: 1,
    import_id: "nw",
    row_type: "TRANSACTION",
    ...partial,
  } as FuelNationwideRow;
}

describe("nationwideStatementFinancial", () => {
  it("CAD row uses CARD_TOTAL GST when ex-gst column missing", () => {
    const row = nw({
      volume: "674.17",
      total: "1,263.85",
      currency: "",
    });
    const fin = nationwideStatementFinancialFields(row, {
      cardTax: { currency: "CAD", gst: 145.4, pst: null, qst: 0, hst: null },
    });
    expect(fin.pre_tax_amt).toBe("1,118.45");
    expect(fin.gst).toBe("145.40");
  });

  it("CAD Niagara row: ex-tax extension + implied GST = final", () => {
    const row = nw({
      unit_number: "788",
      volume: "674.17",
      ex_gst_per_unit: "1.659",
      total: "1,263.85",
      currency: "CAD",
      gst: null,
    });
    expect(nationwideExTaxLineAmount(row)).toBeCloseTo(1118.45, 2);
    const fin = nationwideStatementFinancialFields(row);
    expect(fin.pre_tax_amt).toBe("1,118.45");
    expect(fin.gst).toBe("145.40");
  });

  it("USD row: pre-tax equals provider total (no line tax split)", () => {
    const row = nw({
      volume: "100.00",
      ex_gst_per_unit: "4.629",
      total: "462.90",
      currency: "USD",
    });
    const fin = nationwideStatementFinancialFields(row);
    expect(fin.pre_tax_amt).toBe("462.90");
    expect(fin.gst).toBeUndefined();
  });
});
