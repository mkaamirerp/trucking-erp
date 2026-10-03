import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { bvdReviewFieldDisplay } from "./bvdParsedDisplay";

function txn(partial: Partial<FuelBvdRow>): FuelBvdRow {
  return {
    id: 1,
    import_id: "imp",
    row_type: "TRANSACTION",
    ...partial,
  } as FuelBvdRow;
}

describe("bvdReviewFieldDisplay", () => {
  it("blank provider money fields render as 0.00", () => {
    expect(bvdReviewFieldDisplay(txn({}), "disc_amt")).toBe("0.00");
    expect(bvdReviewFieldDisplay(txn({ gst: "" }), "gst")).toBe("0.00");
    expect(bvdReviewFieldDisplay(txn({ hst: "0.00" }), "hst")).toBe("0.00");
  });

  it("non-money blanks stay em dash", () => {
    expect(bvdReviewFieldDisplay(txn({ driver_name: "" }), "driver_name")).toBe("—");
  });
});
