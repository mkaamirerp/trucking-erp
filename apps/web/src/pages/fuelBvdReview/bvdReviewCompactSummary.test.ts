import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { buildBvdReviewCompactSummary, displayBvdStatementCurrency } from "./bvdReviewCompactSummary";
import type { FuelBvdSourceReconciliation } from "./bvdReconciliationStrip";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../../..");
const golden = JSON.parse(
  readFileSync(join(repoRoot, "tests/fixtures/fuel_bvd_972201_expected.json"), "utf-8"),
) as { rows: Record<string, unknown>[] };

function goldenRows(): FuelBvdRow[] {
  return golden.rows.map((r, i) => ({
    id: i + 1,
    import_id: "import-972201",
    review_status: "PENDING",
    ...r,
  })) as FuelBvdRow[];
}

function recon(partial: Partial<FuelBvdSourceReconciliation>): FuelBvdSourceReconciliation {
  return {
    passed: true,
    transaction_total: "0",
    all_unit_total: "0",
    provider_grand_total: "0",
    difference: "0.00",
    checks: [],
    ...partial,
  };
}

describe("displayBvdStatementCurrency", () => {
  it("maps BVD US/CN codes for display", () => {
    expect(displayBvdStatementCurrency("US")).toBe("USD");
    expect(displayBvdStatementCurrency("CN")).toBe("CAD");
    expect(displayBvdStatementCurrency("EUR")).toBe("EUR");
  });
});

describe("buildBvdReviewCompactSummary", () => {
  it("builds reconciliation label from backend checks", () => {
    const rows = goldenRows();
    const model = buildBvdReviewCompactSummary(
      rows,
      recon({
        passed: true,
        provider_grand_total: "9047.72",
        checks: [
          { code: "A", status: "PASS" },
          { code: "B", status: "PASS" },
          { code: "C", status: "PASS" },
        ],
      }),
    );
    expect(model.reconciliationLabel).toBe("3/3 PASS");
    expect(model.reconciliationPass).toBe(true);
  });

  it("omits tax lines when grand total taxes are zero", () => {
    const rows = goldenRows();
    const grand = rows.find((r) => r.row_type === "GRAND_TOTAL" && r.row_label === "Grand Total");
    if (grand) {
      grand.hst = "0.00";
      grand.gst = "0.00";
      grand.pst = "0.00";
      grand.qst = "0.00";
    }
    const model = buildBvdReviewCompactSummary(rows, recon({ passed: true }));
    expect(model.taxes).toEqual([]);
  });

  it("includes product breakdown segments from grand total lines", () => {
    const model = buildBvdReviewCompactSummary(goldenRows(), recon({ passed: true }));
    expect(model.productSegments.some((s) => s.key === "TA")).toBe(true);
    expect(model.productSegments.find((s) => s.key === "TA")?.amountDisplay).toBeTruthy();
  });

  it("sums purchase discount and qty from transaction rows", () => {
    const rows: FuelBvdRow[] = [
      {
        id: 1,
        import_id: "x",
        row_type: "HEADER",
        invoice_number: "838710",
        cur: "US",
      } as FuelBvdRow,
      {
        id: 2,
        import_id: "x",
        row_type: "TRANSACTION",
        card_number: "1",
        cur: "US",
        qty: "10.50",
        disc_amt: "1.25",
        final_amt: "100.00",
      } as FuelBvdRow,
      {
        id: 3,
        import_id: "x",
        row_type: "TRANSACTION",
        card_number: "2",
        cur: "US",
        qty: "5.00",
        disc_amt: "2.75",
        final_amt: "50.00",
      } as FuelBvdRow,
      {
        id: 4,
        import_id: "x",
        row_type: "GRAND_TOTAL",
        row_label: "Grand Total",
        final_amount: "150.00",
        cur: "US",
      } as FuelBvdRow,
    ];
    const model = buildBvdReviewCompactSummary(
      rows,
      recon({
        passed: true,
        provider_grand_total: "150.00",
        currencies_seen: ["US"],
      }),
    );
    expect(model.currencyBlocks[0].discountTotal).toBe("4.00");
    expect(model.currencyBlocks[0].qtyTotal).toBe("15.50");
    expect(model.currencyBlocks[0].currency).toBe("USD");
    expect(model.cardsCount).toBe(2);
  });
});
