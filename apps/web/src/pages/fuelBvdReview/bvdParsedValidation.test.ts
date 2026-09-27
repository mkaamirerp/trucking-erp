import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { computeBvdParsedValidation } from "./bvdParsedValidation";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "../../../../..");
const golden = JSON.parse(
  readFileSync(join(repoRoot, "tests/fixtures/fuel_bvd_972201_expected.json"), "utf-8"),
) as { rows: Record<string, unknown>[] };

function goldenAsReviewRows(): FuelBvdRow[] {
  return golden.rows.map((r, i) => ({
    id: i + 1,
    import_id: "test",
    ...r,
  })) as FuelBvdRow[];
}

describe("computeBvdParsedValidation", () => {
  it("passes invoice, units, and cash checks for fixture 972201", () => {
    const result = computeBvdParsedValidation(goldenAsReviewRows());
    expect(result.allPass).toBe(true);

    const invoice = result.metrics.find((m) => m.id === "invoice_amount");
    expect(invoice?.value).toBe("3,421.01");
    expect(invoice?.status).toBe("pass");

    const units = result.metrics.find((m) => m.id === "units_processed");
    expect(units?.value).toBe("2 units");
    expect(units?.subvalue).toBe("1100, 1104");
    expect(units?.status).toBe("pass");
    expect(units?.detail).toBe("2 units billed on this invoice");

    const cash = result.metrics.find((m) => m.id === "cash_advance");
    expect(cash?.value).toBe("0.00");
    expect(cash?.status).toBe("pass");
  });

  it("shows one billed unit when only one unit # appears on transactions", () => {
    const rows = goldenAsReviewRows().filter(
      (r) => r.row_type !== "TRANSACTION" || r.unit_number === "1100",
    );
    const result = computeBvdParsedValidation(rows);
    const units = result.metrics.find((m) => m.id === "units_processed");
    expect(units?.value).toBe("1 unit");
    expect(units?.subvalue).toBe("1100");
  });

  it("flags invoice mismatch when transaction total disagrees with controls", () => {
    const rows = goldenAsReviewRows();
    const txn = rows.find((r) => r.auth_code === "A204040667-TA");
    if (txn) txn.final_amt = "9,999.99";

    const result = computeBvdParsedValidation(rows);
    const invoice = result.metrics.find((m) => m.id === "invoice_amount");
    expect(invoice?.status).toBe("fail");
    expect(invoice?.detail).toMatch(/Mismatch/);
    expect(result.allPass).toBe(false);
  });
});
