import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import type { BvdFieldSlot } from "./bvdFieldSlots";
import { getReviewFieldState } from "./bvdFieldCapture";

function headerRow(overrides: Partial<FuelBvdRow> = {}): FuelBvdRow {
  return {
    id: 1,
    import_id: "imp",
    row_type: "HEADER",
    source_page: 1,
    invoice_number: "972201",
    client_email: "",
    ...overrides,
  } as FuelBvdRow;
}

function slotFor(fieldName: string, ambiguous = false): BvdFieldSlot {
  return {
    fuelBvdId: 1,
    fieldName,
    selectionKey: `1:${fieldName}`,
    page: 1,
    rowType: "HEADER",
    sourceRowNumber: 0,
    left: 10,
    top: 20,
    width: 80,
    height: 12,
    ambiguous,
  };
}

describe("getReviewFieldState", () => {
  it("invoice 972201 client_email empty string is valid blank, not not_captured", () => {
    const row = headerRow({ client_email: "" });
    const state = getReviewFieldState(row, "client_email", slotFor("client_email"));
    expect(state).toBe("valid_blank");
    expect(state).not.toBe("not_captured");
  });

  it("contract field with ambiguous slot is not_captured", () => {
    const row = headerRow({ client_email: "" });
    const state = getReviewFieldState(row, "client_email", slotFor("client_email", true));
    expect(state).toBe("not_captured");
  });

  it("contract field with no slot is not_captured", () => {
    const row = headerRow({ client_phone: "555-0100" });
    const state = getReviewFieldState(row, "client_phone", undefined);
    expect(state).toBe("not_captured");
  });
});
