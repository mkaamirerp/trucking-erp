import { describe, expect, it } from "vitest";
import { formatFuelBvdReviewActionError } from "./bvdReviewActionErrors";

describe("formatFuelBvdReviewActionError", () => {
  it("formats reconciliation failure with failed checks", () => {
    const err = new Error(
      JSON.stringify({
        detail: {
          code: "BVD_SOURCE_RECONCILIATION_FAILED",
          message: "Required BVD source validations did not pass",
          reconciliation: {
            checks: [
              { code: "CORE_TXN_TOTAL_VS_PROVIDER_GRAND", status: "FAIL", difference: "0.01" },
              { code: "PRODUCT_TA_QTY", status: "FAIL", difference: "1.00" },
              { code: "PROVIDER_MANUAL_ZERO", status: "PASS" },
            ],
          },
        },
      }),
    );
    const msg = formatFuelBvdReviewActionError(err);
    expect(msg).toContain("Source reconciliation failed");
    expect(msg).toContain("CORE_TXN_TOTAL_VS_PROVIDER_GRAND");
    expect(msg).not.toContain("PROVIDER_MANUAL_ZERO");
  });
});
