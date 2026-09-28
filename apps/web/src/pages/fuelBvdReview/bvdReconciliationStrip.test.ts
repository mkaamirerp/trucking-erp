import { describe, expect, it } from "vitest";
import { reconciliationStripFromBackend } from "./bvdReconciliationStrip";

describe("reconciliationStripFromBackend", () => {
  it("reflects backend pass/fail", () => {
    const pass = reconciliationStripFromBackend({
      passed: true,
      transaction_total: "3421.01",
      all_unit_total: "3421.01",
      provider_grand_total: "3421.01",
      difference: "0.00",
      checks: [],
    });
    expect(pass.allPass).toBe(true);
    expect(pass.metrics[0]?.status).toBe("pass");

    const fail = reconciliationStripFromBackend({
      passed: false,
      transaction_total: "3420.91",
      all_unit_total: "3420.91",
      provider_grand_total: "3421.01",
      difference: "0.10",
      checks: [{ code: "GRAND_TOTAL_FINAL", status: "FAIL" }],
    });
    expect(fail.allPass).toBe(false);
    expect(fail.metrics[0]?.status).toBe("fail");
    expect(fail.metrics[0]?.detail).toContain("3420.91");
  });
});
