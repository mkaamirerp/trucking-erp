import { describe, expect, it } from "vitest";
import type { FuelBvdRow } from "../../api";
import {
  abbreviateFuelQuantityUnit,
  formatFuelTxnQuantityWithUnit,
  inferFuelQuantityUnitFromCurrency,
} from "./fuelTxnQuantityDisplay";

function row(partial: Partial<FuelBvdRow>): FuelBvdRow {
  return { id: 1, import_id: "x", row_type: "TRANSACTION", ...partial } as FuelBvdRow;
}

describe("fuelTxnQuantityDisplay", () => {
  it("abbreviates canonical units", () => {
    expect(abbreviateFuelQuantityUnit("litres")).toBe("L");
    expect(abbreviateFuelQuantityUnit("gallons")).toBe("gal");
  });

  it("infers L from CAD/CN and gal from USD/US", () => {
    expect(inferFuelQuantityUnitFromCurrency("CAD")).toBe("L");
    expect(inferFuelQuantityUnitFromCurrency("CN")).toBe("L");
    expect(inferFuelQuantityUnitFromCurrency("USD")).toBe("gal");
  });

  it("formats quantity with explicit unit", () => {
    expect(
      formatFuelTxnQuantityWithUnit(
        row({ qty: "674.17", quantity_unit: "litres", cur: "CAD" }),
      ),
    ).toBe("674.17 L");
  });

  it("formats BVD quantity with currency inference", () => {
    expect(formatFuelTxnQuantityWithUnit(row({ qty: "719.50", cur: "CN" }))).toBe("719.50 L");
    expect(formatFuelTxnQuantityWithUnit(row({ qty: "50.14", cur: "US" }))).toBe("50.14 gal");
  });
});
