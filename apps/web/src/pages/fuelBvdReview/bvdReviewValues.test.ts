import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import { extractedValue, isFieldCorrected, reviewedValue } from "./bvdReviewValues";

const baseRow: FuelBvdRow = {
  id: 1,
  import_id: "import",
  row_type: "TRANSACTION",
  unit_number: "1100",
};

describe("bvdReviewValues", () => {
  it("detects corrected vs match", () => {
    expect(isFieldCorrected(baseRow, "unit_number", {})).toBe(false);
    expect(reviewedValue(baseRow, "unit_number", { "1:unit_number": "110A" })).toBe("110A");
    expect(isFieldCorrected(baseRow, "unit_number", { "1:unit_number": "110A" })).toBe(true);
  });

  it("uses persisted correction overlay", () => {
    const row: FuelBvdRow = {
      ...baseRow,
      field_corrections: {
        unit_number: { extracted_value: "1100", reviewed_value: "110A" },
      },
    };
    expect(extractedValue(row, "unit_number")).toBe("1100");
    expect(reviewedValue(row, "unit_number", {})).toBe("110A");
    expect(isFieldCorrected(row, "unit_number", {})).toBe(true);
  });
});
