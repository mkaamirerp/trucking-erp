import { describe, expect, it } from "vitest";
import { formatFuelCurrencyFinancialDiscount } from "./fuelActivityCurrencyFinancial";

describe("formatFuelCurrencyFinancialDiscount", () => {
  it("shows 0.00 for null, blank, dash, and numeric zero", () => {
    expect(formatFuelCurrencyFinancialDiscount({ currency: "CAD", total_amount: "100", discount_amount: null })).toBe(
      "0.00",
    );
    expect(
      formatFuelCurrencyFinancialDiscount({ currency: "CAD", total_amount: "100", discount_amount: "" }),
    ).toBe("0.00");
    expect(
      formatFuelCurrencyFinancialDiscount({ currency: "CAD", total_amount: "100", discount_amount: "—" }),
    ).toBe("0.00");
    expect(
      formatFuelCurrencyFinancialDiscount({ currency: "CAD", total_amount: "100", discount_amount: "0.00" }),
    ).toBe("0.00");
  });

  it("formats non-zero discounts", () => {
    expect(
      formatFuelCurrencyFinancialDiscount({ currency: "USD", total_amount: "100", discount_amount: "5.92" }),
    ).toBe("5.92");
  });
});
