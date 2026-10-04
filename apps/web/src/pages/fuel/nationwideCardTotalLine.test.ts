import { describe, expect, it } from "vitest";
import {
  buildNationwideCardTaxLedger,
  normalizeNationwideCardKey,
  parseNationwideCardTotalLine,
} from "./nationwideCardTotalLine";
import { activeBvdTxnTaxColumns } from "../fuelBvdReview/fuelBvdTxnMoneyColumns";
import { adaptNationwideImportRowsForProcessedStatement } from "./nationwideProcessedStatementAdapter";

describe("parseNationwideCardTotalLine", () => {
  it("parses CAD Niagara CARD_TOTAL with GST $145.4", () => {
    const parsed = parseNationwideCardTotalLine(
      "XXXXX87195 Total GST $145.4 QST $0 674.17 $1,263.85 $0.00 $0.00",
    );
    expect(parsed?.cardNumber).toBe("XXXXX87195");
    expect(parsed?.currency).toBe("CAD");
    expect(parsed?.gst).toBe("145.40");
    expect(parsed?.declaredAmount).toBe("1263.85");
  });
});

describe("normalizeNationwideCardKey", () => {
  it("matches masked and short card numbers", () => {
    expect(normalizeNationwideCardKey("X87195")).toBe(normalizeNationwideCardKey("XXXXX87195"));
  });
});

describe("adaptNationwideImportRowsForProcessedStatement + CARD_TOTAL", () => {
  it("shows GST column from card total when purchase row lacks line gst/currency", () => {
    const rows = adaptNationwideImportRowsForProcessedStatement([
      {
        id: 1,
        import_id: "nw",
        row_type: "TRANSACTION",
        card_number: "X87195",
        unit_number: "788",
        volume: "674.17",
        ex_gst_per_unit: "1.659",
        total: "1,263.85",
        product: "DIESEL",
      },
      {
        id: 2,
        import_id: "nw",
        row_type: "CONTROL",
        control_type: "CARD_TOTAL",
        control_line_raw:
          "XXXXX87195 Total GST $145.4 QST $0 674.17 $1,263.85 $0.00 $0.00",
        gst: "145.40",
        currency: "CAD",
      },
    ]);
    expect(rows).toHaveLength(1);
    expect(rows[0].pre_tax_amt).toBe("1,118.45");
    expect(rows[0].gst).toBe("145.40");
    expect(rows[0].cur).toBe("CAD");
    expect(activeBvdTxnTaxColumns(rows).map((c) => c.field)).toContain("gst");
  });

  it("parses Ex-GST unit with $ and shows GST without CARD_TOTAL row", () => {
    const rows = adaptNationwideImportRowsForProcessedStatement([
      {
        id: 1,
        import_id: "nw",
        row_type: "TRANSACTION",
        volume: "674.17",
        ex_gst_per_unit: "$1.659",
        total: "1,263.85",
        currency: "CAD",
      },
    ]);
    expect(rows[0].pre_tax_amt).toBe("1,118.45");
    expect(rows[0].gst).toBe("145.40");
    expect(activeBvdTxnTaxColumns(rows).map((c) => c.field)).toContain("gst");
  });

  it("uses source reconciliation cad_gst when line taxes still missing", () => {
    const rows = adaptNationwideImportRowsForProcessedStatement(
      [
        {
          id: 1,
          import_id: "nw",
          row_type: "TRANSACTION",
          volume: "674.17",
          total: "1,263.85",
          currency: "CAD",
        },
      ],
      { passed: true, checks: [], cad_gst: "145.40" },
    );
    expect(rows[0].gst).toBe("145.40");
    expect(rows[0].pre_tax_amt).toBe("1,118.45");
  });

  it("buildNationwideCardTaxLedger reads control row gst", () => {
    const ledger = buildNationwideCardTaxLedger([
      {
        row_type: "CONTROL",
        control_type: "CARD_TOTAL",
        control_line_raw:
          "XXXXX87195 Total GST $145.4 QST $0 674.17 $1,263.85 $0.00 $0.00",
        gst: "145.40",
        currency: "CAD",
      },
    ]);
    expect(ledger.get("87195")?.gst).toBeCloseTo(145.4, 2);
  });
});
